"""
Trend Analyzer.
Uses linear regression slope on the last 14 price points.
Classifications:
  strong uptrend   → slope > +2%
  uptrend          → +0.5% to +2%
  sideways         → -0.5% to +0.5%
  downtrend        → -2% to -0.5%
  strong downtrend → slope < -2%
"""

import warnings
from influxdb_client.client.warnings import MissingPivotFunction
warnings.simplefilter("ignore", MissingPivotFunction)

import logging
from typing import Optional

import numpy as np

from src.analytics.models import TrendResult
from src.db.influx_client import InfluxClientWrapper

logger = logging.getLogger(__name__)


def classify_trend(slope_pct: float) -> str:
    if slope_pct > 2.0:
        return "strong uptrend"
    elif slope_pct > 0.5:
        return "uptrend"
    elif slope_pct >= -0.5:
        return "sideways"
    elif slope_pct >= -2.0:
        return "downtrend"
    else:
        return "strong downtrend"


def calculate_trend(
    item_name: str,
    db: InfluxClientWrapper,
    bucket: str = "cs2_market",
) -> Optional[TrendResult]:
    """
    Calculate trend direction for a single item using last 14 price points.
    Returns None if insufficient data.
    """
    flux = f"""
from(bucket: "{bucket}")
  |> range(start: -30d)
  |> filter(fn: (r) => r._measurement == "skin_prices")
  |> filter(fn: (r) => r.item_name == "{item_name}")
  |> filter(fn: (r) => r._field == "median_price")
  |> sort(columns: ["_time"])
  |> tail(n: 14)
"""
    try:
        df = db.query_dataframe(flux)
        if df.empty or len(df) < 5:
            logger.warning(f"Insufficient data for trend analysis: {item_name}")
            return None

        prices = df["_value"].dropna().values
        x = np.arange(len(prices))

        # Linear regression
        coeffs = np.polyfit(x, prices, 1)
        slope = float(coeffs[0])

        # Express slope as percentage of mean price
        mean_price = float(np.mean(prices))
        slope_pct = round((slope / mean_price) * 100, 4) if mean_price else 0.0
        classification = classify_trend(slope_pct)

        return TrendResult(
            item_name=item_name,
            slope=round(slope_pct, 4),
            classification=classification,
            last_14_prices=list(prices),
        )

    except Exception as e:
        logger.error(f"Trend analysis failed for {item_name}: {e}")
        return None