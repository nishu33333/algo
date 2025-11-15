# Usage Examples & Configuration Guide

## 🎯 Basic Usage Examples

### Example 1: Run with Default Settings

```python
from flag_pennant_trading_system import (
    AngelOneClient, TradingConfig, TradingSystem
)

# Initialize
angel_client = AngelOneClient(
    api_key="your_key",
    client_id="your_id",
    password="your_password",
    totp_secret="your_secret"
)

# Login
angel_client.login()

# Create trading system
config = TradingConfig()
trading_system = TradingSystem(angel_client, config)

# Scan single stock
signal = trading_system.scan_stock('RELIANCE', '2885')

if signal:
    # Execute trade (dry run)
    result = trading_system.execute_trade(signal, dry_run=True)
    print(result)
```

### Example 2: Custom Configuration

```python
class MyConfig(TradingConfig):
    # Conservative settings
    TOTAL_CAPITAL = 50000
    ALLOCATION_PER_TRADE = 0.20  # 20% per trade
    RISK_PER_TRADE = 0.005  # 0.5% risk
    REWARD_RISK_RATIO = 3.0  # Target 3:1
    
    # More strict pattern detection
    MIN_FLAGPOLE_GAIN = 0.07  # 7% minimum
    CONSOLIDATION_DAYS_MAX = 10
    VOLUME_BREAKOUT_MULTIPLIER = 2.0

# Use custom config
trading_system = TradingSystem(angel_client, MyConfig())
```

### Example 3: Scan Multiple Stocks

```python
watchlist = [
    {'symbol': 'RELIANCE', 'token': '2885'},
    {'symbol': 'TCS', 'token': '11536'},
    {'symbol': 'INFY', 'token': '1594'},
    {'symbol': 'HDFCBANK', 'token': '1333'},
    {'symbol': 'ICICIBANK', 'token': '4963'}
]

results = trading_system.scan_watchlist(watchlist, dry_run=True)

for result in results:
    signal = result['trade_signal']
    print(f"{signal['symbol']}: {signal['pattern_type']} "
          f"Entry={signal['entry_price']} Target={signal['target']}")
```

### Example 4: Schedule Daily Scans (Linux Cron)

```bash
# Add to crontab (crontab -e)
# Run every day at 9:30 AM
30 9 * * 1-5 cd /home/user/flag-pennant-trading && python flag_pennant_trading_system.py >> /var/log/trading.log 2>&1
```

---

## 🔧 Advanced Configuration

### Pattern Detection Tuning

```python
class AggressiveConfig(TradingConfig):
    """For more frequent signals"""
    MIN_FLAGPOLE_GAIN = 0.03  # 3% minimum (lower threshold)
    FLAGPOLE_DAYS_MIN = 2
    CONSOLIDATION_DAYS_MAX = 20  # Longer consolidations allowed
    VOLUME_BREAKOUT_MULTIPLIER = 1.3  # Less strict volume
    ATR_SL_MULTIPLIER = 0.3  # Tighter stops

class ConservativeConfig(TradingConfig):
    """For higher quality signals"""
    MIN_FLAGPOLE_GAIN = 0.08  # 8% minimum (higher threshold)
    FLAGPOLE_DAYS_MIN = 4
    CONSOLIDATION_DAYS_MAX = 8  # Shorter consolidations
    VOLUME_BREAKOUT_MULTIPLIER = 2.0  # Strict volume
    ATR_SL_MULTIPLIER = 0.7  # Wider stops
```

### Position Sizing Strategies

```python
# Fixed Quantity (for testing)
class FixedQuantityConfig(TradingConfig):
    def calculate_position_size(self, entry, stop_loss):
        return {
            'quantity': 1,  # Always 1 share
            'entry_with_slippage': entry * 1.001,
            'stop_loss': stop_loss,
            'target': entry + 2 * (entry - stop_loss)
        }

# Kelly Criterion (advanced)
class KellyConfig(TradingConfig):
    WIN_RATE = 0.55  # Historical win rate
    
    def calculate_position_size(self, entry, stop_loss):
        avg_win = self.REWARD_RISK_RATIO
        avg_loss = 1
        kelly_fraction = (self.WIN_RATE * avg_win - (1 - self.WIN_RATE) * avg_loss) / avg_win
        kelly_fraction = min(kelly_fraction, 0.25)  # Cap at 25%
        
        allocation = self.TOTAL_CAPITAL * kelly_fraction
        quantity = int(allocation / entry)
        
        return {
            'quantity': quantity,
            'entry_with_slippage': entry * 1.001,
            'stop_loss': stop_loss,
            'target': entry + self.REWARD_RISK_RATIO * (entry - stop_loss)
        }
```

