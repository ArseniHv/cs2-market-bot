"""
Main data collection pipeline.
Every cycle: fetches all CS2 prices from Skinport in one bulk request,
detects market-wide movers, and writes deep data for tracked items to InfluxDB.
Runs on a configurable schedule via APScheduler.
"""

import logging
import os

from apscheduler.schedulers.blocking import BlockingScheduler
from dotenv import load_dotenv

from src.collector.skinport_client import SkinportClient
from src.collector.influx_writer import InfluxWriter
from src.collector.item_manager import ItemManager
from src.db.influx_client import InfluxClientWrapper

load_dotenv()

logger = logging.getLogger(__name__)

COLLECTION_INTERVAL = int(os.getenv("COLLECTION_INTERVAL_MINUTES", "30"))


class Collector:
    def __init__(self):
        self.db = InfluxClientWrapper()
        self.item_manager = ItemManager()
        self.skinport = SkinportClient()
        self.writer = InfluxWriter(self.db)

    def run_collection_cycle(self) -> dict:
        """
        Execute one full collection cycle:
        1. Bulk-fetch all CS2 item prices from Skinport (one request)
        2. Detect market-wide movers vs previous cycle
        3. Write deep price data for tracked items to InfluxDB
        Returns a summary dict.
        """
        logger.info("Starting collection cycle...")

        # Step 1: Bulk fetch all prices
        all_prices = self.skinport.fetch_all_prices()
        if not all_prices:
            logger.error("Skinport returned empty data. Aborting cycle.")
            return {"success": 0, "failed": 0, "total": 0, "movers": 0}

        # Step 2: Detect market-wide movers
        previous_prices = self.skinport.load_last_prices()
        if previous_prices:
            movers = self.skinport.detect_movers(all_prices, previous_prices)
            self.skinport.save_market_movers(movers)
            logger.info(
                f"Market-wide spike detection: {len(movers)} movers found "
                f"(≥5% change across {len(all_prices)} items)."
            )
        else:
            movers = []
            logger.info(
                "No previous price snapshot found — skipping mover detection. "
                "Will compare on next cycle."
            )

        # Save current as next cycle's baseline
        self.skinport.save_last_prices(all_prices)

        # Step 3: Deep write for tracked items
        tracked = self.item_manager.get_all()
        if not tracked:
            logger.warning("No tracked items in items.json.")
            return {"success": 0, "failed": 0, "total": 0, "movers": len(movers)}

        logger.info(f"Writing deep data for {len(tracked)} tracked items...")
        success = 0
        failed = 0

        for item in tracked:
            name = item["market_hash_name"]
            try:
                price_data = self.skinport.get_item_price(name, all_prices)
                if price_data is None:
                    logger.warning(f"No Skinport data for tracked item: {name}")
                    failed += 1
                    continue

                self.writer.write_price_point(item, price_data)
                logger.info(
                    f"✓ {name}: ${price_data['median_price']:.2f} "
                    f"(vol: {price_data['volume']})"
                )
                success += 1

            except Exception as e:
                logger.error(f"Error writing {name}: {e}")
                failed += 1

        logger.info(
            f"Cycle complete — Tracked: {success} ok / {failed} failed. "
            f"Market movers detected: {len(movers)}."
        )
        return {
            "success": success,
            "failed": failed,
            "total": len(tracked),
            "movers": len(movers),
        }

    def seed_historical_data(self) -> None:
        """
        Seed InfluxDB with historical price data from Steam Market.
        Called once via the --seed CLI flag. Tracked items only.
        """
        from src.collector.steam_history_client import SteamHistoryClient

        delay = float(os.getenv("STEAM_REQUEST_DELAY_SECONDS", "3"))
        steam_client = SteamHistoryClient(request_delay=delay)
        items = self.item_manager.get_all()

        logger.info(f"Seeding historical data for {len(items)} tracked items...")
        logger.info("This will take a while due to Steam rate limiting. Please wait.")

        for i, item in enumerate(items, 1):
            name = item["market_hash_name"]
            logger.info(f"[{i}/{len(items)}] Seeding: {name}")

            raw_history = steam_client.fetch_history(name)
            if raw_history is None:
                logger.warning(f"No history available for: {name}")
                continue

            points = steam_client.parse_history_to_points(raw_history)
            if not points:
                logger.warning(f"Could not parse history for: {name}")
                continue

            written = self.writer.write_historical_points(item, points)
            logger.info(f"Seeded {written} points for: {name}")

        logger.info("Historical seeding complete.")

    def start_scheduler(self) -> None:
        """Start the APScheduler blocking scheduler."""
        scheduler = BlockingScheduler(timezone="UTC")
        scheduler.add_job(
            self.run_collection_cycle,
            trigger="interval",
            minutes=COLLECTION_INTERVAL,
            id="collection_job",
            name="CS2 price collection",
            replace_existing=True,
        )
        logger.info(
            f"Scheduler started. Collection runs every {COLLECTION_INTERVAL} minutes."
        )
        logger.info("Running first collection cycle immediately...")
        self.run_collection_cycle()

        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            logger.info("Scheduler stopped.")