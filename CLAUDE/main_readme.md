# 🚀 Flag & Pennant Swing Trading System

A fully automated swing trading system that detects and trades **Bullish Flag** and **Bullish Pennant** continuation patterns in NSE equities using Angel One SmartAPI.

## 📊 Strategy Overview

### Pattern Detection
- **Bullish Flag**: Strong upward move followed by parallel downward consolidation
- **Bullish Pennant**: Strong upward move followed by converging triangle consolidation
- **Timeframe**: Daily charts
- **Volume Confirmation**: Breakout must be accompanied by 1.5x average volume

### Entry & Exit Rules
```
Entry:     Breakout above consolidation high (with 0.1% slippage)
Stop Loss: Consolidation low - (ATR × 0.5)
Target:    Entry + 2× (Entry - Stop Loss)  [2:1 Reward:Risk]
```

### Risk Management
- **Total Capital**: ₹25,000
- **Position Size**: Max 25% per trade (₹6,250)
- **Risk per Trade**: Max 1% (₹250)
- **Position Sizing**: `min(risk_based_qty, allocation_based_qty)`

### Filters
- ✅ Market Cap > ₹1,000 Crores
- ✅ 30-day avg turnover ≥ 2× position size
- ✅ Volume confirmation on breakout

---

## 📁 Project Structure

```
flag-pennant-trading/
├── flag_pennant_trading_system.py    # Core trading engine
├── lambda_handler.py                 # AWS Lambda entry point
├── fargate_runner.py                 # AWS Fargate runner
├── Dockerfile                        # Container definition
├── requirements.txt                  # Python dependencies
├── .env.example                      # Environment variables template
├── README.md                         # This file
├── AWS_DEPLOYMENT_GUIDE.md          # Detailed AWS setup guide
├── sample_trade_output.json         # Example output
├── lambda_deploy.sh                 # Lambda deployment script
└── fargate_deploy.sh                # Fargate deployment script
```

---

## 🔧 Quick Start

### 1. Clone Repository

```bash
git clone https://github.com/yourusername/flag-pennant-trading.git
cd flag-pennant-trading
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Credentials

```bash
cp .env.example .env
# Edit .env with your Angel One credentials
```

### 4. Run Locally (Dry Run)

```bash
# Set environment variables
export ANGEL_API_KEY="your_key"
export ANGEL_CLIENT_ID="your_id"
export ANGEL_PASSWORD="your_password"
export ANGEL_TOTP_SECRET="your_secret"

# Run the system
python flag_pennant_trading_system.py
```

---

## 🏗️ How It Works

### Pattern Detection Algorithm

```python
# 1. Detect Flagpole
- Scan for 5%+ gain in 3-8 days
- Verify volume increase during flagpole

# 2. Detect Consolidation
- Flag: Parallel downward channel (3-15 days)
- Pennant: Converging triangle (3-15 days)
- Verify volume decrease during consolidation

# 3. Confirm Breakout
- Price breaks above consolidation high
- Volume > 1.5× 20-day average
- Calculate ATR for stop loss

# 4. Apply Filters
- Check market cap (yfinance)
- Verify liquidity (30-day turnover)

# 5. Calculate Position Size
risk_per_share = entry - stop_loss
qty_risk = max_risk / risk_per_share
qty_allocation = max_allocation / entry
quantity = min(qty_risk, qty_allocation)

# 6. Place Order
- Entry: Limit order at breakout + slippage
- Stop Loss: Below consolidation - ATR buffer
- Target: 2× reward-to-risk ratio
```

### Mathematical Formulas

**Position Sizing:**
```
Max Allocation = ₹25,000 × 0.25 = ₹6,250
Max Risk = ₹25,000 × 0.01 = ₹250

Risk per Share = Entry Price - Stop Loss
Qty (Risk-based) = ₹250 / Risk per Share
Qty (Allocation-based) = ₹6,250 / Entry Price