---

## 📊 Custom Pattern Detection

### Add New Pattern: Ascending Triangle

```python
from flag_pennant_trading_system import PatternDetector

class CustomPatternDetector(PatternDetector):
    
    @staticmethod
    def detect_ascending_triangle(df, config):
        """
        Detect ascending triangle pattern
        - Flat resistance (horizontal)
        - Rising support (ascending trendline)
        """
        if len(df) < 15:
            return None
        
        recent_data = df.iloc[-15:]
        
        # Check for flat resistance
        highs = recent_data['high'].values
        resistance = highs.max()
        resistance_count = sum(abs(h - resistance) / resistance < 0.01 for h in highs)
        
        if resistance_count < 3:
            return None
        
        # Check for rising lows
        lows = recent_data['low'].values
        if not all(lows[i] >= lows[i-1] - 5 for i in range(1, len(lows))):
            return None
        
        # Breakout check
        current_price = df.iloc[-1]['close']
        current_volume = df.iloc[-1]['volume']
        avg_volume = df.iloc[-20:]['volume'].mean()
        
        if (current_price > resistance and 
            current_volume > avg_volume * config.VOLUME_BREAKOUT_MULTIPLIER):
            
            return {
                'type': 'ASCENDING_TRIANGLE',
                'resistance': resistance,
                'support_slope': 'rising',
                'breakout_price': current_price
            }
        
        return None
```

---

## 🎨 Custom Filters

### Add Momentum Filter

```python
from flag_pennant_trading_system import MarketFilter

class MomentumFilter(MarketFilter):
    
    @staticmethod
    def check_rsi(df, period=14, oversold=30, overbought=70):
        """Check if RSI is in favorable zone"""
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        current_rsi = rsi.iloc[-1]
        
        # For long positions, prefer RSI > 50 but < 70
        return 50 < current_rsi < overbought
    
    @staticmethod
    def check_macd(df):
        """Check if MACD shows bullish momentum"""
        exp1 = df['close'].ewm(span=12, adjust=False).mean()
        exp2 = df['close'].ewm(span=26, adjust=False).mean()
        macd = exp1 - exp2
        signal = macd.ewm(span=9, adjust=False).mean()
        
        # MACD should be above signal line
        return macd.iloc[-1] > signal.iloc[-1]

# Apply filters
if not MomentumFilter.check_rsi(df):
    print("Failed RSI filter")
    
if not MomentumFilter.check_macd(df):
    print("Failed MACD filter")
```

### Add Sector Filter

```python
class SectorFilter:
    
    # Define sector-wise market cap thresholds
    SECTOR_MIN_MARKET_CAP = {
        'IT': 5000,  # IT stocks need 5000 Cr
        'Banking': 10000,  # Banks need 10000 Cr
        'Pharma': 3000,
        'Auto': 5000,
        'Default': 1000
    }
    
    @staticmethod
    def get_sector(symbol):
        """Get sector for a symbol (simplified)"""
        it_stocks = ['TCS', 'INFY', 'WIPRO', 'HCLTECH', 'TECHM']
        banking_stocks = ['HDFCBANK', 'ICICIBANK', 'SBIN', 'AXISBANK', 'KOTAKBANK']
        pharma_stocks = ['SUNPHARMA', 'DRREDDY', 'CIPLA']
        
        if symbol in it_stocks:
            return 'IT'
        elif symbol in banking_stocks:
            return 'Banking'
        elif symbol in pharma_stocks:
            return 'Pharma'
        else:
            return 'Default'
    
    @classmethod
    def check_sector_filter(cls, symbol, market_cap):
        """Apply sector-specific filters"""
        sector = cls.get_sector(symbol)
        min_cap = cls.SECTOR_MIN_MARKET_CAP.get(sector, 1000)
        
        return market_cap >= min_cap
```

---

## 🔔 Notifications

### Email Notifications

