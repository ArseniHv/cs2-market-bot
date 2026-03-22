"""
CS2 Market Analytics Bot — main entry point.

Usage:
    python main.py             # Start the collector scheduler
    python main.py --seed      # Seed historical data then start scheduler
    python main.py --collect   # Run one collection cycle and exit
"""

import argparse
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="CS2 Market Analytics Bot")
    parser.add_argument(
        "--seed",
        action="store_true",
        help="Seed InfluxDB with historical price data from Steam Market before starting.",
    )
    parser.add_argument(
        "--collect",
        action="store_true",
        help="Run a single collection cycle and exit.",
    )
    args = parser.parse_args()

    from src.collector.collector import Collector
    collector = Collector()

    if args.seed:
        logger.info("Running historical data seed...")
        collector.seed_historical_data()
        logger.info("Seed complete. Starting scheduler...")
        collector.start_scheduler()

    elif args.collect:
        logger.info("Running single collection cycle...")
        result = collector.run_collection_cycle()
        logger.info(f"Done: {result}")
        sys.exit(0)

    else:
        logger.info("Starting collection scheduler...")
        collector.start_scheduler()


if __name__ == "__main__":
    main()