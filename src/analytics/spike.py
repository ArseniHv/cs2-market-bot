"""
Spike Detector.
Uses Z-score on a rolling 30-day price window.
If abs(z_score) > 2.0, flags as spike.
Applies the same tiered alert system as inflation detector.
"""

import warnings
from influxdb_client.client.warnings import MissingPivotFunction
warnings.simplefilter("ignore", MissingPivotFunction)
import logging
from typing import Optional

import numpy as np
import pandas as pd

from src.analytics.models import SpikeResult
from src.analytics.tiers import get_alert_tier
from src.db.influx_client import InfluxClientWrapper

logger = logging.getLogger(__name__)


def calculate_spike(
    item_name: str,
    db: InfluxClientWrapper,
    bucket: str = "cs2_market",
) -> Optional[SpikeResult]:
    """
    Detect price spikes for a single item using Z-score on last 30 days.
    Returns None if insufficient data (need at least 5 points for meaningful Z-score).
    """
    flux = f"""
from(bucket: "{bucket}")
  |> range(start: -30d)
  |> filter(fn: (r) => r._measurement == "skin_prices")
  |> filter(fn: (r) => r.item_name == "{item_name}")
  |> filter(fn: (r) => r._field == "median_price")
  |> sort(columns: ["_time"])
"""
    try:
        df = db.query_dataframe(flux)
        if df.empty or len(df) < 5:
            logger.warning(f"Insufficient data for spike detection: {item_name}")
            return None

        prices = df["_value"].dropna().values
        mean = float(np.mean(prices))
        std = float(np.std(prices))

        if std == 0:
            return SpikeResult(
                item_name=item_name,
                z_score=0.0,
                deviation_pct=0.0,
                alert_tier=0,
                alert_label="",
                current_price=float(prices[-1]),
                rolling_avg=mean,
            )

        current_price = float(prices[-1])
        z_score = round((current_price - mean) / std, 4)
        deviation_pct = round((current_price - mean) / mean * 100, 2) if mean else 0.0

        if abs(z_score) > 2.0:
            tier, label = get_alert_tier(deviation_pct)
        else:
            tier, label = 0, ""

        return SpikeResult(
            item_name=item_name,
            z_score=z_score,
            deviation_pct=deviation_pct,
            alert_tier=tier,
            alert_label=label,
            current_price=current_price,
            rolling_avg=round(mean, 4),
        )

    except Exception as e:
        logger.error(f"Spike detection failed for {item_name}: {e}")
        return None