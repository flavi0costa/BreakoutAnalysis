import pandas as pd
import numpy as np
import logging

class IntradayStrategy:
    def __init__(self, config):
        self.config = config.get('intraday', {}).get('filters', {})
        self.rsi_min = self.config.get('rsi_min', 55)
        self.rsi_max = self.config.get('rsi_max', 70)
        self.volume_mult = self.config.get('volume_multiplier', 1.5)
        self.volume_period = self.config.get('volume_period', 20)
        self.ema_fast_len = self.config.get('ema_fast', 9)
        self.ema_slow_len = self.config.get('ema_slow', 20)
        self.rr_ratio = self.config.get('risk_reward_ratio', 2.0)
        self.atr_period = self.config.get('atr_period', 14)

    def calculate_indicators(self, df):
        """Calculates indicators needed for the strategy."""
        if df.empty or len(df) < max(self.volume_period, self.ema_slow_len, self.atr_period, 30):
            return df

        # EMA
        df['ema_fast'] = df['close'].ewm(span=self.ema_fast_len, adjust=False).mean()
        df['ema_slow'] = df['close'].ewm(span=self.ema_slow_len, adjust=False).mean()

        # RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))

        # MACD
        exp1 = df['close'].ewm(span=12, adjust=False).mean()
        exp2 = df['close'].ewm(span=26, adjust=False).mean()
        df['macd'] = exp1 - exp2
        df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()

        # VWAP (Reset daily)
        df['date'] = df.index.date
        v = df['volume'].values
        tp = (df['high'] + df['low'] + df['close']).values / 3

        # Calculate cumulative volume and price-volume product grouped by date
        df['pv'] = tp * v
        df['cum_pv'] = df.groupby('date')['pv'].cumsum()
        df['cum_v'] = df.groupby('date')['volume'].cumsum()
        df['vwap'] = df['cum_pv'] / df['cum_v']

        # Cleanup temporary columns
        df.drop(columns=['date', 'pv', 'cum_pv', 'cum_v'], inplace=True)

        # ATR
        high_low = df['high'] - df['low']
        high_cp = np.abs(df['high'] - df['close'].shift())
        low_cp = np.abs(df['low'] - df['close'].shift())
        tr = pd.concat([high_low, high_cp, low_cp], axis=1).max(axis=1)
        df['atr'] = tr.rolling(window=self.atr_period).mean()

        # Volume SMA
        df['volume_sma'] = df['volume'].rolling(window=self.volume_period).mean()

        return df

    def check_long_conditions(self, df):
        """
        Checks for long entry conditions on the latest closed candle.
        Conditions:
        1. Price above VWAP
        2. EMA 9 > EMA 20
        3. RSI between 55 and 70
        4. MACD line above signal line
        5. Current volume > 1.5x average volume (last 20 candles)
        6. Break of previous candle high
        """
        if len(df) < 2:
            return None

        # We look at the latest completed candle (index -1)
        # Note: If this is called in real-time, -1 is the current forming candle.
        # For strategy validation, we usually use the last CLOSED candle.
        curr = df.iloc[-1]
        prev = df.iloc[-2]

        conditions = {
            "price_above_vwap": curr['close'] > curr['vwap'],
            "ema_cross": curr['ema_fast'] > curr['ema_slow'],
            "rsi_range": self.rsi_min <= curr['rsi'] <= self.rsi_max,
            "macd_bullish": curr['macd'] > curr['macd_signal'],
            "volume_confirmation": curr['volume'] > (curr['volume_sma'] * self.volume_mult),
            "break_prev_high": curr['close'] > prev['high']
        }

        all_met = all(conditions.values())

        if all_met:
            # Calculate Entry, SL, TP
            entry = curr['close'] # Or prev['high'] as per requirement "Break of previous candle high"
            # Actually, "Break of previous candle high" is the trigger.
            # If curr['close'] > prev['high'], it already broke it.

            # SL: Below previous candle low OR 1x ATR, whichever is tighter
            sl_prev_low = prev['low']
            sl_atr = curr['close'] - curr['atr']
            stop_loss = max(sl_prev_low, sl_atr) # "whichever is tighter" means closer to entry -> higher price for long SL

            risk = entry - stop_loss
            if risk <= 0:
                return None # Invalid risk

            take_profit = entry + (self.rr_ratio * risk)

            return {
                "entry": entry,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "risk_reward": self.rr_ratio,
                "conditions": conditions,
                "indicators": {
                    "rsi": curr['rsi'],
                    "macd": curr['macd'],
                    "macd_signal": curr['macd_signal'],
                    "vwap": curr['vwap'],
                    "ema_fast": curr['ema_fast'],
                    "ema_slow": curr['ema_slow'],
                    "volume": curr['volume'],
                    "avg_volume": curr['volume_sma'],
                    "atr": curr['atr']
                }
            }

        return None
