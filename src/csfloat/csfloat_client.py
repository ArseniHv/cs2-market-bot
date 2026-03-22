"""
CSFloat API client.
Used exclusively for the /float command — fetches current listings
for an item and groups them by float range with average pricing.

API docs: https://docs.csfloat.com/
Auth: Authorization header with API key.
Prices returned in cents — always divide by 100 for USD.
"""

import logging
import os
from typing import Optional
from urllib.parse import quote

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

CSFLOAT_API_BASE = os.getenv("CSFLOAT_API_BASE", "https://csfloat.com/api/v1")
CSFLOAT_API_KEY = os.getenv("CSFLOAT_API_KEY")

# Float range boundaries matching Steam's wear conditions
FLOAT_RANGES = {
    "fn": (0.00, 0.07),   # Factory New
    "mw": (0.07, 0.15),   # Minimal Wear
    "ft": (0.15, 0.38),   # Field-Tested
    "ww": (0.38, 0.45),   # Well-Worn
    "bs": (0.45, 1.00),   # Battle-Scarred
}

FLOAT_LABELS = {
    "fn": "Factory New",
    "mw": "Minimal Wear",
    "ft": "Field-Tested",
    "ww": "Well-Worn",
    "bs": "Battle-Scarred",
    "none": "N/A",
}


def classify_float(float_value: float) -> str:
    """Map a float value to its wear tier abbreviation."""
    for tier, (low, high) in FLOAT_RANGES.items():
        if low <= float_value < high:
            return tier
    return "bs"  # Edge case: exactly 1.0


class CSFloatClient:
    def __init__(self, timeout: int = 30):
        if not CSFLOAT_API_KEY:
            raise ValueError("CSFLOAT_API_KEY is not set in environment.")
        self.timeout = timeout
        self.headers = {
            "Authorization": CSFLOAT_API_KEY,
            "Content-Type": "application/json",
        }

    def fetch_listings(
        self,
        market_hash_name: str,
        limit: int = 50,
    ) -> list[dict]:
        """
        Fetch current buy-now listings for an item from CSFloat.
        Returns a list of listing dicts, empty list on failure.
        Fetches up to `limit` listings (max 50 per CSFloat API).
        """
        params = {
            "market_hash_name": market_hash_name,
            "type": "buy_now",
            "limit": min(limit, 50),
            "sort_by": "lowest_price",
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(
                    f"{CSFLOAT_API_BASE}/listings",
                    headers=self.headers,
                    params=params,
                )
                response.raise_for_status()
                data = response.json()

            listings = data if isinstance(data, list) else data.get("data", [])
            logger.info(
                f"Fetched {len(listings)} CSFloat listings for: {market_hash_name}"
            )
            return listings

        except httpx.HTTPStatusError as e:
            logger.error(
                f"CSFloat HTTP {e.response.status_code} for {market_hash_name}: "
                f"{e.response.text[:200]}"
            )
            return []
        except Exception as e:
            logger.error(f"CSFloat fetch failed for {market_hash_name}: {e}")
            return []

    def group_by_float_range(
        self, listings: list[dict]
    ) -> dict[str, dict]:
        """
        Group listings by float range and calculate per-range stats.

        Returns a dict keyed by float range abbreviation:
        {
            "fn": {
                "label": "Factory New",
                "count": 3,
                "avg_price": 45.20,
                "min_price": 42.00,
                "max_price": 49.50,
                "avg_float": 0.034,
            },
            ...
        }
        Only includes ranges that have at least one listing.
        """
        groups: dict[str, list] = {tier: [] for tier in FLOAT_RANGES}

        for listing in listings:
            item = listing.get("item", {})
            float_value = item.get("float_value")
            price_cents = listing.get("price")

            if float_value is None or price_cents is None:
                continue

            tier = classify_float(float(float_value))
            groups[tier].append({
                "price": float(price_cents) / 100,
                "float_value": float(float_value),
            })

        result = {}
        for tier, entries in groups.items():
            if not entries:
                continue

            prices = [e["price"] for e in entries]
            floats = [e["float_value"] for e in entries]

            result[tier] = {
                "label": FLOAT_LABELS[tier],
                "count": len(entries),
                "avg_price": round(sum(prices) / len(prices), 2),
                "min_price": round(min(prices), 2),
                "max_price": round(max(prices), 2),
                "avg_float": round(sum(floats) / len(floats), 4),
            }

        return result

    def find_best_value_range(
        self,
        grouped: dict[str, dict],
        historical_avgs: dict[str, float],
    ) -> Optional[str]:
        """
        Find the float range offering the best value relative to its
        historical average price. Returns the tier abbreviation or None.

        historical_avgs: {tier: avg_price} from InfluxDB item_metadata.
        Falls back to comparing ranges against each other if no history.
        """
        if not grouped:
            return None

        if historical_avgs:
            best_tier = None
            best_ratio = float("inf")
            for tier, data in grouped.items():
                hist_avg = historical_avgs.get(tier)
                if hist_avg and hist_avg > 0:
                    ratio = data["avg_price"] / hist_avg
                    if ratio < best_ratio:
                        best_ratio = ratio
                        best_tier = tier
            if best_tier:
                return best_tier

        # Fallback: lowest price-to-float-quality ratio
        # (cheapest relative to float range position)
        tier_order = ["fn", "mw", "ft", "ww", "bs"]
        for tier in tier_order:
            if tier in grouped:
                return tier

        return None