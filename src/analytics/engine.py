"""
Analytics Engine entry point.
Runs all analytics components for all tracked items and returns
structured results ready for the alert manager and bot commands.
"""

import logging
from typing import Optional

from src.analytics.alert_cooldown import AlertCooldownManager
from src.analytics.category import calculate_category
from src.analytics.inflation import calculate_inflation
from src.analytics.liquidity import calculate_liquidity
from src.analytics.models import (
    CategoryResult,
    InflationResult,
    LiquidityResult,
    SpikeResult,
    TrendResult,
)
from src.analytics.spike import calculate_spike
from src.analytics.trend import calculate_trend
from src.collector.item_manager import ItemManager
from src.db.influx_client import InfluxClientWrapper

logger = logging.getLogger(__name__)


class AnalyticsEngine:
    def __init__(self, db: InfluxClientWrapper, item_manager: ItemManager):
        self.db = db
        self.item_manager = item_manager
        self.cooldown = AlertCooldownManager()

    def run_item(self, item_name: str) -> dict:
        """
        Run all analytics for a single item.
        Returns a dict with all result objects.
        """
        return {
            "liquidity": calculate_liquidity(item_name, self.db),
            "inflation": calculate_inflation(item_name, self.db),
            "spike": calculate_spike(item_name, self.db),
            "trend": calculate_trend(item_name, self.db),
        }

    def run_all(self) -> dict[str, dict]:
        """
        Run all analytics for every tracked item.
        Returns a dict keyed by item_name.
        """
        results = {}
        for item in self.item_manager.get_all():
            name = item["market_hash_name"]
            logger.info(f"Running analytics for: {name}")
            results[name] = self.run_item(name)
        return results

    def get_alerts(self, results: dict[str, dict]) -> list[dict]:
        """
        Filter analytics results through the cooldown manager.
        Returns a list of alert dicts ready for the Telegram alert manager.
        """
        alerts = []

        for item_name, item_results in results.items():
            inflation: Optional[InflationResult] = item_results.get("inflation")
            spike: Optional[SpikeResult] = item_results.get("spike")
            trend: Optional[TrendResult] = item_results.get("trend")

            trend_label = trend.classification if trend else "unknown"

            # Inflation alert
            if inflation and inflation.alert_tier > 0 and not inflation.is_anomaly:
                if self.cooldown.should_alert_inflation(
                    item_name, inflation.alert_tier
                ):
                    alerts.append({
                        "item_name": item_name,
                        "type": "inflation",
                        "tier": inflation.alert_tier,
                        "label": inflation.alert_label,
                        "deviation_pct": inflation.deviation_pct,
                        "current_price": inflation.avg_7d,
                        "avg_30d": inflation.avg_30d,
                        "volume_confirmed": inflation.volume_confirmed,
                        "trend": trend_label,
                    })

            # Data anomaly warning
            if inflation and inflation.is_anomaly:
                alerts.append({
                    "item_name": item_name,
                    "type": "anomaly",
                    "tier": 0,
                    "label": "⚠️ possible data anomaly",
                    "deviation_pct": inflation.deviation_pct,
                    "current_price": inflation.avg_7d,
                    "avg_30d": inflation.avg_30d,
                    "volume_confirmed": False,
                    "trend": trend_label,
                })

            # Spike alert
            if spike and spike.alert_tier > 0:
                if self.cooldown.should_alert_spike(item_name, spike.alert_tier):
                    alerts.append({
                        "item_name": item_name,
                        "type": "spike",
                        "tier": spike.alert_tier,
                        "label": spike.alert_label,
                        "deviation_pct": spike.deviation_pct,
                        "current_price": spike.current_price,
                        "avg_30d": spike.rolling_avg,
                        "volume_confirmed": False,
                        "trend": trend_label,
                    })

        return alerts

    def get_category(self, category: str) -> Optional[CategoryResult]:
        return calculate_category(category, self.db, self.item_manager)

    def get_top_movers(self, n: int = 5) -> list[dict]:
        """
        Return the top N tracked items by absolute price deviation (inflation).
        Used by the /summary command.
        """
        movers = []
        for item in self.item_manager.get_all():
            name = item["market_hash_name"]
            inflation = calculate_inflation(name, self.db)
            if inflation:
                movers.append({
                    "item_name": name,
                    "deviation_pct": inflation.deviation_pct,
                    "avg_7d": inflation.avg_7d,
                    "avg_30d": inflation.avg_30d,
                    "alert_label": inflation.alert_label,
                })

        movers.sort(key=lambda x: abs(x["deviation_pct"]), reverse=True)
        return movers[:n]