import logging
import time
import os
import sys
import json
from datetime import datetime, timedelta
import pytz

# --- ULTRA-ROBUST PATH INJECTION ---
# This ensures that 'src' is always discoverable regardless of how the script is called.
def _setup_paths():
    current_file = os.path.abspath(__file__)
    current_dir = os.path.dirname(current_file)
    project_root = os.path.abspath(os.path.join(current_dir, ".."))

    # Add project root to sys.path if not already there
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    # Remove the 'src' directory itself from sys.path to avoid shadowed imports
    if current_dir in sys.path:
        sys.path.remove(current_dir)

_setup_paths()
# ----------------------------------

from src.screeners.intraday_scanner import IntradayScanner
from src.strategies.intraday_strategy import IntradayStrategy
from src.utils.db_manager import DBManager, TradeStatusEnum
from src.llms.llm_client import LLMClient
from src.tradealerts import update_notify_json, send_notifications, parse_llm_analysis

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - INTRADAY_BOT - %(levelname)s - %(message)s')

class IntradayBot:
    def __init__(self, config_path='config/config.json'):
        # Determine project root: parent of the 'src' directory
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.project_root = os.path.abspath(os.path.join(script_dir, ".."))
        self.config_path = os.path.join(self.project_root, config_path)
        self.config = self._load_config()

        self.intraday_config = self.config.get('intraday', {})
        self.enabled = self.intraday_config.get('enabled', False)
        self.timeframe = self.intraday_config.get('timeframe', '5m')
        self.version = self.intraday_config.get('strategy_version', '1.0.0')
        self.discord_webhook = self.intraday_config.get('discord', {}).get('webhook_url')

        self.scanner = IntradayScanner(config_path=config_path)
        from src.utils.alpaca_client import AlpacaClient
        self.alpaca = AlpacaClient(config_path=config_path)
        self.strategy = IntradayStrategy(self.config)
        self.db = DBManager(config_path=config_path)

        try:
            self.llm_client = LLMClient(config_path=self.config_path)
        except Exception as e:
            logging.warning(f"Failed to initialize LLMClient: {e}")
            self.llm_client = None

        self.last_scan_time = None
        self.scan_interval = self._get_scan_interval()

    def _load_config(self):
        try:
            with open(self.config_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Error loading config in IntradayBot: {e}")
            return {}

    def _get_scan_interval(self):
        """Determines scan frequency based on timeframe."""
        if self.timeframe == '1m': return 60
        if self.timeframe == '5m': return 120 # Scan every 2 minutes as requested
        if self.timeframe == '15m': return 300 # Scan every 5 minutes as requested
        return 300

    def send_discord_alert(self, title, content, ticker=None, embed_data=None):
        """Sends a structured alert to Discord via the existing notification system."""
        notification_item = {
            "title": title,
            "content": content
        }

        if embed_data:
            field_str = ""
            for field in embed_data:
                field_str += f"\n**{field['name']}:** {field['value']}"
            notification_item["content"] += f"\n{field_str}"

        notification_item["content"] += f"\n\n*Strategy Version: {self.version} | Timeframe: {self.timeframe}*"

        try:
            update_notify_json([notification_item])
            send_notifications()
        except Exception as e:
            logging.error(f"Failed to send Discord alert: {e}")

    def process_signals(self):
        """Main loop for scanning and processing signals."""
        if not self.enabled:
            logging.info("Intraday bot is disabled in config.")
            return

        logging.info(f"Starting intraday scan cycle for timeframe: {self.timeframe}")

        tickers = self.scanner.get_candidate_tickers()
        if not tickers:
            logging.info("No candidate tickers found by screener.")
            return

        self.monitor_active_trades()

        for ticker in tickers:
            try:
                active_signals = self.db.get_active_signals()
                if any(s.ticker == ticker for s in active_signals):
                    continue

                df = self.scanner.get_intraday_data(ticker, self.timeframe)
                if df.empty: continue

                df = self.strategy.calculate_indicators(df)
                signal = self.strategy.check_long_conditions(df)

                if signal:
                    logging.info(f"NEW SIGNAL FOUND: {ticker}")

                    signal_id = self.db.add_signal(
                        ticker=ticker,
                        timeframe=self.timeframe,
                        entry=signal['entry'],
                        sl=signal['stop_loss'],
                        tp=signal['take_profit'],
                        rr=signal['risk_reward'],
                        indicators=signal['indicators'],
                        conditions=signal['conditions'],
                        version=self.version
                    )

                    ai_analysis = "N/A"
                    if self.llm_client:
                        try:
                            llm_input = {
                                "ticker": ticker,
                                "timeframe": self.timeframe,
                                "price": signal['entry'],
                                "indicators": signal['indicators'],
                                "conditions": signal['conditions']
                            }
                            raw_analysis = self.llm_client.analyze_stock(llm_input)
                            ai_analysis = parse_llm_analysis(raw_analysis)
                        except Exception as e:
                            logging.error(f"LLM Analysis failed for {ticker}: {e}")

                    self.save_signal_to_json(ticker, signal, signal_id, ai_analysis)

                    fields = [
                        {"name": "Ticker", "value": ticker, "inline": True},
                        {"name": "Entry", "value": f"{signal['entry']:.2f}", "inline": True},
                        {"name": "Stop-Loss", "value": f"{signal['stop_loss']:.2f}", "inline": True},
                        {"name": "Take-Profit", "value": f"{signal['take_profit']:.2f}", "inline": True},
                        {"name": "Risk/Reward", "value": f"{signal['risk_reward']}", "inline": True},
                    ]

                    cond_str = "\n".join([f"✅ {k.replace('_', ' ').title()}" for k, v in signal['conditions'].items() if v])
                    fields.append({"name": "Conditions Met", "value": cond_str, "inline": False})

                    if ai_analysis != "N/A":
                        fields.append({"name": "🤖 AI Insights", "value": ai_analysis, "inline": False})

                    self.send_discord_alert(
                        title=f"🚀 NEW INTRADAY LONG SIGNAL: {ticker}",
                        content=f"A new long setup has been detected for {ticker} on the {self.timeframe} chart.",
                        ticker=ticker,
                        embed_data=fields
                    )
            except Exception as e:
                logging.error(f"Error processing ticker {ticker}: {e}")

    def monitor_active_trades(self):
        """Checks status of active/pending signals using optimized quote fetching."""
        active_signals = self.db.get_active_signals()
        if not active_signals: return

        for signal in active_signals:
            try:
                curr_price = self.alpaca.get_current_price(signal.ticker)
                if curr_price is None:
                    continue

                if signal.status == TradeStatusEnum.PENDING:
                    if curr_price >= signal.entry_price:
                        self.db.update_status(signal.id, TradeStatusEnum.TRIGGERED, f"Price {curr_price} hit entry {signal.entry_price}")
                        self.send_discord_alert(
                            title=f"🎯 Trade Triggered: {signal.ticker}",
                            content=f"The long signal for {signal.ticker} has been triggered at {curr_price:.2f}."
                        )

                elif signal.status == TradeStatusEnum.TRIGGERED:
                    if curr_price <= signal.stop_loss:
                        self.db.update_status(signal.id, TradeStatusEnum.STOP_LOSS, f"Price {curr_price} hit SL {signal.stop_loss}")
                        self.send_discord_alert(
                            title=f"🛑 Stop-Loss Hit: {signal.ticker}",
                            content=f"The trade for {signal.ticker} was closed at stop-loss level {signal.stop_loss:.2f} (Current: {curr_price:.2f})."
                        )
                    elif curr_price >= signal.take_profit:
                        self.db.update_status(signal.id, TradeStatusEnum.TAKE_PROFIT, f"Price {curr_price} hit TP {signal.take_profit}")
                        self.send_discord_alert(
                            title=f"💰 Take-Profit Hit: {signal.ticker}",
                            content=f"The trade for {signal.ticker} reached its take-profit target of {signal.take_profit:.2f}! 🚀"
                        )
            except Exception as e:
                logging.error(f"Error monitoring signal {signal.id}: {e}")

    def save_signal_to_json(self, ticker, signal, signal_id, ai_analysis="N/A"):
        """Saves signal to a persistent JSON file."""
        signals_file = os.path.join(self.project_root, "analysis", "intraday_signals.json")
        os.makedirs(os.path.dirname(signals_file), exist_ok=True)

        data = []
        if os.path.exists(signals_file):
            with open(signals_file, 'r') as f:
                try:
                    data = json.load(f)
                except: pass

        signal_entry = {
            "id": signal_id,
            "timestamp": datetime.now().isoformat(),
            "ticker": ticker,
            "timeframe": self.timeframe,
            "entry": signal['entry'],
            "stop_loss": signal['stop_loss'],
            "take_profit": signal['take_profit'],
            "risk_reward": signal['risk_reward'],
            "indicators": signal['indicators'],
            "trigger_conditions": signal['conditions'],
            "ai_analysis": ai_analysis,
            "version": self.version
        }
        data.append(signal_entry)

        with open(signals_file, 'w') as f:
            json.dump(data, f, indent=4)

    def run(self):
        """Infinite loop for the bot, aligning with candle closes."""
        logging.info(f"Intraday Bot started. timeframe={self.timeframe}, interval={self.scan_interval}s")

        while True:
            try:
                now = datetime.now()
                interval_minutes = self.scan_interval // 60
                seconds_since_last_interval = (now.minute % interval_minutes) * 60 + now.second
                sleep_seconds = self.scan_interval - seconds_since_last_interval

                if sleep_seconds <= 0:
                    sleep_seconds = self.scan_interval

                sleep_seconds += 2

                logging.info(f"Next scan in {sleep_seconds:.1f}s (aligning with {self.timeframe} candle close)...")
                time.sleep(sleep_seconds)

                self.process_signals()
                logging.info(f"Cycle complete.")
            except KeyboardInterrupt:
                logging.info("Bot stopped by user.")
                break
            except Exception as e:
                logging.error(f"Unexpected error in bot loop: {e}")
                time.sleep(60)

if __name__ == "__main__":
    bot = IntradayBot()
    bot.run()
