"""
CS2 Market Analytics Bot — main entry point.

Usage:
    python main.py             # Start the bot + collector scheduler
    python main.py --seed      # Seed historical data then start bot
    python main.py --collect   # Run one collection cycle and exit (no bot)
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
        help="Seed InfluxDB with historical price data before starting the bot.",
    )
    parser.add_argument(
        "--collect",
        action="store_true",
        help="Run a single collection cycle and exit (no bot started).",
    )
    args = parser.parse_args()

    if args.collect:
        from src.collector.collector import Collector
        logger.info("Running single collection cycle...")
        result = Collector().run_collection_cycle()
        logger.info(f"Done: {result}")
        sys.exit(0)

    if args.seed:
        from src.collector.collector import Collector
        logger.info("Seeding historical data...")
        Collector().seed_historical_data()
        logger.info("Seed complete. Starting bot...")

    from src.bot.bot import start_bot
    start_bot()


if __name__ == "__main__":
    main()