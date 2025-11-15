#!/usr/bin/env python3
import os
import time
import json
import pyotp
import yfinance as yf
import pandas as pd
import talib
from datetime import datetime, timedelta
from smartapi import SmartConnect
import logging
from math import floor

# --- CONFIGURATION (ADJUSTABLE) ---
# Capital & Risk
TOTAL_CAPITAL = 25000
RISK_PER_TRADE_PCT = 0.01
ALLOCATION_PER_TRADE_PCT = 0.25

# Pattern Detection
POLE_LOOKBACK = 10  # Bars
POLE_PCT_MOVE = 0.15  # 15% move to qualify as a pole
CONSOL_MIN_BARS = 4  # Min bars in consolidation
CONSOL_MAX_BARS = 15  # Max bars in consolidation
MAX_RETRACE_PCT = 0.5  # Max 50% retrace of pole
VOLUME_FACTOR = 1.5  # Breakout volume must be 1.5x avg
ATR_PERIOD = 14
ATR_BUFFER_MULT = 1.5
AVG_VOL_PERIOD = 30

# Filters
MIN_MARKET_CAP = 1000 * 10000000  # 1,000 Crores (₹10,000,000,000)
SLIPPAGE_PCT = 0.001  # 0.1%

# --- END CONFIGURATION ---

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


# --- 1. BROKER & DATA FUNCTIONS ---

def get_smartapi_connection():
    """
    Logs into Angel One SmartAPI using environment variables.
    Requires: API_KEY, CLIENT_ID, PIN, TOTP_SECRET
    """
    try:
        api_key = os.environ.get('SMARTAPI_KEY')
        client_id = os.environ.get('SMARTAPI_CLIENT_ID')
        client_pin = os.environ.get('SMARTAPI_PIN')
        totp_secret = os.environ.get('SMARTAPI_TOTP_SECRET')

        if not all([api_key, client_id, client_pin, totp_secret]):
            logging.error("Missing one or more required environment variables for SmartAPI.")
            return None

        smart_conn = SmartConnect(api_key=api_key)
        totp = pyotp.TOTP(totp_secret).now()

        data = {
            "clientcode": client_id,
            "password": client_pin,
            "totp": totp
        }

        session = smart_conn.generateSession(data['clientcode'], data['password'], data['totp'])
        if session['status'] and session['data']['jwtToken']:
            logging.info(f"SmartAPI login successful for {client_id}.")
            smart_conn.setAccessToken(session['data']['jwtToken'])
            smart_conn.setRefreshToken(session['data']['refreshToken'])
            return smart_conn
        else:
            logging.error(f"SmartAPI Login Failed: {session['message']}")
            return None
    except Exception as e:
        logging.error(f"Exception during SmartAPI login: {e}")
        return None


def get_nse_symbols_and_tokens():
    """
    MOCK FUNCTION.
    In a real system, you would download and parse the Angel One
    ScripMaster JSON file to get a list of all NSE-EQ symbols
    and their corresponding 'symboltoken'.

    File URL: https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json

    Returns:
        list[dict]: A list of dicts, e.g.,
        [
            {'symbol': 'RELIANCE-EQ', 'token': '3045', 'yfsymbol': 'RELIANCE.NS'},
            {'symbol': 'TCS-EQ', 'token': '11536', 'yfsymbol': 'TCS.NS'},
            ...
        ]
    """
    logging.warning("Using MOCKED symbol list. Replace with actual ScripMaster logic.")
    # This is a small, representative sample.
    return [
        {'symbol': 'RELIANCE-EQ', 'token': '3045', 'yfsymbol': 'RELIANCE.NS'},
        {'symbol': 'TCS-EQ', 'token': '11536', 'yfsymbol': 'TCS.NS'},
        {'symbol': 'HDFCBANK-EQ', 'token': '1333', 'yfsymbol': 'HDFCBANK.NS'},
        {'symbol': 'INFY-EQ', 'token': '1594', 'yfsymbol': 'INFY.NS'},
        {'symbol': 'ICICIBANK-EQ', 'token': '14977', 'yfsymbol': 'ICICIBANK.NS'},
        {'symbol': 'SBIN-EQ', 'token': '3063', 'yfsymbol': 'SBIN.NS'},
        # Add more symbols for a real scan
    ]


