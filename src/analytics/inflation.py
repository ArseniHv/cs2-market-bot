"""
Inflation Detector.
Compares 7-day rolling average price to 30-day rolling average.
Deviation = (7d_avg - 30d_avg) / 30d_avg * 100.
Applies tiered alert system with superflag volume cross-check.
"""

import logging
from typing import Optional

import pandas as pd

from src.analytics.models import InflationResult
from src.analytics.tiers import get_alert_tier
from src.db.influx_client import InfluxClientWrapper

logger = logging.getLogger(__name__)


def calculate_inflation(
    item_name: str,
    db: InfluxClientWrapper,
    bucket: str = "cs2_market",
) -> Optional[InflationResult]:
    """
    Calculate inflation for a single item using last 30 days of price data.
    Returns None if insufficient data.
    """
    flux = f"""
from(bucket: "{bucket}")
  |> range(start: -30d)
  |> filter(fn: (r) => r._measurement == "skin_prices")
  |> filter(fn: (r) => r.item_name == "{item_name}")
  |> filter(fn: (r) => r._field == "median_price" or r._field == "volume")
  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
  |> sort(columns: ["_time"])
"""
    try:
        df = db.query_dataframe(flux)
        if df.empty or len(df) < 7:
            logger.warning(f"Insufficient data for inflation: {item_name}")
            return None

        prices = df["median_price"].dropna()
        volumes = df["volume"].dropna() if "volume" in df.columns else pd.Series([0])

        avg_7d = float(prices.tail(7).mean())
        avg_30d = float(prices.mean())

        if avg_30d == 0:
            return None

        deviation_pct = round((avg_7d - avg_30d) / avg_30d * 100, 2)
        tier, label = get_alert_tier(deviation_pct)

        # Superflag volume cross-check
        volume_confirmed = False
        is_anomaly = False

        if tier == 3:
            avg_volume_30d = float(volumes.mean())
            recent_volume = float(volumes.tail(7).mean())
            if avg_volume_30d > 0:
                volume_ratio = recent_volume / avg_volume_30d
                if volume_ratio >= 1.5:
                    volume_confirmed = True
                else:
                    # Price spike but volume is normal — likely data anomaly
                    is_anomaly = True
                    tier = 0
                    label = "⚠️ possible data anomaly"

        return InflationResult(
            item_name=item_name,
            avg_7d=round(avg_7d, 4),
            avg_30d=round(avg_30d, 4),
            deviation_pct=deviation_pct,
            alert_tier=tier,
            alert_label=label,
            volume_confirmed=volume_confirmed,
            is_anomaly=is_anomaly,
        )

    except Exception as e:
        logger.error(f"Inflation calculation failed for {item_name}: {e}")
        return None