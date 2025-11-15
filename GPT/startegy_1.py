"""
Flag & Pennant Swing-Trading Bot for Angel One (NSE)

This script logs into SmartAPI, scans Nifty 500 stocks for bullish flag/pennant patterns
on daily and 15-min data, applies filters (market cap, liquidity), computes
entry/SL/target/quantity, and places BUY orders. It uses a 25k capital with 25% per trade and 1% risk rules.
"""

import os
import time
import json
import logging
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
from SmartApi import SmartConnect  # Angel One SmartAPI Python SDK
import pyotp

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === Configurable Strategy Parameters ===
CAPITAL = 25000.0
TRADE_ALLOC = 0.25 * CAPITAL     # 25% of capital per trade (₹6,250)
RISK_PER_TRADE = 0.01 * CAPITAL  # 1% of capital (₹250)
SLIPPAGE_PCT = 0.001            # 0.1% slippage
MIN_MKT_CAP = 1e11              # ₹1,000 Crore = 1e11 rupees
MIN_DAILY_TURNOVER = 2 * TRADE_ALLOC  # ₹12,500
FLAGPOLE_LOOKBACK = 20  # days for pole
FLAG_LOOKBACK = 10      # days for consolidation
VOLUME_MULT = 1.5       # breakout volume must exceed 1.5x avg

# Interval mappings
INTERVAL_DAILY = "ONE_DAY"
INTERVAL_15MIN = "FIFTEEN_MINUTE"

# AWS/Env variables for SmartAPI credentials
API_KEY = os.getenv("SMARTAPI_API_KEY")
CLIENT_CODE = os.getenv("SMARTAPI_CLIENT_CODE")  # Angel client code
PASSWORD = os.getenv("SMARTAPI_PASSWORD")        # Angel PIN/password
TOTP_SECRET = os.getenv("SMARTAPI_TOTP_SECRET")  # Base32 TOTP secret

def login_smartapi():
    """Log into Angel One SmartAPI and return SmartConnect instance with tokens."""
    if not all([API_KEY, CLIENT_CODE, PASSWORD, TOTP_SECRET]):
        logger.error("Missing SmartAPI credentials in environment.")
        raise SystemExit("Set SMARTAPI_API_KEY, SMARTAPI_CLIENT_CODE, SMARTAPI_PASSWORD, SMARTAPI_TOTP_SECRET")
    smartapi = SmartConnect(API_KEY)
    # Generate 2FA TOTP code
    totp = pyotp.TOTP(TOTP_SECRET).now()
    data = smartapi.generateSession(CLIENT_CODE, PASSWORD, totp)
    if not data.get("status"):
        logger.error(f"SmartAPI login failed: {data}")
        raise RuntimeError("Login failed")
    authToken = data["data"]["jwtToken"]
    refreshToken = data["data"]["refreshToken"]
    # Set tokens for subsequent requests
    smartapi.token = authToken
    smartapi.generateToken(refreshToken)
    logger.info("SmartAPI login successful.")
    return smartapi

def get_nifty500_symbols():
    """
    Placeholder function to get Nifty 500 symbols.
    In practice, this could fetch from an API or a static list.
    Here we return a short sample list for demo.
    """
    # TODO: Replace with actual Nifty 500 retrieval
    return ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS"]

def fetch_market_cap(symbol):
    """Fetch market cap for given NSE symbol via yfinance (returns rupees)."""
    ticker = yf.Ticker(symbol)
    info = ticker.info
    cap = info.get("marketCap", None)
    if cap is None:
        return 0.0
    return float(cap)

def fetch_historical(symbol, interval, days=60):
    """
    Fetch historical OHLCV data for the symbol.
    - Using yfinance for daily data.
    - For intraday (15-min), could use SmartAPI if available.
    """
    end = datetime.now()
    if interval == INTERVAL_DAILY:
        start = end - timedelta(days=days)
        df = yf.download(symbol, start=start, end=end, interval='1d')
        df = df.dropna().reset_index()
        df.rename(columns={"Date": "datetime", "Open": "open", "High": "high", "Low": "low",
                           "Close": "close", "Volume": "volume"}, inplace=True)
    else:
        # For FIFTEEN_MINUTE, use SmartAPI (requires login first)
        # Assumes smartapi.generateSession already done.
        # Yahoo Finance intraday data is not reliable beyond 60 days.
        start = (end - timedelta(days=7)).strftime("%Y-%m-%d %H:%M")
        end_str = end.strftime("%Y-%m-%d %H:%M")
        param = {
            "exchange": "NSE",
            "symboltoken": None,  # will be filled externally (see symboltoken map)
            "interval": INTERVAL_15MIN,
            "fromdate": start,
            "todate": end_str
        }
        # We'll fetch candles via SmartAPI.getCandleData in main flow (needs symboltoken).
        return None  # indicate we should use SmartAPI in main code
    return df

def compute_atr(df, period=14):
    """Compute ATR (Average True Range) for given OHLC DataFrame."""
    highs = df['high'].values
    lows = df['low'].values
    closes = df['close'].values
    trs = []
    for i in range(1, len(df)):
        high_low = highs[i] - lows[i]
        high_prev = abs(highs[i] - closes[i-1])
        low_prev = abs(lows[i] - closes[i-1])
        tr = max(high_low, high_prev, low_prev)
        trs.append(tr)
    if not trs:
        return 0.0
    atr = np.mean(trs[-period:]) if len(trs)>=period else np.mean(trs)
    return atr

