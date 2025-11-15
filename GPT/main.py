import os, time, json, logging
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
import yfinance as yf
from SmartApi.smartConnect import SmartConnect
import pyotp

# Setup logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def login_smartapi():
    """Login to SmartAPI and return SmartConnect object."""
    apikey = os.environ['ANGEL_API_KEY']
    client_id = os.environ['ANGEL_CLIENT_ID']
    password = os.environ['ANGEL_PIN']
    totp_secret = os.environ['ANGEL_TOTP_SECRET']
    smartapi = SmartConnect(api_key=apikey)
    for attempt in range(3):
        try:
            totp = pyotp.TOTP(totp_secret).now()
            data = smartapi.generateSession(client_id, password, totp)
            auth_token = data['data']['jwtToken']
            # Set auth token for further calls
            smartapi.refreshToken = data['data']['refreshToken']
            smartapi.generateToken(data['data']['refreshToken'])
            feed_token = smartapi.getfeedToken()
            logger.info("Logged in to SmartAPI")
            return smartapi
        except Exception as e:
            logger.error(f"Login attempt {attempt + 1} failed: {e}")
            time.sleep(1)
    raise Exception("SmartAPI login failed after retries")


def fetch_candles(smartapi, exchange, symbol_token, interval, start, end):
    """Fetch OHLCV data via SmartAPI. Returns DataFrame."""
    historicParam = {
        "exchange": exchange,
        "symboltoken": str(symbol_token),
        "interval": interval,
        "fromdate": start.strftime("%Y-%m-%d %H:%M"),
        "todate": end.strftime("%Y-%m-%d %H:%M")
    }
    for attempt in range(3):
        try:
            res = smartapi.getCandleData(historicParam)
            data = res['data']
            df = pd.DataFrame(data, columns=['DateTime', 'Open', 'High', 'Low', 'Close', 'Volume'])
            df['DateTime'] = pd.to_datetime(df['DateTime'])
            df.set_index('DateTime', inplace=True)
            return df
        except Exception as e:
            logger.error(f"Candle fetch failed: {e}. Retrying...")
            time.sleep(1)
    logger.error("Failed to fetch candles after retries")
    return None


def detect_flag_pattern(df):
    """
    Detect bullish flag on daily data.
    Returns (breakout_price, stop_price, target_price) or None.
    """
    if len(df) < 10:
        return None
    # Example logic: take last 20 days, find max drawdown period of 3-5 days for flagpole, then 5-10 days consolidation
    arr = df['Close'].values
    # Simplest: identify last rally: find a segment of length >=3 with continuous up moves >3%
    rally_found = False
    for window in [3, 4, 5]:
        if len(arr) < window + 5: break
        if np.all(np.diff(arr[-window - 5:-5]) > 0):
            rally_pct = (arr[-5] - arr[-window - 5]) / arr[-window - 5]
            if rally_pct > 0.05:
                rally_found = True
                pole_start = -window - 5
                pole_end = -5
                break
    if not rally_found:
        return None
    flag_df = df.iloc[pole_end:]
    pole_height = df['Close'].iloc[pole_end] - df['Close'].iloc[pole_start]
    # Consolidation is last 5 bars
    cons_df = df.iloc[pole_end - 5:pole_end]
    cons_high = cons_df['High'].max()
    cons_low = cons_df['Low'].min()
    breakout_price = cons_high
    stop_price = cons_low
    # Volume drop
    if df['Volume'].iloc[pole_start:pole_end].mean() < cons_df['Volume'].mean():
        return None
    target_price = breakout_price + pole_height
    return (breakout_price, stop_price, target_price)


def detect_pennant_pattern(df):
    """
    Detect bullish pennant on daily data.
    Similar to flag but look for narrowing range.
    Returns (breakout_price, stop_price, target_price) or None.
    """
    # This is a simplified check
    if len(df) < 15: return None
    recent = df['Close'][-15:]
    # Check for high followed by lower highs and higher lows (triangle)
    highs = recent.rolling(5).max().dropna()
    lows = recent.rolling(5).min().dropna()
    if highs.iloc[-1] < highs.iloc[-2] and lows.iloc[-1] > lows.iloc[-2]:
        pole = df['Close'][-15:-5]
        if len(pole) == 10 and (pole.iloc[-1] - pole.iloc[0]) > 0:
            pole_height = pole.iloc[-1] - pole.iloc[0]
            cons_df = df.iloc[-5:]
            breakout_price = cons_df['High'].max()
            stop_price = cons_df['Low'].min()
            target_price = breakout_price + pole_height
            # Ensure volume tapering
            if df['Volume'][-15:-5].mean() < df['Volume'][-5:].mean():
                return (breakout_price, stop_price, target_price)
    return None


def get_market_cap(symbol):
    """Fetch market cap via yfinance (in INR)."""
    try:
        ticker = yf.Ticker(symbol + ".NS")
        info = ticker.info
        mcap = info.get('marketCap', 0)
        return mcap
    except Exception as e:
        logger.error(f"yfinance error for {symbol}: {e}")
        return 0


def avg_turnover(df):
    """Compute average turnover (price*volume) from DataFrame."""
    if df is None or len(df) == 0:
        return 0
    return (df['Close'] * df['Volume']).mean()


