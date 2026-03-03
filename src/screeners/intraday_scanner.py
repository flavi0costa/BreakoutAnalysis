import logging
import pandas as pd
import sys
import os

# --- ULTRA-ROBUST PATH INJECTION ---
def _setup_paths():
    current_file = os.path.abspath(__file__)
    current_dir = os.path.dirname(current_file)
    project_root = os.path.abspath(os.path.join(current_dir, "..", ".."))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
_setup_paths()
# ----------------------------------

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.data.enums import DataFeed, Adjustment
from datetime import datetime, timedelta
import pytz
import json

class IntradayScanner:
    def __init__(self, config_path='config/config.json'):
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
        self.config_path = os.path.join(project_root, config_path)
        self.config = self._load_config()

        alpaca_config = self.config.get('alpaca', {})
        api_key = alpaca_config.get('api_key')
        api_secret = alpaca_config.get('api_secret')

        feed_str = alpaca_config.get('data_feed', 'iex').lower()
        self.data_feed = DataFeed.SIP if feed_str == 'sip' else DataFeed.IEX

        try:
            self.data_client = StockHistoricalDataClient(api_key=api_key, secret_key=api_secret)
            logging.info(f"IntradayScanner initialized with Alpaca {feed_str.upper()} feed.")
        except Exception as e:
            logging.error(f"Failed to initialize Alpaca Data Client: {e}")
            self.data_client = None

    def _load_config(self):
        try:
            with open(self.config_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Error loading config in IntradayScanner: {e}")
            return {}

    def get_intraday_data(self, ticker, timeframe_str='5m', lookback_candles=100):
        """Fetches intraday bars for a given ticker and timeframe."""
        if not self.data_client:
            logging.error("Data client not available.")
            return pd.DataFrame()

        # Map timeframe string to Alpaca TimeFrame using TimeFrameUnit
        if timeframe_str == '1m':
            tf = TimeFrame.Minute
        elif timeframe_str == '5m':
            tf = TimeFrame(5, TimeFrameUnit.Minute)
        elif timeframe_str == '15m':
            tf = TimeFrame(15, TimeFrameUnit.Minute)
        else:
            tf = TimeFrame.Minute

        eastern = pytz.timezone('US/Eastern')
        now = datetime.now(eastern)
        start = now - timedelta(days=2) # Safe margin

        try:
            request_params = StockBarsRequest(
                symbol_or_symbols=[ticker],
                timeframe=tf,
                start=start,
                end=now,
                feed=self.data_feed,
                adjustment=Adjustment.ALL
            )
            bars = self.data_client.get_stock_bars(request_params)

            if ticker in bars.df.index.get_level_values('symbol').unique():
                df = bars.df.loc[ticker].copy()
                df = df.sort_index()
                return df
            else:
                logging.warning(f"No bars returned for {ticker}")
                return pd.DataFrame()
        except Exception as e:
            logging.error(f"Error fetching intraday data for {ticker}: {e}")
            return pd.DataFrame()

    def get_candidate_tickers(self):
        """
        Identify active candidate tickers using the existing market_gainers screener logic.
        """
        from src.screeners.market_gainers import fetch_screener_data

        logging.info("Scanning for candidate tickers using market screener...")
        df = fetch_screener_data(self.config)

        if df is not None and not df.empty:
            tickers = df['name'].tolist()
            logging.info(f"Screener found {len(tickers)} candidate tickers.")
            return tickers
        return []