def detect_flag_pennant(df):
    """
    Detect bullish flag/pennant pattern in price DataFrame `df` (with columns datetime, open, high, low, close).
    Returns consolidation_high, consolidation_low, flagpole_height or None if no pattern.
    """
    if len(df) < FLAGPOLE_LOOKBACK + 5:
        return None
    # Identify potential flagpole: last peak in the last FLAGPOLE_LOOKBACK days
    lookback_df = df[-FLAGPOLE_LOOKBACK:]
    flagpole_start = lookback_df['close'].idxmin()
    flagpole_end = lookback_df['close'].idxmax()
    if flagpole_end <= flagpole_start:
        return None
    flagpole_height = lookback_df.loc[flagpole_end, 'close'] - lookback_df.loc[flagpole_start, 'close']
    # Require significant flagpole (e.g. >5% move)
    if flagpole_height / lookback_df.loc[flagpole_start, 'close'] < 0.05:
        return None
    # Consolidation: data after flagpole_end
    cons_df = df.iloc[flagpole_end+1:]
    if cons_df.empty or len(cons_df) < 3:
        return None
    cons_high = cons_df['high'].max()
    cons_low = cons_df['low'].min()
    # Narrow range check: consolidation width small relative to pole?
    if (cons_high - cons_low) / flagpole_height > 0.5:
        return None
    # Pennant shape vs flag shape: optional, here treat any tight range as valid
    return (cons_high, cons_low, flagpole_height)

def compute_quantity(entry_price, sl_price):
    """Compute buy quantity based on allocation and risk limits."""
    # Allocation-based
    q_alloc = int(TRADE_ALLOC / entry_price)
    # Risk-based
    risk_amt = RISK_PER_TRADE
    q_risk = int(risk_amt / max(1e-6, (entry_price - sl_price)))
    qty = min(q_alloc, q_risk)
    return qty

def place_order(smartapi, symbol, symbol_token, entry_price, sl_price, target_price, qty):
    """Place a BUY order via SmartAPI with given parameters."""
    order_params = {
        "variety": "NORMAL",
        "tradingsymbol": symbol.split(".")[0] + "-EQ",  # e.g. "TCS-EQ"
        "symboltoken": str(symbol_token),
        "transactiontype": "BUY",
        "exchange": "NSE",
        "ordertype": "LIMIT",
        "producttype": "INTRADAY",
        "duration": "DAY",
        "price": str(round(entry_price * (1+SLIPPAGE_PCT), 2)),  # limit slightly above entry
        "squareoff": str(round(target_price, 2)),
        "stoploss": str(round(sl_price, 2)),
        "quantity": str(qty)
    }
    try:
        order_id = smartapi.placeOrder(order_params)
        logger.info(f"Order placed for {symbol}: ID={order_id}")
        return order_id
    except Exception as e:
        logger.error(f"Order placement failed for {symbol}: {e}")
        return None

# === Main Trading Flow ===

def main():
    smartapi = login_smartapi()
    symbols = get_nifty500_symbols()
    trades_executed = []

    for symbol in symbols:
        # Skip if not NSE symbol format
        if not symbol.endswith(".NS"):
            continue

        # 1. Market Cap filter
        mcap = fetch_market_cap(symbol)
        if mcap < MIN_MKT_CAP:
            logger.info(f"{symbol}: Market cap {mcap:.0f} below threshold.")
            continue

        # 2. Fetch daily data and check for pattern breakout
        df_daily = fetch_historical(symbol, INTERVAL_DAILY, days=FLAGPOLE_LOOKBACK+30)
        if df_daily is None or df_daily.empty:
            logger.warning(f"{symbol}: No daily data.")
            continue

        pattern = detect_flag_pennant(df_daily)
        if not pattern:
            continue  # no flag/pennant found
        cons_high, cons_low, flagpole_h = pattern
        last_close = df_daily.iloc[-1]['close']
        # Check breakout (yesterday's close above consolidation high)
        if last_close <= cons_high:
            continue
        # Volume confirmation on breakout day
        avg_vol = df_daily['volume'][-30:].mean()
        if df_daily.iloc[-1]['volume'] < VOLUME_MULT * avg_vol:
            continue

        entry_price = last_close
        sl_price = cons_low - compute_atr(df_daily)
        target_price = entry_price + 2*(entry_price - sl_price)
        # 3. Liquidity filter: 30-day avg turnover
        avg_turnover = (df_daily['close'] * df_daily['volume'])[-30:].mean()
        if avg_turnover < MIN_DAILY_TURNOVER:
            logger.info(f"{symbol}: Illiquid (avg turnover {avg_turnover}). Skipping.")
            continue

        qty = compute_quantity(entry_price*(1+SLIPPAGE_PCT), sl_price)
        if qty <= 0:
            continue

        # 4. Place BUY order
        # Get symboltoken (placeholder: user must supply mapping; here we assume known tokens)
        symbol_token = lookup_symbol_token(symbol)  # implement this function as needed
        order_id = place_order(smartapi, symbol, symbol_token, entry_price, sl_price, target_price, qty)
        if order_id:
            trades_executed.append({
                "symbol": symbol,
                "entry": entry_price,
                "stop_loss": sl_price,
                "target": target_price,
                "qty": qty,
                "order_id": order_id
            })

    # Print or log executed trades
    if trades_executed:
        print("Executed Trades Summary:")
        print(json.dumps(trades_executed, indent=2))
    else:
        print("No trades executed.")

# Helper: placeholder for symboltoken lookup
def lookup_symbol_token(symbol):
    """
    Convert symbol (e.g. 'TCS.NS') to Angel One symboltoken.
    In production, this could query SmartAPI or maintain an instrument mapping.
    """
    instrument_map = {
        "RELIANCE.NS": 3045,  # example token (not real)
        "TCS.NS": 3046,
        "INFY.NS": 3047,
        "HDFCBANK.NS": 3048
    }
    return instrument_map.get(symbol, "")

if __name__ == "__main__":
    main()
