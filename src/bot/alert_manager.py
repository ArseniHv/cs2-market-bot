"""
Alert Manager.
Runs after each collection cycle, executes the analytics engine,
and fires push notifications to Telegram for any items that cross alert thresholds.
Tracks last collection time for the /status command.
"""

import json
import logging
import os
from datetime import datetime, timezone

from src.analytics.engine import AnalyticsEngine
from src.bot.formatters import format_alert_message
from src.collector.item_manager import ItemManager
from src.db.influx_client import InfluxClientWrapper

logger = logging.getLogger(__name__)

STATUS_FILE = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "bot_status.json"
)


class AlertManager:
    def __init__(
        self,
        db: InfluxClientWrapper,
        item_manager: ItemManager,
        bot_app,
        chat_id: int,
    ):
        self.db = db
        self.item_manager = item_manager
        self.bot_app = bot_app
        self.chat_id = chat_id
        self.engine = AnalyticsEngine(db, item_manager)
        self.status_file = os.path.abspath(STATUS_FILE)
        self._alerts_enabled = self._load_alerts_enabled()

    # ------------------------------------------------------------------
    # Alert toggle state
    # ------------------------------------------------------------------

    def _load_alerts_enabled(self) -> bool:
        if not os.path.exists(self.status_file):
            return True
        try:
            with open(self.status_file, "r") as f:
                return json.load(f).get("alerts_enabled", True)
        except Exception:
            return True

    def set_alerts_enabled(self, enabled: bool) -> None:
        self._alerts_enabled = enabled
        self._save_status()

    def alerts_enabled(self) -> bool:
        return self._alerts_enabled

    # ------------------------------------------------------------------
    # Collection time tracking
    # ------------------------------------------------------------------

    def _save_status(self, last_collection: str | None = None) -> None:
        try:
            existing = {}
            if os.path.exists(self.status_file):
                with open(self.status_file, "r") as f:
                    existing = json.load(f)
            existing["alerts_enabled"] = self._alerts_enabled
            if last_collection:
                existing["last_collection"] = last_collection
            with open(self.status_file, "w") as f:
                json.dump(existing, f, indent=2)
        except Exception as e:
            logger.error(f"Could not save bot status: {e}")

    def get_last_collection(self) -> str | None:
        try:
            if os.path.exists(self.status_file):
                with open(self.status_file, "r") as f:
                    return json.load(f).get("last_collection")
        except Exception:
            pass
        return None

    def record_collection(self) -> None:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        self._save_status(last_collection=now)

    # ------------------------------------------------------------------
    # Main alert loop
    # ------------------------------------------------------------------

    async def run_alerts(self) -> int:
        """
        Run analytics on all tracked items and fire Telegram alerts.
        Called after each collection cycle.
        Returns number of alerts fired.
        """
        self.record_collection()

        if not self._alerts_enabled:
            logger.info("Push alerts are disabled — skipping alert check.")
            return 0

        results = self.engine.run_all()
        alerts = self.engine.get_alerts(results)

        if not alerts:
            logger.info("No alerts to fire this cycle.")
            return 0

        fired = 0
        for alert in alerts:
            try:
                message = format_alert_message(alert)
                await self.bot_app.bot.send_message(
                    chat_id=self.chat_id,
                    text=message,
                    parse_mode="MarkdownV2",
                )
                fired += 1
                logger.info(
                    f"Alert fired: {alert['item_name']} — {alert['label']}"
                )
            except Exception as e:
                logger.error(
                    f"Failed to send alert for {alert['item_name']}: {e}"
                )

        logger.info(f"Alert cycle complete — {fired} alerts fired.")
        return fired