"""
Manages the list of tracked CS2 items.
Reads from and writes to data/items.json.
All items are identified by market_hash_name throughout the codebase.
"""

import json
import os
from typing import Optional

ITEMS_FILE = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "items.json"
)


class ItemManager:
    def __init__(self, items_file: str = ITEMS_FILE):
        self.items_file = os.path.abspath(items_file)
        self._data = self._load()

    def _load(self) -> dict:
        with open(self.items_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save(self) -> None:
        with open(self.items_file, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

    def get_all(self) -> list[dict]:
        """Return the full list of tracked items."""
        return self._data.get("items", [])

    def get_names(self) -> list[str]:
        """Return just the market_hash_name of every tracked item."""
        return [item["market_hash_name"] for item in self.get_all()]

    def get_item(self, market_hash_name: str) -> Optional[dict]:
        """Return a single item dict by market_hash_name, or None if not found."""
        for item in self.get_all():
            if item["market_hash_name"] == market_hash_name:
                return item
        return None

    def add_item(
        self,
        market_hash_name: str,
        category: str = "other",
        float_range: str = "ft",
    ) -> bool:
        """
        Add an item to the tracked list.
        Returns True if added, False if already present.
        """
        if self.get_item(market_hash_name):
            return False
        self._data["items"].append(
            {
                "market_hash_name": market_hash_name,
                "category": category,
                "float_range": float_range,
            }
        )
        self._save()
        return True

    def remove_item(self, market_hash_name: str) -> bool:
        """
        Remove an item from the tracked list.
        Returns True if removed, False if not found.
        """
        items = self.get_all()
        filtered = [i for i in items if i["market_hash_name"] != market_hash_name]
        if len(filtered) == len(items):
            return False
        self._data["items"] = filtered
        self._save()
        return True

    def count(self) -> int:
        return len(self.get_all())