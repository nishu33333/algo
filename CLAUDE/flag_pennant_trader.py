"""
Flag & Pennant Swing Trading System
Angel One SmartAPI Implementation

Author: Algo Trading Engineer
Strategy: Bullish Flag & Pennant Continuation Patterns
Capital: ₹25,000
Risk per Trade: 1% (₹250)
"""

import os
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np
import yfinance as yf
from SmartApi import SmartConnect
from SmartApi.smartWebSocketV2 import SmartWebSocketV2

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TradingConfig:
    """Trading configuration parameters"""
    TOTAL_CAPITAL = 25000  # ₹25,000
    ALLOCATION_PER_TRADE = 0.25  # 25%
    RISK_PER_TRADE = 0.01  # 1%
    MIN_MARKET_CAP = 1000  # ₹1,000 Crores
    SLIPPAGE = 0.001  # 0.1%
    REWARD_RISK_RATIO = 2.0  # 2:1
    
    # Pattern detection parameters
    MIN_FLAGPOLE_GAIN = 0.05  # 5% minimum gain
    FLAGPOLE_DAYS_MIN = 3
    FLAGPOLE_DAYS_MAX = 8
    CONSOLIDATION_DAYS_MIN = 3
    CONSOLIDATION_DAYS_MAX = 15
    VOLUME_BREAKOUT_MULTIPLIER = 1.5
    ATR_PERIOD = 14
    ATR_SL_MULTIPLIER = 0.5


