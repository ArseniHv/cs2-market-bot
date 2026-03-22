"""
Chart generator for the /chart bot command.
Produces a Matplotlib price history chart as a PNG bytes buffer
ready to send via Telegram's send_photo method.
"""

import io
import logging
from datetime import datetime

import matplotlib
matplotlib.use("Agg")  # Non-interactive backend — required for server use
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd

from src.db.influx_client import InfluxClientWrapper

logger = logging.getLogger(__name__)


def generate_price_chart(
    item_name: str,
    db: InfluxClientWrapper,
    days: int = 30,
    bucket: str = "cs2_market",
) -> io.BytesIO | None:
    """
    Generate a price history chart for an item.
    Returns a BytesIO PNG buffer ready for Telegram, or None on failure.
    """
    flux = f"""
from(bucket: "{bucket}")
  |> range(start: -{days}d)
  |> filter(fn: (r) => r._measurement == "skin_prices")
  |> filter(fn: (r) => r.item_name == "{item_name}")
  |> filter(fn: (r) => r._field == "median_price")
  |> sort(columns: ["_time"])
"""
    try:
        df = db.query_dataframe(flux)
        if df.empty or len(df) < 2:
            logger.warning(f"Not enough data to chart: {item_name}")
            return None

        times = pd.to_datetime(df["_time"])
        prices = df["_value"].astype(float)

        fig, ax = plt.subplots(figsize=(10, 4))
        fig.patch.set_facecolor("#1a1a2e")
        ax.set_facecolor("#16213e")

        # Price line
        ax.plot(times, prices, color="#e94560", linewidth=1.8, label="Median price")
        ax.fill_between(times, prices, alpha=0.15, color="#e94560")

        # 7-day moving average
        if len(prices) >= 7:
            ma7 = prices.rolling(window=7, min_periods=1).mean()
            ax.plot(times, ma7, color="#f5a623", linewidth=1.2,
                    linestyle="--", label="7d MA", alpha=0.8)

        # Formatting
        ax.set_title(item_name, color="white", fontsize=11, pad=10)
        ax.set_ylabel("Price (USD)", color="#aaaaaa", fontsize=9)
        ax.tick_params(colors="#aaaaaa", labelsize=8)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
        ax.xaxis.set_major_locator(mdates.AutoDateLocator())
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha="right")

        for spine in ax.spines.values():
            spine.set_edgecolor("#444466")

        ax.legend(
            facecolor="#1a1a2e", edgecolor="#444466",
            labelcolor="white", fontsize=8
        )
        ax.grid(True, color="#2a2a4a", linewidth=0.5, alpha=0.7)

        plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format="png", dpi=120, bbox_inches="tight",
                    facecolor=fig.get_facecolor())
        buf.seek(0)
        plt.close(fig)
        return buf

    except Exception as e:
        logger.error(f"Chart generation failed for {item_name}: {e}")
        return None