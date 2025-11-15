# flag_pennant_bot.py
"""
Simple swing bot:
- Detects simple flag & pennant patterns on daily/15m data
- Applies market-cap filter (> INR 1,000 crore) via yfinance
- Liquidity check: avg turnover (30d) >= 2x position_value
- Position sizing: capital 25000, allocation_pct 0.25 -> position_value = 6250
- Uses SmartAPI (angel-one/smartapi-python) to place orders
"""

import math
import time
import pandas as pd
import numpy as np
import yfinance as yf
from smartapi import SmartConnect   # from smartapi-python SDK
import requests
from ta.volatility import AverageTrueRange

# ------------- CONFIG ----------------
SMARTAPI_API_KEY = "YOUR_SMARTAPI_API_KEY"
CLIENT_CODE = "YOUR_CLIENT_CODE"
PASSWORD = "YOUR_PASSWORD"   # or use TOTP flow as per docs
CAPITAL = 25000
ALLOCATION_PCT = 0.25
MAX_RISK_PCT = 0.01   # max risk per trade of total capital (1% => 250 INR)
LIQUIDITY_MULTIPLIER = 2.0
MARKETCAP_THRESHOLD = 1000 * 1e7  # ₹1,000 crore = 1,000 * 10^7 rupees
# (since marketcap from yfinance is in INR for Indian tickers? verify)

# ------------- HELPERS ----------------
def get_marketcap_yahoo(ticker):
    """Ticker must be Yahoo-style like 'RELIANCE.NS' or 'TCS.NS'."""
    try:
        tk = yf.Ticker(ticker)
        info = tk.info
        return info.get("marketCap", None)
    except Exception as e:
        print("yfinance error:", e)
        return None

def avg_turnover(df, lookback=30):
    # df must have 'Close' and 'Volume'
    df2 = df.tail(lookback)
    return (df2['Close'] * df2['Volume']).mean()

def atr_series(df, n=14):
    atr = AverageTrueRange(high=df['High'], low=df['Low'], close=df['Close'], window=n)
    return atr.average_true_range()

# naive flag detection
def detect_flag(df):
    """
    Return dict or None.
    Simple approach:
    - Look for a run-up (flagpole): compare current price to price N bars back
    - Then a small downward/upward channel of limited height & length
    - This is heuristic and will generate false positives.
    """
    out = None
    N_pole = 10  # lookback for pole
    if len(df) < N_pole + 5:
        return None
    close = df['Close']
    curr = close.iloc[-1]
    base = close.iloc[-(N_pole+1)]
    pole_mag = (curr - base) / base
    # require at least 10% move as pole (tweakable)
    if pole_mag > 0.10:
        # check consolidation: last 6 bars have low range relative to pole
        cons = df.tail(6)
        cons_range = (cons['High'].max() - cons['Low'].min()) / base
        if cons_range < 0.05:
            out = {
                "pattern": "flag",
                "pole_pct": pole_mag,
                "cons_range": cons_range,
                "entry_hint": cons['High'].max()  # breakout above consolidation
            }
    return out

