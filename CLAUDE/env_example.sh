# Angel One SmartAPI Credentials
# Get these from: https://smartapi.angelbroking.com/
ANGEL_API_KEY=your_api_key_here
ANGEL_CLIENT_ID=your_client_id_here
ANGEL_PASSWORD=your_password_here
ANGEL_TOTP_SECRET=your_totp_secret_here

# Trading Configuration
DRY_RUN=true  # Set to 'false' for live trading (USE WITH CAUTION!)

# AWS Configuration (if using AWS deployment)
AWS_REGION=us-east-1
AWS_ACCOUNT_ID=your_aws_account_id

# Optional: Notification Settings
ENABLE_NOTIFICATIONS=false
NOTIFICATION_EMAIL=your_email@example.com
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL

# Optional: Advanced Trading Parameters
CAPITAL=25000  # Total trading capital in INR
ALLOCATION_PER_TRADE=0.25  # 25% allocation per trade
RISK_PER_TRADE=0.01  # 1% risk per trade
MIN_MARKET_CAP=1000  # Minimum market cap in Crores
SLIPPAGE=0.001  # 0.1% slippage assumption
REWARD_RISK_RATIO=2.0  # Target 2:1 reward-to-risk

# Pattern Detection Parameters
MIN_FLAGPOLE_GAIN=0.05  # 5% minimum gain for flagpole
FLAGPOLE_DAYS_MIN=3
FLAGPOLE_DAYS_MAX=8
CONSOLIDATION_DAYS_MIN=3
CONSOLIDATION_DAYS_MAX=15
VOLUME_BREAKOUT_MULTIPLIER=1.5
ATR_PERIOD=14
ATR_SL_MULTIPLIER=0.5

# Logging Level (DEBUG, INFO, WARNING, ERROR)
LOG_LEVEL=INFO