Final Quantity = min(Qty_risk, Qty_allocation)
```

**Stop Loss Calculation:**
```
ATR(14) = Average True Range over 14 periods
Stop Loss = Consolidation Low - (ATR × 0.5)
```

**Target Calculation:**
```
Risk = Entry - Stop Loss
Target = Entry + (2 × Risk)
```

---

## 🌐 AWS Deployment

### Option 1: AWS Lambda (Serverless)

**Advantages:**
- No server management
- Pay per execution
- Easy to set up
- Scales automatically

**Deploy:**
```bash
chmod +x lambda_deploy.sh
./lambda_deploy.sh
```

**Schedule:** Runs daily at 9:30 AM IST via CloudWatch Events

**Cost:** ~$0.50/month (assuming daily execution)

### Option 2: AWS Fargate (Containerized)

**Advantages:**
- More control
- Better for longer-running tasks
- Isolated environment
- Docker-based

**Deploy:**
```bash
chmod +x fargate_deploy.sh
./fargate_deploy.sh
```

**Schedule:** Runs daily at 9:30 AM IST via EventBridge

**Cost:** ~$1.50/month (assuming daily 5-minute runs)

**Full Setup Guide:** See [AWS_DEPLOYMENT_GUIDE.md](AWS_DEPLOYMENT_GUIDE.md)

---

## 📊 Sample Output

```json
{
  "status": "DRY_RUN",
  "trade_signal": {
    "symbol": "RELIANCE",
    "pattern_type": "FLAG",
    "entry_price": 2459.20,
    "stop_loss": 2398.50,
    "target": 2580.40,
    "quantity": 4,
    "allocation": 9836.80,
    "risk_amount": 242.80,
    "risk_percentage": 0.97,
    "reward_risk_ratio": 2.0
  }
}
```

See [sample_trade_output.json](sample_trade_output.json) for complete example.

---

## 🔍 Monitoring

### View Logs

**Lambda:**
```bash
aws logs tail /aws/lambda/flag-pennant-trading --follow
```

**Fargate:**
```bash
aws logs tail /ecs/flag-pennant-trading --follow
```

### CloudWatch Metrics

- Lambda executions
- Error rates
- Execution duration
- Signal generation rate

### Alerts

Set up SNS notifications for:
- Execution failures
- Order placement errors
- Pattern detection anomalies

---

## ⚙️ Configuration

### Adjustable Parameters

Edit `TradingConfig` class in `flag_pennant_trading_system.py`:

```python
class TradingConfig:
    TOTAL_CAPITAL = 25000
    ALLOCATION_PER_TRADE = 0.25  # 25%
    RISK_PER_TRADE = 0.01  # 1%
    MIN_MARKET_CAP = 1000  # Crores
    
    # Pattern parameters
    MIN_FLAGPOLE_GAIN = 0.05  # 5%
    FLAGPOLE_DAYS_MIN = 3
    FLAGPOLE_DAYS_MAX = 8
    CONSOLIDATION_DAYS_MIN = 3
    CONSOLIDATION_DAYS_MAX = 15
    
    # Risk parameters
    REWARD_RISK_RATIO = 2.0
    ATR_SL_MULTIPLIER = 0.5
    SLIPPAGE = 0.001  # 0.1%
```

### Watchlist

Modify watchlist in `fargate_runner.py` or pass custom watchlist to Lambda:

```python
watchlist = [
    {'symbol': 'RELIANCE', 'token': '2885'},
    {'symbol': 'TCS', 'token': '11536'},
    {'symbol': 'INFY', 'token': '1594'},
    # Add more symbols...
]
```

---

## 🧪 Testing

### Unit Tests

```bash
# Run all tests
pytest tests/

# Run specific test
pytest tests/test_patterns.py -v

# With coverage
pytest --cov=flag_pennant_trading_system tests/
```

### Backtesting

```python
# Test on historical data
from flag_pennant_trading_system import PatternDetector
import pandas as pd

# Load historical data
df = pd.read_csv('historical_data.csv')