# naive pennant detection
def detect_pennant(df):
    """
    Detects contracting range: successive lower highs & higher lows over last 6 bars.
    """
    out = None
    window = 8
    if len(df) < window:
        return None
    seg = df.tail(window)
    highs = seg['High'].values
    lows = seg['Low'].values
    # crude test: highs trend down, lows trend up, and range contracting
    highs_lin = np.polyfit(range(window), highs, 1)[0]
    lows_lin = np.polyfit(range(window), lows, 1)[0]
    range_now = highs.max() - lows.min()
    range_earlier = (seg.head(window//2)['High'].max() - seg.head(window//2)['Low'].min())
    if highs_lin < 0 and lows_lin > 0 and range_now < 0.7 * range_earlier:
        out = {
            "pattern": "pennant",
            "highs_slope": highs_lin,
            "lows_slope": lows_lin,
            "entry_hint": seg['High'].max()
        }
    return out

def compute_position_size(entry_price, stop_price, capital=CAPITAL, allocation_pct=ALLOCATION_PCT):
    allocation = capital * allocation_pct
    risk_per_share = abs(entry_price - stop_price)
    if risk_per_share <= 0:
        return 0, allocation
    max_risk_amount = capital * MAX_RISK_PCT
    # prefer to enforce both risk per trade cap and allocation cap:
    qty_by_risk = math.floor(max_risk_amount / risk_per_share)
    qty_by_alloc = math.floor(allocation / entry_price)
    qty = min(qty_by_risk, qty_by_alloc)
    return int(qty), allocation

# ------------- SmartAPI helpers ----------------
def login_smartapi(api_key, client_code, password):
    obj = SmartConnect(api_key=api_key)
    # Example login flow: create session; SmartAPI might have fed_token / session token flow
    data = obj.generateSession(client_code, password)  # adjust if totp required
    access_token = data.get("data", {}).get("jwtToken")
    obj.set_session_token(access_token)
    return obj

def place_market_order(api_obj, tradingsymbol, exchange, transaction_type, quantity, price=None):
    # sample order params - check SDK docs for exact param names & required fields
    orderparams = {
        "variety": "NORMAL",
        "tradingsymbol": tradingsymbol,
        "symboltoken": api_obj.getscripToken(tradingsymbol),  # pseudo-method
        "transactiontype": transaction_type,  # BUY or SELL
        "exchange": exchange,
        "ordertype": "MARKET" if price is None else "LIMIT",
        "producttype": "INTRADAY",  # or CNC for delivery
        "duration": "DAY",
        "price": price or 0,
        "quantity": str(quantity),
    }
    return api_obj.placeOrder(orderparams)

# ------------- Main flow ----------------
def analyze_and_place(symbol_yahoo, smartapi_symbol_token):
    # 1) marketcap
    mc = get_marketcap_yahoo(symbol_yahoo)
    if mc is None or mc < MARKETCAP_THRESHOLD:
        print(symbol_yahoo, "skipped due marketcap", mc)
        return None
    # 2) fetch historical OHLC via SmartAPI historical endpoint or yfinance for speed (here using yfinance)
    tk = yf.Ticker(symbol_yahoo)
    df = tk.history(period="120d", interval="1d").reset_index()
    if df.empty:
        print("no data")
        return None
    df.rename(columns={"Date":"Datetime"}, inplace=True)
    # compute ATR
    df['ATR'] = atr_series(df)
    pattern = detect_flag(df) or detect_pennant(df)
    if not pattern:
        print(symbol_yahoo, "no pattern")
        return None
    # use entry hint
    entry_hint = pattern['entry_hint']
    # suggested entry: breakout price = entry_hint * (1 + 0.002)  # 0.2% buffer
    entry_price = entry_hint * 1.002
    # stop: use consolidation low minus ATR*1.2 (simple)
    atr_now = df['ATR'].iloc[-1]
    stop_price = df['Low'].tail(6).min() - 1.2 * atr_now
    qty, allocation = compute_position_size(entry_price, stop_price)
    if qty <= 0:
        print("qty zero -> risk too big or allocation too small")
        return None
    # Liquidity check
    turnover = avg_turnover(df)
    if turnover < allocation * LIQUIDITY_MULTIPLIER:
        print("low liquidity. turnover:", turnover, "needed:", allocation * LIQUIDITY_MULTIPLIER)
        return None
    # target example: 2x reward:risk
    reward = entry_price - stop_price
    target = entry_price + 2 * reward
    signal = {
        "symbol": symbol_yahoo,
        "pattern": pattern['pattern'],
        "entry_price": round(entry_price,2),
        "stop_price": round(stop_price,2),
        "target": round(target,2),
        "qty": qty,
        "allocation": allocation,
        "marketcap": mc,
        "turnover": turnover
    }
    print("Signal:", signal)
    # DO NOT auto-place in this demo. If you want to place:
    # result = place_market_order(api_obj, tradingsymbol=..., exchange="NSE", transaction_type="BUY", quantity=qty)
    return signal

# Example runner
if __name__=="__main__":
    # login (demo)
    # api = login_smartapi(SMARTAPI_API_KEY, CLIENT_CODE, PASSWORD)
    # for demo, use a shortlist of symbols (Yahoo tickers)
    symbols = ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS"]  # replace with screening step to build universe
    results = []
    for s in symbols:
        try:
            r = analyze_and_place(s, None)
            if r:
                results.append(r)
        except Exception as e:
            print("error", s, e)
    print("Done. signals:", results)
