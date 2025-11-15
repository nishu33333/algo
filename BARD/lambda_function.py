import json
import os
import strategy_backbone  # Imports all logic from the other file


def lambda_handler(event, context):
    """
    AWS Lambda handler function.
    This is triggered by CloudWatch Events (Cron).
    'event' will contain info about the trigger, e.g., timeframe.
    """

    # You can pass the timeframe in the EventBridge schedule's 'Input'
    # Defaulting to 15min if not provided
    timeframe = event.get('timeframe', 'FIFTEEN_MINUTE')

    try:
        found_trades = strategy_backbone.main_scanner_loop(timeframe=timeframe)

        return {
            'statusCode': 200,
            'body': json.dumps(f"Scan complete. Found {len(found_trades)} trades.")
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps(f"Error during scan: {e}")
        }