def calculate_quantity(capital, alloc_pct, risk_pct, price, stop):
    """Compute trade quantity given capital, allocation %, risk %, entry price, stop price."""
    allocation = capital * alloc_pct
    risk_amt = capital * risk_pct
    if price <= 0 or price <= stop:
        return 0
    qty_alloc = allocation / price
    qty_risk = risk_amt / (price - stop)
    qty = int(min(qty_alloc, qty_risk))
    return max(qty, 0)


def place_order(smartapi, symbol, token, price, qty):
    """Place a buy order via SmartAPI (LIMIT, DAY)."""
    orderparams = {
        "variety": "NORMAL",
        "tradingsymbol": symbol,
        "symboltoken": str(token),
        "transactiontype": "BUY",
        "exchange": "NSE",
        "ordertype": "LIMIT",
        "producttype": "MARGIN",
        "duration": "DAY",
        "price": str(round(price, 2)),
        "quantity": str(qty),
        "disclosedqty": "0",
        "triggerprice": "0",
        "stoploss": "0"
    }
    try:
        order_id = smartapi.placeOrder(orderparams)
        logger.info(f"Order placed: {symbol} x{qty} @ {price}, order_id={order_id}")
        return order_id
    except Exception as e:
        logger.error(f"Order failed for {symbol}: {e}")
        return None


def lambda_handler(event, context):
    # Strategy parameters
    CAPITAL = 25000
    ALLOC_PCT = 0.25
    RISK_PCT = 0.01
    SLIPPAGE = 0.001  # 0.1%
    breakout_buffer = 0.001  # extra for breakout
    # Example ticker list (in practice, load Nifty-500 list)
    tickers = ["RELIANCE", "TCS", "INFY"]  # placeholder
    smartapi = login_smartapi()
    trades = []

    # Iterate through stocks
    for symbol in tickers:
        # 1. Market Cap filter
        mcap = get_market_cap(symbol)
        if mcap < 1000e7:  # ₹1000 crore = 1e10 Rs
            logger.info(f"Skipping {symbol}: market cap {mcap} below threshold")
            continue
        # 2. Fetch daily data (last 60 days)
        to_date = datetime.now()
        from_date = to_date - timedelta(days=60)
        # Need symbol token; for demo assume a mapping function or API exists
        # For simplicity, we use a dummy token map:
        symbol_tokens = {"RELIANCE": "2885", "TCS": "2951", "INFY": "1594"}  # example tokens
        token = symbol_tokens.get(symbol)
        if not token:
            logger.error(f"No symbol token for {symbol}")
            continue
        df_daily = fetch_candles(smartapi, "NSE", token, "ONE_DAY", from_date, to_date)
        if df_daily is None: continue

        # 3. Pattern detection
        flag = detect_flag_pattern(df_daily)
        pennant = detect_pennant_pattern(df_daily)
        pattern = None
        if flag:
            breakout_price, stop_price, target_price = flag
            pattern = "Bull_Flag"
        elif pennant:
            breakout_price, stop_price, target_price = pennant
            pattern = "Bull_Pennant"
        else:
            continue  # no pattern

        # 4. Entry check on 15-min chart
        # We assume the pattern high (breakout_price) was on last daily bar
        # Now check if current 15m price >= breakout
        start_intraday = to_date.replace(hour=9, minute=15)  # market open IST
        df_15min = fetch_candles(smartapi, "NSE", token, "FIFTEEN_MINUTE", start_intraday, to_date)
        if df_15min is None or df_15min.empty:
            continue
        last_bar = df_15min.iloc[-1]
        current_close = last_bar['Close']
        current_vol = last_bar['Volume']
        avg_vol = df_15min['Volume'].rolling(10).mean().iloc[-1]
        if current_close < breakout_price * (1 + breakout_buffer):
            continue  # no breakout yet
        if current_vol < avg_vol:
            continue  # no volume confirmation

        entry_price = current_close * (1 + SLIPPAGE)
        stop_loss = stop_price - (df_daily['Close'].rolling(14).std().iloc[-1] or 0)  # subtract ~1*ATR
        if stop_loss >= entry_price:
            continue
        target = max(target_price, entry_price + 2 * (entry_price - stop_loss))

        # 5. Position sizing
        qty = calculate_quantity(CAPITAL, ALLOC_PCT, RISK_PCT, entry_price, stop_loss)
        if qty <= 0:
            continue
        # Liquidity check: 30-day avg turnover
        df_30d = df_daily.tail(30)
        avg_turn = avg_turnover(df_30d)
        if avg_turn < 2 * (entry_price * qty):
            logger.info(f"Skipping {symbol}: low liquidity (avg turn {avg_turn})")
            continue

        # 6. Place order
        order_id = place_order(smartapi, symbol, token, entry_price, qty)
        trade_info = {
            "symbol": symbol,
            "pattern": pattern,
            "entry": round(entry_price, 2),
            "stop_loss": round(stop_loss, 2),
            "target": round(target, 2),
            "quantity": qty,
            "allocation_value": round(entry_price * qty, 2),
            "risk_value": round((entry_price - stop_loss) * qty, 2),
            "order_id": order_id,
            "timestamp": datetime.now().isoformat()
        }
        trades.append(trade_info)

    logger.info(f"Trades executed: {json.dumps(trades)}")
    return {"statusCode": 200, "body": trades}