```python
import smtplib
from email.mime.text import MIMEText

def send_email_alert(trade_signal):
    """Send email notification for new signal"""
    msg = MIMEText(f"""
    New Trading Signal!
    
    Symbol: {trade_signal['symbol']}
    Pattern: {trade_signal['pattern_type']}
    Entry: ₹{trade_signal['entry_price']}
    Target: ₹{trade_signal['target']}
    Stop Loss: ₹{trade_signal['stop_loss']}
    Quantity: {trade_signal['quantity']}
    Risk: ₹{trade_signal['risk_amount']}
    """)
    
    msg['Subject'] = f"Trading Signal: {trade_signal['symbol']}"
    msg['From'] = "trading@example.com"
    msg['To'] = "your@email.com"
    
    with smtplib.SMTP('smtp.gmail.com', 587) as server:
        server.starttls()
        server.login("trading@example.com", "your_password")
        server.send_message(msg)
```

### Telegram Notifications

```python
import requests

def send_telegram_alert(trade_signal):
    """Send Telegram notification"""
    bot_token = "YOUR_BOT_TOKEN"
    chat_id = "YOUR_CHAT_ID"
    
    message = f"""
🚀 *New Trading Signal*

📊 Symbol: `{trade_signal['symbol']}`
📈 Pattern: {trade_signal['pattern_type']}
💰 Entry: ₹{trade_signal['entry_price']}
🎯 Target: ₹{trade_signal['target']}
🛑 Stop Loss: ₹{trade_signal['stop_loss']}
📦 Quantity: {trade_signal['quantity']}
⚠️ Risk: ₹{trade_signal['risk_amount']}
    """
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }
    
    requests.post(url, data=data)
```

### Slack Notifications

```python
import requests

def send_slack_alert(trade_signal):
    """Send Slack notification"""
    webhook_url = "YOUR_SLACK_WEBHOOK_URL"
    
    message = {
        "text": f"New Trading Signal: {trade_signal['symbol']}",
        "attachments": [
            {
                "color": "good",
                "fields": [
                    {"title": "Pattern", "value": trade_signal['pattern_type'], "short": True},
                    {"title": "Entry", "value": f"₹{trade_signal['entry_price']}", "short": True},
                    {"title": "Target", "value": f"₹{trade_signal['target']}", "short": True},
                    {"title": "Stop Loss", "value": f"₹{trade_signal['stop_loss']}", "short": True}
                ]
            }
        ]
    }
    
    requests.post(webhook_url, json=message)
```

---

## 📈 Performance Tracking

### Log Trades to CSV

```python
import csv
from datetime import datetime

def log_trade_to_csv(trade_signal, result):
    """Log all trades to CSV for analysis"""
    with open('trades.csv', 'a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            datetime.now().isoformat(),
            trade_signal['symbol'],
            trade_signal['pattern_type'],
            trade_signal['entry_price'],
            trade_signal['stop_loss'],
            trade_signal['target'],
            trade_signal['quantity'],
            trade_signal['risk_amount'],
            result.get('order_id', 'N/A')
        ])
```

### Calculate Performance Metrics

```python
import pandas as pd

def calculate_performance():
    """Calculate trading performance from logs"""
    df = pd.read_csv('trades.csv', 
                     names=['timestamp', 'symbol', 'pattern', 'entry', 
                            'sl', 'target', 'qty', 'risk', 'order_id'])
    
    # Add your exit prices manually or via API
    df['exit_price'] = None  # Fill this
    df['profit_loss'] = (df['exit_price'] - df['entry']) * df['qty']
    
    print(f"Total Trades: {len(df)}")
    print(f"Win Rate: {(df['profit_loss'] > 0).sum() / len(df) * 100:.2f}%")
    print(f"Average Profit: ₹{df[df['profit_loss'] > 0]['profit_loss'].mean():.2f}")
    print(f"Average Loss: ₹{df[df['profit_loss'] < 0]['profit_loss'].mean():.2f}")
    print(f"Total P&L: ₹{df['profit_loss'].sum():.2f}")
```

---

## 🧪 Backtesting Example

