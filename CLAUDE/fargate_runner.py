"""
AWS Fargate Runner for Flag & Pennant Trading System
Runs as a scheduled container task
"""

import os
import json
import logging
from datetime import datetime

from flag_pennant_trading_system import (
    AngelOneClient,
    TradingConfig,
    TradingSystem
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Main execution for Fargate container"""
    
    logger.info("="*60)
    logger.info("FLAG & PENNANT TRADING SYSTEM - FARGATE EXECUTION")
    logger.info(f"Started at: {datetime.now().isoformat()}")
    logger.info("="*60)
    
    try:
        # Get credentials from environment variables
        api_key = os.getenv('ANGEL_API_KEY')
        client_id = os.getenv('ANGEL_CLIENT_ID')
        password = os.getenv('ANGEL_PASSWORD')
        totp_secret = os.getenv('ANGEL_TOTP_SECRET')
        dry_run = os.getenv('DRY_RUN', 'true').lower() == 'true'
        
        if not all([api_key, client_id, password, totp_secret]):
            logger.error("Missing required environment variables")
            return
        
        logger.info(f"Dry Run Mode: {dry_run}")
        
        # Initialize Angel One client
        logger.info("Initializing Angel One client...")
        angel_client = AngelOneClient(api_key, client_id, password, totp_secret)
        
        # Login
        logger.info("Logging in to Angel One...")
        if not angel_client.login():
            logger.error("Failed to login to Angel One")
            return
        
        logger.info("Login successful!")
        
        # Initialize trading system
        config = TradingConfig()
        trading_system = TradingSystem(angel_client, config)
        
        # Comprehensive watchlist (NSE Top 50 stocks)
        watchlist = [
            {'symbol': 'RELIANCE', 'token': '2885'},
            {'symbol': 'TCS', 'token': '11536'},
            {'symbol': 'HDFCBANK', 'token': '1333'},
            {'symbol': 'INFY', 'token': '1594'},
            {'symbol': 'ICICIBANK', 'token': '4963'},
            {'symbol': 'HINDUNILVR', 'token': '1394'},
            {'symbol': 'BHARTIARTL', 'token': '10604'},
            {'symbol': 'SBIN', 'token': '3045'},
            {'symbol': 'LT', 'token': '11483'},
            {'symbol': 'AXISBANK', 'token': '5900'},
            {'symbol': 'ITC', 'token': '1660'},
            {'symbol': 'KOTAKBANK', 'token': '1922'},
            {'symbol': 'BAJFINANCE', 'token': '317'},
            {'symbol': 'ASIANPAINT', 'token': '236'},
            {'symbol': 'MARUTI', 'token': '10999'},
            {'symbol': 'TITAN', 'token': '3506'},
            {'symbol': 'SUNPHARMA', 'token': '3351'},
            {'symbol': 'ULTRACEMCO', 'token': '11532'},
            {'symbol': 'NESTLEIND', 'token': '17963'},
            {'symbol': 'WIPRO', 'token': '3787'},
            {'symbol': 'POWERGRID', 'token': '14977'},
            {'symbol': 'NTPC', 'token': '11630'},
            {'symbol': 'M&M', 'token': '2031'},
            {'symbol': 'ADANIENT', 'token': '25'},
            {'symbol': 'TATAMOTORS', 'token': '3456'},
            {'symbol': 'TATASTEEL', 'token': '3499'},
            {'symbol': 'ONGC', 'token': '2475'},
            {'symbol': 'BAJAJFINSV', 'token': '16675'},
            {'symbol': 'TECHM', 'token': '13538'},
            {'symbol': 'HCLTECH', 'token': '7229'}
        ]
        
        logger.info(f"Scanning {len(watchlist)} stocks...")
        
        # Run scan
        results = trading_system.scan_watchlist(watchlist, dry_run=dry_run)
        
        # Summary
        logger.info("="*60)
        logger.info("EXECUTION SUMMARY")
        logger.info(f"Stocks Scanned: {len(watchlist)}")
        logger.info(f"Signals Generated: {len(results)}")
        logger.info(f"Dry Run: {dry_run}")
        logger.info("="*60)
        
        # Save results to file (useful for logging in CloudWatch)
        results_file = f"/tmp/trading_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(results_file, 'w') as f:
            json.dump({
                'timestamp': datetime.now().isoformat(),
                'stocks_scanned': len(watchlist),
                'signals_generated': len(results),
                'dry_run': dry_run,
                'results': results
            }, f, indent=2)
        
        logger.info(f"Results saved to: {results_file}")
        
        # Print detailed results
        if results:
            logger.info("\nDETAILED RESULTS:")
            for i, result in enumerate(results, 1):
                logger.info(f"\n--- Signal {i} ---")
                logger.info(json.dumps(result, indent=2))
        
        logger.info("\n" + "="*60)
        logger.info("Execution completed successfully")
        logger.info("="*60)
        
    except Exception as e:
        logger.error(f"Execution failed: {str(e)}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
