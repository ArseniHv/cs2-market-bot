"""
Writes collected price data to InfluxDB.
Maps normalised API responses to the skin_prices measurement schema.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from src.db.influx_client import InfluxClientWrapper

logger = logging.getLogger(__name__)


class InfluxWriter:
    def __init__(self, db: InfluxClientWrapper):
        self.db = db

    def write_price_point(
        self,
        item: dict,
        price_data: dict,
        timestamp: Optional[datetime] = None,
    ) -> None:
        """
        Write a single price snapshot for an item.

        item: dict from ItemManager with keys market_hash_name, category, float_range
        price_data: normalised dict from CSGOTraderClient.get_item_price()
        """
        ts = timestamp or datetime.now(timezone.utc)

        try:
            self.db.write_skin_price(
                item_name=item["market_hash_name"],
                category=item["category"],
                float_range=item["float_range"],
                median_price=price_data["median_price"],
                volume=price_data["volume"],
                lowest_sell=price_data["lowest_sell"],
                highest_buy=price_data["highest_buy"],
                spread=price_data["spread"],
                timestamp=ts,
            )
            logger.debug(
                f"Wrote price point: {item['market_hash_name']} "
                f"@ ${price_data['median_price']:.2f}"
            )
        except Exception as e:
            logger.error(
                f"Failed to write price point for {item['market_hash_name']}: {e}"
            )

    def write_historical_points(
        self,
        item: dict,
        points: list[dict],
    ) -> int:
        """
        Bulk-write historical price points for an item.
        Returns the number of points successfully written.
        """
        written = 0
        for point in points:
            try:
                self.db.write_skin_price(
                    item_name=item["market_hash_name"],
                    category=item["category"],
                    float_range=item["float_range"],
                    median_price=point["median_price"],
                    volume=point["volume"],
                    lowest_sell=point["lowest_sell"],
                    highest_buy=point["highest_buy"],
                    spread=point["spread"],
                    timestamp=point["timestamp"],
                )
                written += 1
            except Exception as e:
                logger.error(
                    f"Failed to write historical point for "
                    f"{item['market_hash_name']} at {point.get('timestamp')}: {e}"
                )
        logger.info(
            f"Wrote {written}/{len(points)} historical points "
            f"for {item['market_hash_name']}"
        )
        return written