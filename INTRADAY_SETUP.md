# 🚀 Intraday Trading Bot Setup Guide

This guide explains how to configure and run the intraday trading analysis module.

---

## 1. Prerequisites

- **Python 3.10+**
- **Alpaca API Keys** (SIP feed recommended for best accuracy)
- **Discord Webhook URL**
- **PostgreSQL Database** (Optional, falls back to SQLite `trading.db`)

---

## 2. Configuration (`config/config.json`)

Ensure the `intraday` section is correctly populated:

```json
"intraday": {
    "enabled": true,
    "timeframe": "5m",
    "strategy_version": "1.0.0",
    "database_url": "postgresql://user:password@localhost/trading_db",
    "filters": {
        "rsi_min": 55,
        "rsi_max": 70,
        "volume_multiplier": 1.5,
        "volume_period": 20,
        "ema_fast": 9,
        "ema_slow": 20,
        "risk_reward_ratio": 2.0,
        "atr_period": 14
    },
    "discord": {
        "webhook_url": "YOUR_DISCORD_INTRADAY_WEBHOOK_URL"
    }
}
```

---

## 3. Installation

```bash
pip install -r requirements.txt
playwright install chromium
```

---

## 4. Running the Bot

To start the intraday trading analysis bot:

```bash
export PYTHONPATH=$PYTHONPATH:.
python src/intraday_bot.py
```

---

## 5. How It Works

1. **Scanner**: Scans the market using the TradingView screener to identify active candidate stocks.
2. **Analysis**: Fetches precise intraday bars from Alpaca and applies the rule-based strategy (VWAP, EMA, RSI, MACD, Volume).
3. **Alerts**: Sends structured Discord alerts for "NEW SIGNAL" with entry, stop-loss, and take-profit levels.
4. **Monitoring**: Continuously monitors the status of active trades (Triggered, Stop-Loss Hit, or Take-Profit Hit) and sends updates.
5. **Storage**: Persists every signal and status update in the database and `analysis/intraday_signals.json`.

---

## 6. Strategy Rules (Long-Only)

- **Entry**: Price > VWAP, EMA 9 > EMA 20, RSI between 55-70, MACD bullish crossover, and Volume > 1.5x average.
- **Trigger**: Break of previous candle high.
- **Stop-Loss**: Below previous candle low or 1x ATR, whichever is tighter (closer to entry).
- **Take-Profit**: 2.0x Risk/Reward ratio.
