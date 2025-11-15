import time
import strategy_backbone
import logging


def run_fargate_loop():
    """
    Main entrypoint for the Fargate container.
    Runs the scanner in a continuous loop.
    """
    # Define scan intervals
    # You could scan multiple timeframes
    SCAN_INTERVAL_15MIN = 900  # 15 minutes * 60 seconds

    while True:
        try:
            logging.info("--- FARGATE LOOP: Starting 15-minute scan ---")

            # Run the 15-minute scanner
            strategy_backbone.main_scanner_loop(timeframe="FIFTEEN_MINUTE")

            # In a real system, you might also run the Daily scanner once
            # e.g., if (time_is_9am):
            #   strategy_backbone.main_scanner_loop(timeframe="ONE_DAY")

            logging.info(f"--- FARGATE LOOP: Scan complete. Sleeping for {SCAN_INTERVAL_15MIN}s ---")
            time.sleep(SCAN_INTERVAL_15MIN)

        except Exception as e:
            logging.error(f"Critical error in Fargate main loop: {e}")
            logging.error("Restarting loop after 60s sleep...")
            time.sleep(60)


if __name__ == "__main__":
    run_fargate_loop()