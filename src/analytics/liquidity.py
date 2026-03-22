"""
Liquidity Calculator.
Liquidity score = rolling_7d_avg(volume) / median_price.
Score interpretation: >1.0 = highly liquid, 0.5-1.0 = moderate, <0.5 = illiquid.
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd

from src.analytics.models import LiquidityResult
from src.db.influx_client import InfluxClientWrapper

logger = logging.getLogger(__name__)


def interpret_liquidity(score: float) -> str:
    if score > 1.0:
        return "highly liquid"
    elif score >= 0.5:
        return "moderate"
    else:
        return "illiquid"


def calculate_liquidity(
    item_name: str,
    db: InfluxClientWrapper,
    bucket: str = "cs2_market",
) -> Optional[LiquidityResult]:
    """
    Calculate liquidity score for a single item using the last 7 days of data.
    Returns None if insufficient data is available.
    """
    flux = f"""
from(bucket: "{bucket}")
  |> range(start: -7d)
  |> filter(fn: (r) => r._measurement == "skin_prices")
  |> filter(fn: (r) => r.item_name == "{item_name}")
  |> filter(fn: (r) => r._field == "volume" or r._field == "median_price")
  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
"""
    try:
        df = db.query_dataframe(flux)
        if df.empty or len(df) < 3:
            logger.warning(f"Insufficient data for liquidity: {item_name}")
            return None

        avg_volume = float(df["volume"].mean()) if "volume" in df.columns else 0.0
        median_price = float(df["median_price"].median()) if "median_price" in df.columns else 0.0

        if median_price == 0:
            logger.warning(f"Zero median price for liquidity calc: {item_name}")
            return None

        score = round(avg_volume / median_price, 4)

        return LiquidityResult(
            item_name=item_name,
            score=score,
            interpretation=interpret_liquidity(score),
            rolling_7d_avg_volume=round(avg_volume, 2),
            median_price=round(median_price, 4),
        )

    except Exception as e:
        logger.error(f"Liquidity calculation failed for {item_name}: {e}")
        return None