"""
ML Price Prediction Service using Facebook Prophet.
Fetches historical price data from InfluxDB, trains Prophet,
and generates a 7-day forecast with confidence intervals.

Rules:
- Minimum 30 data points required before prediction is allowed
- Model is retrained fresh on every /predict call — not persisted to disk
- Returns both a forecast dict and a Matplotlib chart as BytesIO PNG
"""

import io
import logging
import warnings

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from influxdb_client.client.warnings import MissingPivotFunction

logging.getLogger("prophet").setLevel(logging.WARNING)
logging.getLogger("cmdstanpy").setLevel(logging.WARNING)
warnings.filterwarnings("ignore", message=".*Importing plotly failed.*")
warnings.simplefilter("ignore", MissingPivotFunction)
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

logger = logging.getLogger(__name__)

MINIMUM_DATA_POINTS = 30


class PricePredictor:
    def __init__(self, db):
        self.db = db

    def _fetch_price_history(
        self,
        item_name: str,
        bucket: str = "cs2_market",
    ) -> pd.DataFrame:
        """
        Fetch all available price history for an item from InfluxDB.
        Returns a DataFrame with columns: ds (datetime), y (price).
        Prophet requires exactly these column names.
        """
        flux = f"""
from(bucket: "{bucket}")
  |> range(start: -365d)
  |> filter(fn: (r) => r._measurement == "skin_prices")
  |> filter(fn: (r) => r.item_name == "{item_name}")
  |> filter(fn: (r) => r._field == "median_price")
  |> sort(columns: ["_time"])
"""
        df = self.db.query_dataframe(flux)
        if df.empty:
            return pd.DataFrame()

        result = pd.DataFrame()
        result["ds"] = pd.to_datetime(df["_time"]).dt.tz_localize(None)
        result["y"] = df["_value"].astype(float)
        result = result.dropna().sort_values("ds").reset_index(drop=True)
        return result

    def predict(
        self,
        item_name: str,
        forecast_days: int = 7,
        bucket: str = "cs2_market",
    ) -> dict:
        """
        Train Prophet on historical data and generate a price forecast.

        Returns a dict:
        {
            "success": bool,
            "error": str | None,
            "item_name": str,
            "data_points": int,
            "forecast_price": float,
            "confidence_low": float,
            "confidence_high": float,
            "chart": io.BytesIO | None,
            "forecast_df": pd.DataFrame,
        }
        """
        history = self._fetch_price_history(item_name, bucket)
        data_points = len(history)

        if data_points < MINIMUM_DATA_POINTS:
            return {
                "success": False,
                "error": (
                    f"Not enough data to predict\\. "
                    f"Need at least {MINIMUM_DATA_POINTS} price records "
                    f"— currently have {data_points}\\."
                ),
                "item_name": item_name,
                "data_points": data_points,
                "forecast_price": None,
                "confidence_low": None,
                "confidence_high": None,
                "chart": None,
                "forecast_df": None,
            }

        logger.info(
            f"Training Prophet for '{item_name}' "
            f"on {data_points} data points..."
        )

        try:
            from prophet import Prophet

            model = Prophet(
                daily_seasonality=False,
                weekly_seasonality=True,
                yearly_seasonality=True,
                changepoint_prior_scale=0.05,
                interval_width=0.80,
            )
            model.fit(history)

            future = model.make_future_dataframe(
                periods=forecast_days,
                freq="h",
                include_history=True,
            )
            forecast = model.predict(future)

            future_only = forecast[forecast["ds"] > history["ds"].max()]
            if future_only.empty:
                raise ValueError("Prophet returned empty future forecast.")

            last_row = future_only.iloc[-1]
            forecast_price = round(float(last_row["yhat"]), 2)
            confidence_low = round(float(last_row["yhat_lower"]), 2)
            confidence_high = round(float(last_row["yhat_upper"]), 2)

            logger.info(
                f"Forecast for '{item_name}': "
                f"${forecast_price:.2f} "
                f"(${confidence_low:.2f} — ${confidence_high:.2f})"
            )

            chart = self._generate_forecast_chart(
                item_name=item_name,
                history=history,
                forecast=forecast,
                forecast_days=forecast_days,
            )

            return {
                "success": True,
                "error": None,
                "item_name": item_name,
                "data_points": data_points,
                "forecast_price": forecast_price,
                "confidence_low": confidence_low,
                "confidence_high": confidence_high,
                "chart": chart,
                "forecast_df": future_only[
                    ["ds", "yhat", "yhat_lower", "yhat_upper"]
                ].reset_index(drop=True),
            }

        except Exception as e:
            logger.error(f"Prophet prediction failed for '{item_name}': {e}")
            return {
                "success": False,
                "error": f"Prediction failed: {str(e)}",
                "item_name": item_name,
                "data_points": data_points,
                "forecast_price": None,
                "confidence_low": None,
                "confidence_high": None,
                "chart": None,
                "forecast_df": None,
            }

    def _generate_forecast_chart(
        self,
        item_name: str,
        history: pd.DataFrame,
        forecast: pd.DataFrame,
        forecast_days: int,
    ) -> io.BytesIO | None:
        """
        Generate a Matplotlib chart showing:
        - Historical prices (last 30 days)
        - Prophet forecast line
        - Confidence interval band
        """
        try:
            cutoff = history["ds"].max() - pd.Timedelta(days=30)
            recent_history = history[history["ds"] >= cutoff]

            future_start = history["ds"].max()
            forecast_future = forecast[forecast["ds"] > future_start]
            forecast_overlap = forecast[
                (forecast["ds"] >= cutoff) &
                (forecast["ds"] <= future_start)
            ]

            fig, ax = plt.subplots(figsize=(11, 4.5))
            fig.patch.set_facecolor("#1a1a2e")
            ax.set_facecolor("#16213e")

            ax.plot(
                recent_history["ds"],
                recent_history["y"],
                color="#e94560",
                linewidth=1.8,
                label="Historical price",
                zorder=3,
            )
            ax.plot(
                forecast_overlap["ds"],
                forecast_overlap["yhat"],
                color="#f5a623",
                linewidth=1.2,
                linestyle="--",
                alpha=0.7,
                label="Model fit",
            )
            ax.plot(
                forecast_future["ds"],
                forecast_future["yhat"],
                color="#00d4ff",
                linewidth=2.0,
                label=f"{forecast_days}d forecast",
                zorder=3,
            )
            ax.fill_between(
                forecast_future["ds"],
                forecast_future["yhat_lower"],
                forecast_future["yhat_upper"],
                alpha=0.20,
                color="#00d4ff",
                label="80% confidence interval",
            )
            ax.axvline(
                x=future_start,
                color="#666688",
                linewidth=1.0,
                linestyle=":",
                alpha=0.8,
            )

            ax.set_title(
                f"{item_name} — {forecast_days}-day price forecast",
                color="white",
                fontsize=10,
                pad=10,
            )
            ax.set_ylabel("Price (USD)", color="#aaaaaa", fontsize=9)
            ax.tick_params(colors="#aaaaaa", labelsize=8)
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
            ax.xaxis.set_major_locator(mdates.AutoDateLocator())
            plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha="right")

            for spine in ax.spines.values():
                spine.set_edgecolor("#444466")

            ax.legend(
                facecolor="#1a1a2e",
                edgecolor="#444466",
                labelcolor="white",
                fontsize=7,
                loc="upper left",
            )
            ax.grid(True, color="#2a2a4a", linewidth=0.5, alpha=0.7)
            plt.tight_layout()

            buf = io.BytesIO()
            plt.savefig(
                buf,
                format="png",
                dpi=120,
                bbox_inches="tight",
                facecolor=fig.get_facecolor(),
            )
            buf.seek(0)
            plt.close(fig)
            return buf

        except Exception as e:
            logger.error(f"Forecast chart generation failed: {e}")
            return None