def fetch_historical_data(smart_conn, symbol_token, timeframe):
    """
    Fetches historical data from SmartAPI.
    Timeframe: 'ONE_DAY' or 'FIFTEEN_MINUTE'
    """
    try:
        # We need ~60 days of data for 30-day avg + pattern lookback
        end_date = datetime.now()
        start_date = end_date - timedelta(days=60)

        params = {
            "exchange": "NSE",
            "symboltoken": symbol_token,
            "interval": timeframe,
            "fromdate": start_date.strftime("%Y-%m-%d %H:%M"),
            "todate": end_date.strftime("%Y-%m-%d %H:%M")
        }

        hist_data = smart_conn.historicalData(params)

        if hist_data['status'] and hist_data['data']:
            df = pd.DataFrame(hist_data['data'], columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df.set_index('timestamp', inplace=True)
            # Ensure numeric types
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            return df
        else:
            logging.warning(f"No data returned for token {symbol_token}. Message: {hist_data.get('message')}")
            return pd.DataFrame()

    except Exception as e:
        logging.error(f"Error fetching historical data for {symbol_token}: {e}")
        return pd.DataFrame()


def fetch_market_cap_with_retry(yfsymbol, retries=3, delay=2):
    """
    Fetches market cap from yfinance with retry logic.
    """
    for i in range(retries):
        try:
            ticker = yf.Ticker(yfsymbol)
            mcap = ticker.info.get('marketCap')
            if mcap:
                return mcap
            else:
                logging.warning(f"Could not find marketCap for {yfsymbol}.")
                return None
        except Exception as e:
            logging.warning(f"yfinance failed for {yfsymbol} (Attempt {i + 1}/{retries}): {e}")
            time.sleep(delay)
    return None


# --- 2. STRATEGY & FILTER FUNCTIONS ---

def calculate_indicators(df):
    """Adds ATR and Volume SMA to the DataFrame."""
    df['atr'] = talib.ATR(df['high'], df['low'], df['close'], timeperiod=ATR_PERIOD)
    df['avg_volume'] = df['volume'].rolling(window=AVG_VOL_PERIOD).mean()
    df['avg_turnover'] = (df['close'] * df['volume']).rolling(window=30).mean()
    return df


def detect_flag_pennant(df):
    """
    Heuristic-based pattern detector. Checks if the *latest* bars
    form a valid breakout from a flag/pennant pattern.

    Returns:
        dict with pattern info if a breakout is found, else None.
    """
    if len(df) < (POLE_LOOKBACK + CONSOL_MAX_BARS):
        # Not enough data to check
        return None

    # We check for a pattern ending on the second-to-last bar,
    # with the breakout happening on the *very last bar*.
    last_bar = df.iloc[-1]

    # Iterate backwards to find the end of the pole
    for consol_len in range(CONSOL_MIN_BARS, CONSOL_MAX_BARS + 1):
        # Define consolidation and pole periods
        consol_end_idx = -2  # Second-to-last bar
        consol_start_idx = consol_end_idx - consol_len

        pole_end_idx = consol_start_idx - 1
        pole_start_idx = pole_end_idx - POLE_LOOKBACK

        if pole_start_idx < 0:
            continue  # Not enough data for this lookback

        # 1. Analyze the Flagpole
        pole_data = df.iloc[pole_start_idx: pole_end_idx + 1]
        pole_low = pole_data['low'].min()
        pole_high = pole_data['high'].max()
        pole_move_pct = (pole_high - pole_low) / pole_low

        if pole_move_pct < POLE_PCT_MOVE:
            continue  # Pole isn't strong enough

        # 2. Analyze the Consolidation
        consol_data = df.iloc[consol_start_idx: consol_end_idx + 1]
        consol_high = consol_data['high'].max()
        consol_low = consol_data['low'].min()

        # 3. Check Retracement
        # Retracement should not be more than MAX_RETRACE_PCT
        retrace_level = pole_high - (pole_high - pole_low) * MAX_RETRACE_PCT
        if consol_low < retrace_level:
            continue  # Retraced too far

        # 4. Check Breakout & Volume on *last bar*
        if (last_bar['close'] > consol_high) and \
                (last_bar['volume'] > (last_bar['avg_volume'] * VOLUME_FACTOR)):
            # Found a valid breakout!
            logging.info(f"Pattern Found: Breakout at {last_bar['close']} from consol_high {consol_high}")
            return {
                "pattern_found": True,
                "consolidation_high": consol_high,
                "consolidation_low": consol_low,
                "last_bar": last_bar
            }

    return None  # No pattern found


def check_filters(yfsymbol, df):
    """
    Checks Market Cap and Liquidity filters.
    """
    # 1. Market Cap Filter
    mcap = fetch_market_cap_with_retry(yfsymbol)
    if not mcap or mcap < MIN_MARKET_CAP:
        logging.info(f"Filter FAIL: {yfsymbol} MCap {mcap} < {MIN_MARKET_CAP}")
        return False

    # 2. Liquidity Filter
    # Your position size = ₹6,250. 2x = ₹12,500
    required_turnover = (ALLOCATION_PER_TRADE_PCT * TOTAL_CAPITAL) * 2
    last_avg_turnover = df['avg_turnover'].iloc[-1]

    if last_avg_turnover < required_turnover:
        logging.info(f"Filter FAIL: {yfsymbol} Avg Turnover {last_avg_turnover} < {required_turnover}")
        return False

    logging.info(f"Filters PASS for {yfsymbol} (MCap: {mcap}, Turnover: {last_avg_turnover})")
    return True


def calculate_trade_parameters(pattern_info):
    """
    Calculates Entry, SL, Target, and Quantity based on config.
    """
    last_bar = pattern_info['last_bar']

    entry_price = last_bar['close'] * (1 + SLIPPAGE_PCT)
    stop_loss_price = pattern_info['consolidation_low'] - (last_bar['atr'] * ATR_BUFFER_MULT)

    if stop_loss_price >= entry_price:
        logging.warning("Trade skipped: Calculated SL is at or above entry price.")
        return None

    risk_per_share = entry_price - stop_loss_price
    target_price = entry_price + (risk_per_share * 2)  # 2:1 R:R

    # Position Sizing
    max_risk = TOTAL_CAPITAL * RISK_PER_TRADE_PCT
    max_allocation = TOTAL_CAPITAL * ALLOCATION_PER_TRADE_PCT

    qty_risk_based = floor(max_risk / risk_per_share)
    qty_alloc_based = floor(max_allocation / entry_price)

    final_quantity = min(qty_risk_based, qty_alloc_based)

    if final_quantity <= 0:
        logging.warning(f"Trade skipped: Final quantity is {final_quantity}.")
        return None

    return {
        "entry": round(entry_price, 2),
        "stop_loss": round(stop_loss_price, 2),
        "target": round(target_price, 2),
        "quantity": final_quantity,
        "risk_per_share": round(risk_per_share, 2),
        "position_value": round(final_quantity * entry_price, 2)
    }


# --- 3. EXECUTION FUNCTIONS ---

def place_trade_order(smart_conn, symbol_data, trade_params):
    """
    Formats and places a MARKET order with SmartAPI.
    """
    try:
        order_payload = {
            "variety": "NORMAL",
            "tradingsymbol": symbol_data['symbol'],
            "symboltoken": symbol_data['token'],
            "transactiontype": "BUY",
            "exchange": "NSE",
            "ordertype": "MARKET",  # Buy at market on confirmation
            "producttype": "DELIVERY",  # Swing trade
            "duration": "DAY",
            "quantity": trade_params['quantity']
            # Price is not needed for MARKET order
        }

        logging.info(f"Placing Order: {json.dumps(order_payload, indent=2)}")

        # In a real system, uncomment the following line:
        # order_id = smart_conn.placeOrder(order_payload)
        # logging.info(f"Order placed successfully! Order ID: {order_id}")

        # MOCKING for this example:
        order_id = f"mock_order_{int(time.time())}"
        logging.info(f"MOCK Order placed successfully! Order ID: {order_id}")

        return order_id

    except Exception as e:
        logging.error(f"Error placing order for {symbol_data['symbol']}: {e}")
        return None


# --- 4. MAIN SCANNER LOOP ---

def main_scanner_loop(timeframe):
    """
    The main logic loop to run the entire system.
    timeframe: 'ONE_DAY' or 'FIFTEEN_MINUTE'
    """
    logging.info(f"--- Starting {timeframe} scanner loop ---")

    smart_conn = get_smartapi_connection()
    if not smart_conn:
        logging.error("Exiting: Could not connect to broker.")
        return

    symbols_to_scan = get_nse_symbols_and_tokens()
    all_trades = []

    for symbol_data in symbols_to_scan:
        symbol = symbol_data['symbol']
        token = symbol_data['token']
        yfsymbol = symbol_data['yfsymbol']

        logging.info(f"Scanning {symbol} ({timeframe})...")

        # 1. Fetch Data
        df = fetch_historical_data(smart_conn, token, timeframe)
        if df.empty or len(df) < 50:  # Need 50 bars for MAs/ATR
            logging.warning(f"Skipping {symbol}: Not enough historical data.")
            continue

        # 2. Calculate Indicators
        df = calculate_indicators(df)

        # 3. Check Filters
        if not check_filters(yfsymbol, df):
            continue  # Skips if MCap or Liquidity fails

        # 4. Detect Pattern
        pattern_info = detect_flag_pennant(df)
        if not pattern_info:
            logging.info(f"No breakout pattern found for {symbol}.")
            continue

        # 5. Valid Pattern Found! Calculate Trade
        logging.info(f"*** PATTERN FOUND FOR {symbol} ***")
        trade_params = calculate_trade_parameters(pattern_info)

        if not trade_params:
            logging.warning(f"Skipping {symbol}: Trade params invalid (e.g., qty=0).")
            continue

        # 6. Place Trade
        trade_json = {
            "symbol": symbol,
            "yfsymbol": yfsymbol,
            "token": token,
            "timeframe": timeframe,
            "timestamp": datetime.now().isoformat(),
            "trade_params": trade_params,
            "pattern_info": {
                "consolidation_high": pattern_info['consolidation_high'],
                "consolidation_low": pattern_info['consolidation_low'],
                "breakout_price": pattern_info['last_bar']['close'],
                "breakout_volume": pattern_info['last_bar']['volume'],
                "avg_volume": pattern_info['last_bar']['avg_volume']
            }
        }
        all_trades.append(trade_json)

        # Uncomment to place live trades
        # place_trade_order(smart_conn, symbol_data, trade_params)

    logging.info(f"--- Scanner loop complete. Found {len(all_trades)} trades. ---")
    if all_trades:
        print(json.dumps(all_trades, indent=2))

    return all_trades


if __name__ == "__main__":
    # This block is for direct execution (e.g., local testing or Fargate)
    # For Lambda, the handler in `lambda_function.py` will be used.

    # Example: Run the 15-minute scanner
    # Note: Requires env vars to be set.
    main_scanner_loop(timeframe="FIFTEEN_MINUTE")
# ```
#
# ---
#
# ### **C) AWS Deployment & Execution**
#
# This is how
# you
# run
# the
# `strategy_backbone.py`
# file in a
# real, automated
# AWS
# environment.
#
# #### **Folder Structure**
#
# Your
# project
# should
# be
# organized as follows:
#
# ```text
# / flag - pennant - trader /
# |
# | -- strategy_backbone.py(The
# large
# file
# from Part B)
# |
# | -- requirements.txt(All
# Python
# dependencies)
# | -- README.md(Instructions
# on
# env
# vars, IAM)
# | -- sample_trade.json(Example
# output)
# |
# | --  # For AWS Lambda Deployment
# | `-- lambda_function.py(The
# Lambda
# handler)
# |
# | --  # For AWS Fargate (Docker) Deployment
# | | -- main.py(The
# container
# 's entrypoint)
# | `-- Dockerfile(The
# container
# build - file)
# build - file)