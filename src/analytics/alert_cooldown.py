"""
Alert Cooldown Manager.
Persists alert state to disk so cooldowns survive bot restarts.
Per item: once an alert fires at a given tier, do not re-alert for the same
tier until the price drops below the lower threshold and re-crosses it.
State stored in data/alerts/cooldown_state.json.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from src.analytics.models import AlertState

logger = logging.getLogger(__name__)

COOLDOWN_FILE = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "alerts", "cooldown_state.json"
)


class AlertCooldownManager:
    def __init__(self, state_file: str = COOLDOWN_FILE):
        self.state_file = os.path.abspath(state_file)
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
        self._state: dict[str, AlertState] = self._load()

    def _load(self) -> dict[str, AlertState]:
        if not os.path.exists(self.state_file):
            return {}
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                raw = json.load(f)
            return {
                name: AlertState(
                    item_name=name,
                    last_inflation_tier=data.get("last_inflation_tier", 0),
                    last_spike_tier=data.get("last_spike_tier", 0),
                    last_alert_time=data.get("last_alert_time"),
                )
                for name, data in raw.items()
            }
        except Exception as e:
            logger.warning(f"Could not load cooldown state: {e}")
            return {}

    def _save(self) -> None:
        try:
            serialisable = {
                name: {
                    "last_inflation_tier": state.last_inflation_tier,
                    "last_spike_tier": state.last_spike_tier,
                    "last_alert_time": state.last_alert_time,
                }
                for name, state in self._state.items()
            }
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(serialisable, f, indent=2)
        except Exception as e:
            logger.error(f"Could not save cooldown state: {e}")

    def _get_state(self, item_name: str) -> AlertState:
        if item_name not in self._state:
            self._state[item_name] = AlertState(item_name=item_name)
        return self._state[item_name]

    def should_alert_inflation(self, item_name: str, new_tier: int) -> bool:
        """
        Returns True if an inflation alert should fire.
        Fires if new_tier is higher than the last recorded tier.
        Resets if new_tier has dropped back to 0.
        """
        state = self._get_state(item_name)

        if new_tier == 0:
            if state.last_inflation_tier > 0:
                # Price has cooled — reset cooldown
                state.last_inflation_tier = 0
                self._save()
            return False

        if new_tier > state.last_inflation_tier:
            state.last_inflation_tier = new_tier
            state.last_alert_time = datetime.now(timezone.utc).isoformat()
            self._save()
            return True

        return False

    def should_alert_spike(self, item_name: str, new_tier: int) -> bool:
        """
        Returns True if a spike alert should fire.
        Same logic as inflation cooldown but tracked independently.
        """
        state = self._get_state(item_name)

        if new_tier == 0:
            if state.last_spike_tier > 0:
                state.last_spike_tier = 0
                self._save()
            return False

        if new_tier > state.last_spike_tier:
            state.last_spike_tier = new_tier
            state.last_alert_time = datetime.now(timezone.utc).isoformat()
            self._save()
            return True

        return False

    def reset_item(self, item_name: str) -> None:
        """Reset all alert state for an item (e.g. when untracked)."""
        if item_name in self._state:
            del self._state[item_name]
            self._save()