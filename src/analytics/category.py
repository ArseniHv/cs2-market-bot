"""
Category Aggregator.
Calculates category-level analytics across all tracked items in a category.
Exposes data for the /category bot command.
"""

import logging
from typing import Optional

import pandas as pd

from src.analytics.liquidity import calculate_liquidity
from src.analytics.models import CategoryResult
from src.collector.item_manager import ItemManager
from src.db.influx_client import InfluxClientWrapper

logger = logging.getLogger(__name__)


def calculate_category(
    category: str,
    db: InfluxClientWrapper,
    item_manager: ItemManager,
    bucket: str = "cs2_market",
) -> Optional[CategoryResult]:
    """
    Aggregate analytics for all tracked items in a given category.
    Returns None if no tracked items exist for that category.
    """
    items = [
        i for i in item_manager.get_all()
        if i["category"].lower() == category.lower()
    ]

    if not items:
        logger.warning(f"No tracked items for category: {category}")
        return None

    item_names = [i["market_hash_name"] for i in items]
    names_filter = " or ".join(
        [f'r.item_name == "{n}"' for n in item_names]
    )

    flux = f"""
from(bucket: "{bucket}")
  |> range(start: -30d)
  |> filter(fn: (r) => r._measurement == "skin_prices")
  |> filter(fn: (r) => {names_filter})
  |> filter(fn: (r) => r._field == "median_price")
  |> pivot(rowKey: ["_time", "item_name"], columnKey: ["_field"], valueColumn: "_value")
"""
    try:
        df = db.query_dataframe(flux)
        if df.empty:
            logger.warning(f"No price data found for category: {category}")
            return None

        # Category median price index
        median_price_index = round(float(df["median_price"].median()), 4)

        # Category-wide inflation
        recent = df.groupby("item_name")["median_price"].apply(
            lambda x: x.tail(7).mean()
        )
        overall = df.groupby("item_name")["median_price"].mean()
        inflation_pct = round(
            float(((recent.mean() - overall.mean()) / overall.mean()) * 100), 2
        ) if overall.mean() else 0.0

        # Liquidity per item
        liquidity_scores = {}
        for name in item_names:
            result = calculate_liquidity(name, db, bucket)
            if result:
                liquidity_scores[name] = result.score

        most_liquid = max(liquidity_scores, key=liquidity_scores.get) \
            if liquidity_scores else "N/A"
        least_liquid = min(liquidity_scores, key=liquidity_scores.get) \
            if liquidity_scores else "N/A"

        return CategoryResult(
            category=category,
            median_price_index=median_price_index,
            inflation_rate=inflation_pct,
            most_liquid_item=most_liquid,
            least_liquid_item=least_liquid,
            item_count=len(items),
        )

    except Exception as e:
        logger.error(f"Category aggregation failed for {category}: {e}")
        return None