```python
def backtest_strategy(symbol, start_date, end_date):
    """
    Simple backtesting framework
    """
    # Fetch historical data
    import yfinance as yf
    ticker = yf.Ticker(f"{symbol}.NS")
    df = ticker.history(start=start_date, end=end_date)
    df.columns = [c.lower() for c in df.columns]
    
    trades = []
    capital = 25000
    
    # Rolling window simulation
    for i in range(30, len(df)):
        window = df.iloc[i-30:i+1]
        
        # Detect pattern
        patterns = PatternDetector.detect_patterns(window, TradingConfig())
        
        if patterns:
            pattern = patterns[0]
            
            # Simulate entry
            entry = pattern['breakout_price']
            sl = pattern['stop_loss']
            target = entry + 2 * (entry - sl)
            
            # Look ahead to see result (this is simplified)
            future_data = df.iloc[i+1:i+6]  # Next 5 days
            
            hit_target = (future_data['high'] >= target).any()
            hit_sl = (future_data['low'] <= sl).any()
            
            if hit_sl:
                pnl = sl - entry
            elif hit_target:
                pnl = target - entry
            else:
                pnl = future_data.iloc[-1]['close'] - entry
            
            trades.append({
                'date': df.index[i],
                'entry': entry,
                'sl': sl,
                'target': target,
                'pnl': pnl
            })
    
    # Calculate metrics
    trades_df = pd.DataFrame(trades)
    print(f"\nBacktest Results for {symbol}")
    print(f"Period: {start_date} to {end_date}")
    print(f"Total Signals: {len(trades_df)}")
    print(f"Win Rate: {(trades_df['pnl'] > 0).sum() / len(trades_df) * 100:.2f}%")
    print(f"Avg Win: ₹{trades_df[trades_df['pnl'] > 0]['pnl'].mean():.2f}")
    print(f"Avg Loss: ₹{trades_df[trades_df['pnl'] < 0]['pnl'].mean():.2f}")
    
    return trades_df

# Run backtest
results = backtest_strategy('RELIANCE', '2024-01-01', '2025-11-15')
```

---

## 🔄 Error Handling Examples

```python
from tenacity import retry, stop_after_attempt, wait_exponential

class RobustTradingSystem(TradingSystem):
    
    @retry(stop=stop_after_attempt(3), 
           wait=wait_exponential(multiplier=1, min=2, max=10))
    def safe_scan_stock(self, symbol, token):
        """Scan with automatic retry on failure"""
        try:
            return self.scan_stock(symbol, token)
        except Exception as e:
            logger.error(f"Error scanning {symbol}: {e}")
            raise
    
    def scan_watchlist_with_timeout(self, watchlist, timeout=300):
        """Scan with timeout protection"""
        import signal
        
        def timeout_handler(signum, frame):
            raise TimeoutError("Scan timeout exceeded")
        
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(timeout)
        
        try:
            results = self.scan_watchlist(watchlist)
            signal.alarm(0)  # Cancel alarm
            return results
        except TimeoutError:
            logger.error("Scan timed out")
            return []
```

---

## 📱 Mobile Dashboard (Flask Example)

```python
from flask import Flask, jsonify, render_template

app = Flask(__name__)

@app.route('/api/signals')
def get_signals():
    """API endpoint for current signals"""
    # Load latest signals from database/file
    signals = load_latest_signals()
    return jsonify(signals)

@app.route('/')
def dashboard():
    """Simple web dashboard"""
    return render_template('dashboard.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
```

---

## 💡 Tips & Best Practices

### 1. Start Small
```python
# Begin with paper trading
dry_run = True
capital = 10000  # Virtual capital
```

### 2. Diversify Timeframes
```python
# Scan multiple timeframes
daily_signal = scan_stock(symbol, token, 'ONE_DAY')
intraday_signal = scan_stock(symbol, token, 'FIFTEEN_MINUTE')

# Only trade if both align
if daily_signal and intraday_signal:
    execute_trade(daily_signal)
```

### 3. Use Stop Loss Orders
```python
# Always place protective stops
def place_trade_with_sl(signal):
    # Main order
    buy_order = place_order(signal)
    
    # Immediate SL order
    sl_order = place_order(
        symbol=signal['symbol'],
        order_type='SL',
        trigger_price=signal['stop_loss'],
        transaction_type='SELL'
    )
```

### 4. Keep Records
```python
# Maintain detailed trade journal
journal_entry = {
    'date': datetime.now(),
    'symbol': signal['symbol'],
    'entry_reason': 'Flag breakout with volume',
    'emotions': 'Calm, confident',
    'market_conditions': 'Bullish trend',
    'lessons_learned': ''  # Fill after trade
}
```

### 5. Review Regularly
```python
# Weekly performance review
def weekly_review():
    trades = load_trades_for_week()
    
    print(f"Trades this week: {len(trades)}")
    print(f"Win rate: {calculate_win_rate(trades)}%")
    print(f"Best trade: {get_best_trade(trades)}")
    print(f"Worst trade: {get_worst_trade(trades)}")
    print(f"Lessons learned: {collect_lessons(trades)}")
```

---

**Remember: Consistent profitability comes from discipline, not frequency! 🎯**
