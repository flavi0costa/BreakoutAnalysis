import logging
import time
import os
import sys
import json
from datetime import datetime, timedelta
import pytz

# --- DEFENSIVE PATH INJECTION ---
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, ".."))

# Remove script_dir from path if it's there to avoid shadowing the 'src' package
while script_dir in sys.path:
    sys.path.remove(script_dir)

# Add project root to the START of sys.path
if project_root not in sys.path:
    sys.path.insert(0, project_root)
# --------------------------------

from src.screeners.intraday_scanner import IntradayScanner
from src.strategies.intraday_strategy import IntradayStrategy
from src.utils.db_manager import DBManager, TradeStatusEnum
from src.llms.llm_client import LLMClient
from src.tradealerts import update_notify_json, send_notifications, parse_llm_analysis

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - INTRADAY_BOT - %(levelname)s - %(message)s')

class IntradayBot:
    def __init__(self, config_path='config/config.json'):
        self.project_root = project_root
        self.config_path = os.path.join(self.project_root, config_path)
        self.config = self._load_config()

        self.intraday_config = self.config.get('intraday', {})
        self.enabled = self.intraday_config.get('enabled', False)
        self.timeframe = self.intraday_config.get('timeframe', '5m')
        self.version = self.intraday_config.get('strategy_version', '1.0.0')

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

        self.scan_interval = self._get_scan_interval()

    def _load_config(self):
        try:
            with open(self.config_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Error loading config: {e}")
            return {}

    def _get_scan_interval(self):
        if self.timeframe == '1m': return 60
        if self.timeframe == '5m': return 120
        if self.timeframe == '15m': return 300
        return 300

    def send_discord_alert(self, title, content, ticker=None, embed_data=None):
        notification_item = {"title": title, "content": content}
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
        if not self.enabled: return
        logging.info(f"Starting intraday scan cycle for timeframe: {self.timeframe}")
        tickers = self.scanner.get_candidate_tickers()
        if not tickers: return
        self.monitor_active_trades()
        for ticker in tickers:
            try:
                active_signals = self.db.get_active_signals()
                if any(s.ticker == ticker for s in active_signals): continue
                df = self.scanner.get_intraday_data(ticker, self.timeframe)
                if df.empty: continue
                df = self.strategy.calculate_indicators(df)
                signal = self.strategy.check_long_conditions(df)
                if signal:
                    logging.info(f"NEW SIGNAL FOUND: {ticker}")
                    signal_id = self.db.add_signal(ticker, self.timeframe, signal['entry'], signal['stop_loss'], signal['take_profit'], signal['risk_reward'], signal['indicators'], signal['conditions'], self.version)
                    ai_analysis = "N/A"
                    if self.llm_client:
                        try:
                            # Use Ticker instead of ticker to match prompt requirements in some models
                            llm_input = {"Ticker": ticker, "timeframe": self.timeframe, "price": signal['entry'], "indicators": signal['indicators'], "conditions": signal['conditions']}
                            raw_analysis = self.llm_client.analyze_stock(llm_input)
                            ai_analysis = parse_llm_analysis(raw_analysis)
                        except Exception as e:
                            logging.error(f"LLM Analysis failed: {e}")
                    self.save_signal_to_json(ticker, signal, signal_id, ai_analysis)
                    fields = [{"name": "Ticker", "value": ticker, "inline": True}, {"name": "Entry", "value": f"{signal['entry']:.2f}", "inline": True}, {"name": "Stop-Loss", "value": f"{signal['stop_loss']:.2f}", "inline": True}, {"name": "Take-Profit", "value": f"{signal['take_profit']:.2f}", "inline": True}, {"name": "Risk/Reward", "value": f"{signal['risk_reward']}", "inline": True}]
                    cond_str = "\n".join([f"✅ {k.replace('_', ' ').title()}" for k, v in signal['conditions'].items() if v])
                    fields.append({"name": "Conditions Met", "value": cond_str, "inline": False})
                    if ai_analysis != "N/A": fields.append({"name": "🤖 AI Insights", "value": ai_analysis, "inline": False})
                    self.send_discord_alert(f"🚀 NEW INTRADAY LONG SIGNAL: {ticker}", f"A new long setup has been detected for {ticker} on the {self.timeframe} chart.", ticker, fields)
            except Exception as e:
                logging.error(f"Error processing ticker {ticker}: {e}")

    def monitor_active_trades(self):
        active_signals = self.db.get_active_signals()
        if not active_signals: return
        for signal in active_signals:
            try:
                curr_price = self.alpaca.get_current_price(signal.ticker)
                if curr_price is None: continue
                if signal.status == TradeStatusEnum.PENDING:
                    if curr_price >= signal.entry_price:
                        self.db.update_status(signal.id, TradeStatusEnum.TRIGGERED, f"Price {curr_price} hit entry")
                        self.send_discord_alert(f"🎯 Trade Triggered: {signal.ticker}", f"The long signal for {signal.ticker} has been triggered at {curr_price:.2f} (Entry: {signal.entry_price:.2f}).")
                elif signal.status == TradeStatusEnum.TRIGGERED:
                    if curr_price <= signal.stop_loss:
                        self.db.update_status(signal.id, TradeStatusEnum.STOP_LOSS, f"Price {curr_price} hit SL")
                        self.send_discord_alert(f"🛑 Stop-Loss Hit: {signal.ticker}", f"The trade for {signal.ticker} was closed at stop-loss level {signal.stop_loss:.2f} (Current: {curr_price:.2f}).")
                    elif curr_price >= signal.take_profit:
                        self.db.update_status(signal.id, TradeStatusEnum.TAKE_PROFIT, f"Price {curr_price} hit TP")
                        self.send_discord_alert(f"💰 Take-Profit Hit: {signal.ticker}", f"The trade for {signal.ticker} reached its take-profit target of {signal.take_profit:.2f}! 🚀")
            except Exception as e:
                logging.error(f"Error monitoring signal {signal.id}: {e}")

    def save_signal_to_json(self, ticker, signal, signal_id, ai_analysis="N/A"):
        signals_file = os.path.join(self.project_root, "analysis", "intraday_signals.json")
        os.makedirs(os.path.dirname(signals_file), exist_ok=True)
        data = []
        if os.path.exists(signals_file):
            with open(signals_file, 'r') as f:
                try: data = json.load(f)
                except: pass
        data.append({"id": signal_id, "timestamp": datetime.now().isoformat(), "ticker": ticker, "timeframe": self.timeframe, "entry": signal['entry'], "stop_loss": signal['stop_loss'], "take_profit": signal['take_profit'], "risk_reward": signal['risk_reward'], "indicators": signal['indicators'], "trigger_conditions": signal['conditions'], "ai_analysis": ai_analysis, "version": self.version})
        with open(signals_file, 'w') as f: json.dump(data, f, indent=4)

    def run(self):
        logging.info(f"Intraday Bot started. timeframe={self.timeframe}")
        while True:
            try:
                now = datetime.now()
                interval_minutes = self.scan_interval // 60
                sleep_seconds = self.scan_interval - ((now.minute % interval_minutes) * 60 + now.second)
                if sleep_seconds <= 0: sleep_seconds = self.scan_interval
                sleep_seconds += 2
                logging.info(f"Next scan in {sleep_seconds:.1f}s...")
                time.sleep(sleep_seconds)
                self.process_signals()
            except KeyboardInterrupt: break
            except Exception as e:
                logging.error(f"Unexpected error: {e}")
                time.sleep(60)

if __name__ == "__main__":
    bot = IntradayBot()
    bot.run()
