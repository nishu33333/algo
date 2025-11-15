"""
AWS Lambda Handler for Flag & Pennant Trading System
"""

import json
import os
import sys
from datetime import datetime

# Import main trading system
from flag_pennant_trading_system import (
    AngelOneClient,
    TradingConfig,
    TradingSystem
)


def lambda_handler(event, context):
    """
    AWS Lambda entry point
    
    Expected event format:
    {
        "watchlist": [
            {"symbol": "RELIANCE", "token": "2885"},
            {"symbol": "TCS", "token": "11536"}
        ],
        "dry_run": true
    }
    """
    
    print(f"Lambda execution started at {datetime.now().isoformat()}")
    
    try:
        # Get credentials from environment variables
        api_key = os.getenv('ANGEL_API_KEY')
        client_id = os.getenv('ANGEL_CLIENT_ID')
        password = os.getenv('ANGEL_PASSWORD')
        totp_secret = os.getenv('ANGEL_TOTP_SECRET')
        
        if not all([api_key, client_id, password, totp_secret]):
            return {
                'statusCode': 500,
                'body': json.dumps({
                    'error': 'Missing Angel One credentials',
                    'timestamp': datetime.now().isoformat()
                })
            }
        
        # Initialize Angel One client
        angel_client = AngelOneClient(api_key, client_id, password, totp_secret)
        
        # Login
        if not angel_client.login():
            return {
                'statusCode': 500,
                'body': json.dumps({
                    'error': 'Failed to login to Angel One',
                    'timestamp': datetime.now().isoformat()
                })
            }
        
        # Initialize trading system
        config = TradingConfig()
        trading_system = TradingSystem(angel_client, config)
        
        # Get watchlist from event or use default
        watchlist = event.get('watchlist', [
            {'symbol': 'RELIANCE', 'token': '2885'},
            {'symbol': 'TCS', 'token': '11536'},
            {'symbol': 'INFY', 'token': '1594'},
            {'symbol': 'HDFCBANK', 'token': '1333'},
            {'symbol': 'ICICIBANK', 'token': '4963'},
            {'symbol': 'WIPRO', 'token': '3787'},
            {'symbol': 'AXISBANK', 'token': '5900'},
            {'symbol': 'BHARTIARTL', 'token': '10604'},
            {'symbol': 'SBIN', 'token': '3045'},
            {'symbol': 'LT', 'token': '11483'}
        ])
        
        dry_run = event.get('dry_run', True)
        
        # Run scan
        results = trading_system.scan_watchlist(watchlist, dry_run=dry_run)
        
        # Format response
        response = {
            'statusCode': 200,
            'body': json.dumps({
                'timestamp': datetime.now().isoformat(),
                'stocks_scanned': len(watchlist),
                'signals_generated': len(results),
                'dry_run': dry_run,
                'results': results
            }, indent=2)
        }
        
        print(f"Lambda execution completed: {len(results)} signals")
        return response
        
    except Exception as e:
        print(f"Lambda execution failed: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            })
        }


# For local testing
if __name__ == "__main__":
    test_event = {
        "watchlist": [
            {"symbol": "RELIANCE", "token": "2885"},
            {"symbol": "TCS", "token": "11536"}
        ],
        "dry_run": True
    }
    
    result = lambda_handler(test_event, None)
    print(json.dumps(result, indent=2))