# Detect patterns
patterns = PatternDetector.detect_patterns(df, config)
```

### Dry Run Testing

Always test with `dry_run=True` before live trading:

```python
# In lambda_handler.py or fargate_runner.py
results = trading_system.scan_watchlist(watchlist, dry_run=True)
```

---

## 📈 Performance Tracking

### Key Metrics to Monitor

1. **Win Rate**: % of profitable trades
2. **Average R:R**: Actual reward-to-risk ratio
3. **Maximum Drawdown**: Largest peak-to-trough decline
4. **Sharpe Ratio**: Risk-adjusted returns
5. **Signal Quality**: % of signals that meet all filters

### Logging Trades

All trades are logged with:
- Entry price and time
- Stop loss and target levels
- Position size and risk
- Pattern details
- Market filters status

---

## 🔐 Security Best Practices

### Credentials Management

**❌ Never:**
- Commit credentials to Git
- Hardcode API keys in code
- Share credentials publicly

**✅ Always:**
- Use environment variables
- Store secrets in AWS Secrets Manager
- Rotate credentials regularly
- Use IAM roles with minimal permissions

### AWS Security

```bash
# Use AWS Secrets Manager
aws secretsmanager create-secret \
  --name angel-one-credentials \
  --secret-string '{"api_key":"xxx","client_id":"xxx",...}'

# Grant Lambda access
aws iam attach-role-policy \
  --role-name FlagPennantTradingLambdaRole \
  --policy-arn arn:aws:iam::aws:policy/SecretsManagerReadWrite
```

---

## 🐛 Troubleshooting

### Common Issues

**1. Login Failed**
```
Error: Invalid TOTP
Solution: Verify TOTP secret is correct and system time is synchronized
```

**2. No Historical Data**
```
Error: Insufficient data
Solution: Check symbol token is correct and Angel One API is accessible
```

**3. Position Size = 0**
```
Error: Quantity too small
Solution: Increase capital or reduce stop loss distance
```

**4. Lambda Timeout**
```
Error: Task timed out after 300 seconds
Solution: Increase timeout or reduce watchlist size
```

**5. Market Cap Fetch Failed**
```
Error: yfinance connection timeout
Solution: Check internet connectivity and yfinance symbol format
```

### Debug Mode

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

---

## 📚 Resources

### Angel One SmartAPI
- [API Documentation](https://smartapi.angelbroking.com/docs)
- [Symbol Master](https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json)
- [Rate Limits](https://smartapi.angelbroking.com/docs/RateLimit)

### Pattern Trading
- Bulkowski's Pattern Encyclopedia
- Technical Analysis of Financial Markets
- Chart Pattern Recognition Studies

### AWS Documentation
- [Lambda Developer Guide](https://docs.aws.amazon.com/lambda/)
- [Fargate User Guide](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/AWS_Fargate.html)
- [EventBridge Rules](https://docs.aws.amazon.com/eventbridge/)

---

## ⚠️ Disclaimer

**IMPORTANT:** This software is provided for **educational and research purposes only**.

- ❌ Not financial advice
- ❌ No guarantees of profitability
- ❌ Past performance ≠ future results
- ✅ Use at your own risk
- ✅ Test thoroughly before live trading
- ✅ Consult financial advisors

**Trading involves substantial risk of loss. Only risk capital you can afford to lose.**

---

## 🤝 Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create feature branch
3. Add tests for new features
4. Submit pull request

---

## 📄 License

MIT License - See LICENSE file for details

---

## 📞 Support

- **Issues:** Open GitHub issue
- **Discussions:** GitHub Discussions
- **Email:** support@example.com

---

## 🎯 Roadmap

- [ ] Multi-timeframe analysis (15-min + Daily confirmation)
- [ ] Advanced pattern variations (Bear flags, descending triangles)
- [ ] Machine learning pattern quality scoring
- [ ] Automated position management (trailing stops)
- [ ] Telegram/Discord notifications
- [ ] Web dashboard for monitoring
- [ ] Backtesting framework
- [ ] Paper trading mode with real-time simulation

---

## 🏆 Credits

Developed by: Algo Trading Engineer  
Strategy: Flag & Pennant Continuation Patterns  
Framework: Angel One SmartAPI  
Deployment: AWS Lambda & Fargate

---

**Happy Trading! 📈🚀**

*Remember: The best trade is sometimes no trade. Wait for high-quality setups!*