class AngelOneClient:
    """Angel One SmartAPI client with authentication and retry logic"""
    
    def __init__(self, api_key: str, client_id: str, password: str, totp_secret: str):
        self.api_key = api_key
        self.client_id = client_id
        self.password = password
        self.totp_secret = totp_secret
        self.smart_api = None
        self.auth_token = None
        self.feed_token = None
        
    def generate_totp(self) -> str:
        """Generate TOTP for 2FA"""
        import pyotp
        totp = pyotp.TOTP(self.totp_secret)
        return totp.now()
    
    def login(self, max_retries: int = 3) -> bool:
        """Login to Angel One with retry logic"""
        for attempt in range(max_retries):
            try:
                self.smart_api = SmartConnect(api_key=self.api_key)
                totp = self.generate_totp()
                
                data = self.smart_api.generateSession(
                    self.client_id,
                    self.password,
                    totp
                )
                
                if data['status']:
                    self.auth_token = data['data']['jwtToken']
                    self.feed_token = data['data']['feedToken']
                    logger.info("Angel One login successful")
                    return True
                else:
                    logger.error(f"Login failed: {data.get('message', 'Unknown error')}")
                    
            except Exception as e:
                logger.error(f"Login attempt {attempt + 1} failed: {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
                    
        return False
    
    def get_historical_data(
        self,
        symbol_token: str,
        interval: str,
        from_date: str,
        to_date: str,
        max_retries: int = 3
    ) -> Optional[pd.DataFrame]:
        """
        Fetch historical candle data
        
        Args:
            symbol_token: Angel One symbol token
            interval: ONE_DAY, FIFTEEN_MINUTE, etc.
            from_date: Start date (YYYY-MM-DD HH:MM)
            to_date: End date (YYYY-MM-DD HH:MM)
        """
        for attempt in range(max_retries):
            try:
                params = {
                    "exchange": "NSE",
                    "symboltoken": symbol_token,
                    "interval": interval,
                    "fromdate": from_date,
                    "todate": to_date
                }
                
                data = self.smart_api.getCandleData(params)
                
                if data['status'] and data['data']:
                    df = pd.DataFrame(
                        data['data'],
                        columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
                    )
                    df['timestamp'] = pd.to_datetime(df['timestamp'])
                    df = df.sort_values('timestamp').reset_index(drop=True)
                    return df
                    
            except Exception as e:
                logger.error(f"Historical data fetch attempt {attempt + 1} failed: {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(1)
                    
        return None
    
    def place_order(
        self,
        symbol: str,
        symbol_token: str,
        quantity: int,
        price: float,
        order_type: str = "LIMIT",
        max_retries: int = 3
    ) -> Optional[Dict]:
        """
        Place order with retry logic
        
        Args:
            symbol: Trading symbol (e.g., RELIANCE-EQ)
            symbol_token: Angel One token
            quantity: Number of shares
            price: Order price
            order_type: MARKET or LIMIT
        """
        for attempt in range(max_retries):
            try:
                order_params = {
                    "variety": "NORMAL",
                    "tradingsymbol": symbol,
                    "symboltoken": symbol_token,
                    "transactiontype": "BUY",
                    "exchange": "NSE",
                    "ordertype": order_type,
                    "producttype": "DELIVERY",
                    "duration": "DAY",
                    "price": str(round(price, 2)),
                    "squareoff": "0",
                    "stoploss": "0",
                    "quantity": str(quantity)
                }
                
                if order_type == "MARKET":
                    order_params["price"] = "0"
                
                result = self.smart_api.placeOrder(order_params)
                
                if result['status']:
                    logger.info(f"Order placed successfully: {result['data']}")
                    return result['data']
                else:
                    logger.error(f"Order placement failed: {result.get('message', 'Unknown error')}")
                    
            except Exception as e:
                logger.error(f"Order placement attempt {attempt + 1} failed: {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(1)
                    
        return None


class PatternDetector:
    """Detect Flag and Pennant continuation patterns"""
    
    @staticmethod
    def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calculate Average True Range"""
        high = df['high']
        low = df['low']
        close = df['close'].shift(1)
        
        tr1 = high - low
        tr2 = abs(high - close)
        tr3 = abs(low - close)
        
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()
        
        return atr
    
    @staticmethod
    def detect_flagpole(df: pd.DataFrame, config: TradingConfig) -> Optional[Dict]:
        """
        Detect strong upward flagpole move
        
        Returns:
            Dict with flagpole_start_idx, flagpole_end_idx, flagpole_gain
        """
        if len(df) < config.FLAGPOLE_DAYS_MAX + config.CONSOLIDATION_DAYS_MAX:
            return None
        
        # Look for flagpole in recent history
        for pole_length in range(config.FLAGPOLE_DAYS_MIN, config.FLAGPOLE_DAYS_MAX + 1):
            end_idx = len(df) - config.CONSOLIDATION_DAYS_MIN - 1
            start_idx = end_idx - pole_length + 1
            
            if start_idx < 0:
                continue
            
            start_price = df.loc[start_idx, 'close']
            end_price = df.loc[end_idx, 'close']
            gain = (end_price - start_price) / start_price
            
            # Check if gain meets minimum threshold
            if gain >= config.MIN_FLAGPOLE_GAIN:
                # Check for increasing volume during flagpole
                pole_volume = df.loc[start_idx:end_idx, 'volume'].values
                avg_volume_first_half = pole_volume[:len(pole_volume)//2].mean()
                avg_volume_second_half = pole_volume[len(pole_volume)//2:].mean()
                
                if avg_volume_second_half > avg_volume_first_half * 0.8:  # Volume sustained or increased
                    return {
                        'start_idx': start_idx,
                        'end_idx': end_idx,
                        'gain': gain,
                        'height': end_price - start_price
                    }
        
        return None
    
    @staticmethod
    def detect_flag_consolidation(
        df: pd.DataFrame,
        flagpole: Dict,
        config: TradingConfig
    ) -> Optional[Dict]:
        """
        Detect parallel downward consolidation after flagpole
        
        Returns:
            Dict with consolidation details
        """
        consolidation_start = flagpole['end_idx'] + 1
        current_idx = len(df) - 1
        consolidation_length = current_idx - consolidation_start + 1
        
        if consolidation_length < config.CONSOLIDATION_DAYS_MIN:
            return None
        
        if consolidation_length > config.CONSOLIDATION_DAYS_MAX:
            consolidation_start = current_idx - config.CONSOLIDATION_DAYS_MAX + 1
            consolidation_length = config.CONSOLIDATION_DAYS_MAX
        
        # Extract consolidation data
        consol_df = df.loc[consolidation_start:current_idx].copy()
        
        # Check for decreasing volume
        if consol_df['volume'].iloc[-1] > consol_df['volume'].iloc[0] * 1.2:
            return None  # Volume should decrease during consolidation
        
        # Calculate consolidation high and low
        consol_high = consol_df['high'].max()
        consol_low = consol_df['low'].min()
        
        # Flag should consolidate within 50% of flagpole height
        consolidation_range = consol_high - consol_low
        if consolidation_range > flagpole['height'] * 0.5:
            return None
        
        # Check for slight downward bias (flag characteristic)
        first_half_avg = consol_df.iloc[:len(consol_df)//2]['close'].mean()
        second_half_avg = consol_df.iloc[len(consol_df)//2:]['close'].mean()
        
        if second_half_avg > first_half_avg:
            return None  # Should have downward drift
        
        return {
            'start_idx': consolidation_start,
            'end_idx': current_idx,
            'high': consol_high,
            'low': consol_low,
            'length': consolidation_length
        }
    
    @staticmethod
    def detect_pennant_consolidation(
        df: pd.DataFrame,
        flagpole: Dict,
        config: TradingConfig
    ) -> Optional[Dict]:
        """
        Detect converging triangle consolidation after flagpole
        
        Returns:
            Dict with pennant details
        """
        consolidation_start = flagpole['end_idx'] + 1
        current_idx = len(df) - 1
        consolidation_length = current_idx - consolidation_start + 1
        
        if consolidation_length < config.CONSOLIDATION_DAYS_MIN:
            return None
        
        if consolidation_length > config.CONSOLIDATION_DAYS_MAX:
            consolidation_start = current_idx - config.CONSOLIDATION_DAYS_MAX + 1
            consolidation_length = config.CONSOLIDATION_DAYS_MAX
        
        consol_df = df.loc[consolidation_start:current_idx].copy()
        
        # Check for decreasing volume
        if consol_df['volume'].iloc[-1] > consol_df['volume'].iloc[0] * 1.2:
            return None
        
        # Check for converging highs and lows
        highs = consol_df['high'].values
        lows = consol_df['low'].values
        
        # Simple convergence check: range should be decreasing
        first_half_range = (highs[:len(highs)//2].max() - lows[:len(lows)//2].min())
        second_half_range = (highs[len(highs)//2:].max() - lows[len(lows)//2:].min())
        
        if second_half_range >= first_half_range:
            return None  # Not converging
        
        consol_high = consol_df['high'].max()
        consol_low = consol_df['low'].min()
        
        return {
            'start_idx': consolidation_start,
            'end_idx': current_idx,
            'high': consol_high,
            'low': consol_low,
            'length': consolidation_length
        }
    
    @classmethod
    def detect_patterns(
        cls,
        df: pd.DataFrame,
        config: TradingConfig
    ) -> List[Dict]:
        """
        Main pattern detection function
        
        Returns:
            List of detected patterns with trade parameters
        """
        patterns = []
        
        # Detect flagpole
        flagpole = cls.detect_flagpole(df, config)
        if not flagpole:
            return patterns
        
        # Try to detect flag
        flag = cls.detect_flag_consolidation(df, flagpole, config)
        if flag:
            # Check for breakout
            current_price = df.iloc[-1]['close']
            current_volume = df.iloc[-1]['volume']
            avg_volume = df.iloc[-20:]['volume'].mean()
            
            if (current_price > flag['high'] and 
                current_volume > avg_volume * config.VOLUME_BREAKOUT_MULTIPLIER):
                
                atr = cls.calculate_atr(df, config.ATR_PERIOD).iloc[-1]
                
                pattern = {
                    'type': 'FLAG',
                    'flagpole': flagpole,
                    'consolidation': flag,
                    'breakout_price': current_price,
                    'stop_loss': flag['low'] - (atr * config.ATR_SL_MULTIPLIER),
                    'atr': atr,
                    'avg_volume': avg_volume,
                    'breakout_volume': current_volume
                }
                patterns.append(pattern)
        
        # Try to detect pennant
        pennant = cls.detect_pennant_consolidation(df, flagpole, config)
        if pennant:
            current_price = df.iloc[-1]['close']
            current_volume = df.iloc[-1]['volume']
            avg_volume = df.iloc[-20:]['volume'].mean()
            
            if (current_price > pennant['high'] and 
                current_volume > avg_volume * config.VOLUME_BREAKOUT_MULTIPLIER):
                
                atr = cls.calculate_atr(df, config.ATR_PERIOD).iloc[-1]
                
                pattern = {
                    'type': 'PENNANT',
                    'flagpole': flagpole,
                    'consolidation': pennant,
                    'breakout_price': current_price,
                    'stop_loss': pennant['low'] - (atr * config.ATR_SL_MULTIPLIER),
                    'atr': atr,
                    'avg_volume': avg_volume,
                    'breakout_volume': current_volume
                }
                patterns.append(pattern)
        
        return patterns


class MarketFilter:
    """Apply market cap and liquidity filters"""
    
    @staticmethod
    def get_market_cap(symbol: str) -> Optional[float]:
        """
        Fetch market cap using yfinance
        
        Returns:
            Market cap in Crores INR
        """
        try:
            # Convert NSE symbol to Yahoo Finance format
            yf_symbol = f"{symbol}.NS"
            ticker = yf.Ticker(yf_symbol)
            info = ticker.info
            
            # Market cap in USD, convert to INR Crores
            market_cap_usd = info.get('marketCap', 0)
            if market_cap_usd:
                # Approximate USD to INR conversion (83 INR per USD)
                market_cap_inr_crores = (market_cap_usd * 83) / 10000000
                return market_cap_inr_crores
                
        except Exception as e:
            logger.error(f"Error fetching market cap for {symbol}: {str(e)}")
            
        return None
    
    @staticmethod
    def check_liquidity(
        df: pd.DataFrame,
        position_value: float,
        lookback_days: int = 30
    ) -> bool:
        """
        Check if stock meets liquidity requirements
        
        Args:
            df: Historical price data
            position_value: Intended position size in INR
            lookback_days: Days to calculate average turnover
        """
        if len(df) < lookback_days:
            return False
        
        recent_data = df.iloc[-lookback_days:]
        avg_turnover = (recent_data['close'] * recent_data['volume']).mean()
        
        # Turnover should be at least 2x position size
        return avg_turnover >= (position_value * 2)
    
    @staticmethod
    def apply_filters(
        symbol: str,
        df: pd.DataFrame,
        position_value: float,
        config: TradingConfig
    ) -> bool:
        """
        Apply all filters
        
        Returns:
            True if stock passes all filters
        """
        # Market cap filter
        market_cap = MarketFilter.get_market_cap(symbol)
        if not market_cap or market_cap < config.MIN_MARKET_CAP:
            logger.info(f"{symbol} failed market cap filter: {market_cap} Cr")
            return False
        
        # Liquidity filter
        if not MarketFilter.check_liquidity(df, position_value):
            logger.info(f"{symbol} failed liquidity filter")
            return False
        
        logger.info(f"{symbol} passed all filters. Market Cap: {market_cap:.2f} Cr")
        return True


class PositionSizer:
    """Calculate position size based on risk and allocation"""
    
    @staticmethod
    def calculate_position_size(
        entry_price: float,
        stop_loss: float,
        config: TradingConfig
    ) -> Dict:
        """
        Calculate position size
        
        Returns:
            Dict with quantity, allocation, and risk details
        """
        # Add slippage to entry
        entry_with_slippage = entry_price * (1 + config.SLIPPAGE)
        
        # Risk per share
        risk_per_share = entry_with_slippage - stop_loss
        
        if risk_per_share <= 0:
            return {
                'quantity': 0,
                'reason': 'Invalid stop loss (above entry price)'
            }
        
        # Calculate quantities
        max_allocation = config.TOTAL_CAPITAL * config.ALLOCATION_PER_TRADE
        max_risk = config.TOTAL_CAPITAL * config.RISK_PER_TRADE
        
        qty_risk_based = int(max_risk / risk_per_share)
        qty_allocation_based = int(max_allocation / entry_with_slippage)
        
        # Take minimum
        quantity = min(qty_risk_based, qty_allocation_based)
        
        if quantity <= 0:
            return {
                'quantity': 0,
                'reason': 'Quantity too small after risk calculation'
            }
        
        # Calculate actual values
        actual_allocation = quantity * entry_with_slippage
        actual_risk = quantity * risk_per_share
        
        # Calculate target
        target = entry_with_slippage + (risk_per_share * config.REWARD_RISK_RATIO)
        
        return {
            'quantity': quantity,
            'entry_price': entry_price,
            'entry_with_slippage': round(entry_with_slippage, 2),
            'stop_loss': round(stop_loss, 2),
            'target': round(target, 2),
            'allocation': round(actual_allocation, 2),
            'risk_amount': round(actual_risk, 2),
            'risk_percentage': round((actual_risk / config.TOTAL_CAPITAL) * 100, 2),
            'reward_amount': round(quantity * risk_per_share * config.REWARD_RISK_RATIO, 2),
            'reward_risk_ratio': config.REWARD_RISK_RATIO
        }


class TradingSystem:
    """Main trading system orchestrator"""
    
    def __init__(self, angel_client: AngelOneClient, config: TradingConfig):
        self.angel_client = angel_client
        self.config = config
        self.pattern_detector = PatternDetector()
        self.market_filter = MarketFilter()
        self.position_sizer = PositionSizer()
        
    def scan_stock(self, symbol: str, symbol_token: str, interval: str = "ONE_DAY") -> Optional[Dict]:
        """
        Scan a single stock for patterns
        
        Args:
            symbol: Stock symbol (e.g., RELIANCE)
            symbol_token: Angel One token
            interval: Timeframe (ONE_DAY, FIFTEEN_MINUTE)
        """
        logger.info(f"Scanning {symbol} on {interval} timeframe")
        
        # Fetch historical data (90 days for daily, 30 days for intraday)
        days_back = 90 if interval == "ONE_DAY" else 30
        to_date = datetime.now().strftime("%Y-%m-%d %H:%M")
        from_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d %H:%M")
        
        df = self.angel_client.get_historical_data(
            symbol_token,
            interval,
            from_date,
            to_date
        )
        
        if df is None or len(df) < 30:
            logger.warning(f"Insufficient data for {symbol}")
            return None
        
        # Detect patterns
        patterns = self.pattern_detector.detect_patterns(df, self.config)
        
        if not patterns:
            logger.info(f"No patterns detected for {symbol}")
            return None
        
        # Process first detected pattern
        pattern = patterns[0]
        logger.info(f"{pattern['type']} pattern detected for {symbol}")
        
        # Calculate position size
        position = self.position_sizer.calculate_position_size(
            pattern['breakout_price'],
            pattern['stop_loss'],
            self.config
        )
        
        if position['quantity'] <= 0:
            logger.warning(f"Position size too small for {symbol}: {position.get('reason', 'Unknown')}")
            return None
        
        # Apply market filters
        if not self.market_filter.apply_filters(
            symbol,
            df,
            position['allocation'],
            self.config
        ):
            return None
        
        # Prepare trade signal
        trade_signal = {
            'symbol': symbol,
            'symbol_token': symbol_token,
            'pattern_type': pattern['type'],
            'timeframe': interval,
            'current_price': round(pattern['breakout_price'], 2),
            'entry_price': position['entry_with_slippage'],
            'stop_loss': position['stop_loss'],
            'target': position['target'],
            'quantity': position['quantity'],
            'allocation': position['allocation'],
            'risk_amount': position['risk_amount'],
            'risk_percentage': position['risk_percentage'],
            'reward_amount': position['reward_amount'],
            'reward_risk_ratio': position['reward_risk_ratio'],
            'atr': round(pattern['atr'], 2),
            'avg_volume': int(pattern['avg_volume']),
            'breakout_volume': int(pattern['breakout_volume']),
            'volume_ratio': round(pattern['breakout_volume'] / pattern['avg_volume'], 2),
            'timestamp': datetime.now().isoformat()
        }
        
        return trade_signal
    
    def execute_trade(self, trade_signal: Dict, dry_run: bool = True) -> Dict:
        """
        Execute trade based on signal
        
        Args:
            trade_signal: Trade details
            dry_run: If True, don't place actual orders
        """
        logger.info(f"\n{'='*60}")
        logger.info(f"TRADE SIGNAL: {trade_signal['symbol']}")
        logger.info(f"Pattern: {trade_signal['pattern_type']}")
        logger.info(f"Entry: ₹{trade_signal['entry_price']} | SL: ₹{trade_signal['stop_loss']} | Target: ₹{trade_signal['target']}")
        logger.info(f"Quantity: {trade_signal['quantity']} | Allocation: ₹{trade_signal['allocation']}")
        logger.info(f"Risk: ₹{trade_signal['risk_amount']} ({trade_signal['risk_percentage']}%)")
        logger.info(f"{'='*60}\n")
        
        if dry_run:
            logger.info("DRY RUN MODE - No actual order placed")
            return {
                'status': 'DRY_RUN',
                'trade_signal': trade_signal
            }
        
        # Place actual order
        order_result = self.angel_client.place_order(
            f"{trade_signal['symbol']}-EQ",
            trade_signal['symbol_token'],
            trade_signal['quantity'],
            trade_signal['entry_price'],
            order_type="LIMIT"
        )
        
        if order_result:
            return {
                'status': 'ORDER_PLACED',
                'order_id': order_result.get('orderid'),
                'trade_signal': trade_signal
            }
        else:
            return {
                'status': 'ORDER_FAILED',
                'trade_signal': trade_signal
            }
    
    def scan_watchlist(self, watchlist: List[Dict], dry_run: bool = True) -> List[Dict]:
        """
        Scan multiple stocks from watchlist
        
        Args:
            watchlist: List of {'symbol': 'RELIANCE', 'token': '1234'}
            dry_run: If True, don't place actual orders
        """
        results = []
        
        for stock in watchlist:
            try:
                # Scan on daily timeframe
                signal = self.scan_stock(
                    stock['symbol'],
                    stock['token'],
                    interval="ONE_DAY"
                )
                
                if signal:
                    result = self.execute_trade(signal, dry_run=dry_run)
                    results.append(result)
                    
                # Small delay between scans
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"Error scanning {stock['symbol']}: {str(e)}")
                continue
        
        return results


def main():
    """Main execution function"""
    
    # Load credentials from environment variables
    api_key = os.getenv('ANGEL_API_KEY')
    client_id = os.getenv('ANGEL_CLIENT_ID')
    password = os.getenv('ANGEL_PASSWORD')
    totp_secret = os.getenv('ANGEL_TOTP_SECRET')
    
    if not all([api_key, client_id, password, totp_secret]):
        logger.error("Missing Angel One credentials in environment variables")
        return
    
    # Initialize Angel One client
    angel_client = AngelOneClient(api_key, client_id, password, totp_secret)
    
    # Login
    if not angel_client.login():
        logger.error("Failed to login to Angel One")
        return
    
    # Initialize trading system
    config = TradingConfig()
    trading_system = TradingSystem(angel_client, config)
    
    # Sample watchlist (You need to get actual symbol tokens from Angel One)
    watchlist = [
        {'symbol': 'RELIANCE', 'token': '2885'},
        {'symbol': 'TCS', 'token': '11536'},
        {'symbol': 'INFY', 'token': '1594'},
        {'symbol': 'HDFCBANK', 'token': '1333'},
        {'symbol': 'ICICIBANK', 'token': '4963'},
    ]
    
    # Run scan
    results = trading_system.scan_watchlist(watchlist, dry_run=True)
    
    # Print results
    logger.info(f"\n{'='*60}")
    logger.info(f"SCAN COMPLETE - {len(results)} signals generated")
    logger.info(f"{'='*60}")
    
    for result in results:
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
