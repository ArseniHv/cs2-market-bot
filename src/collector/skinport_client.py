"""
Client for Skinport's public /v1/items endpoint.
Returns all CS2 items with prices in a single request — no API key required.
Used as the primary bulk price source for both tracked item analytics
and market-wide spike discovery.

Rate limit: 8 requests per 5 minutes. Our 30-min cycle uses 1.
Prices returned in USD. Brotli compression required by the endpoint.
"""

import json
import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

SKINPORT_ITEMS_URL = "https://api.skinport.com/v1/items"

LAST_PRICES_FILE = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "last_prices.json"
)
MARKET_MOVERS_FILE = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "market_movers.json"
)


class SkinportClient:
    """
    Fetches all CS2 item prices from Skinport in one bulk request.
    Also handles market-wide mover detection between cycles.
    """

    def __init__(self, timeout: int = 60):
        self.timeout = timeout
        self.last_prices_file = os.path.abspath(LAST_PRICES_FILE)
        self.market_movers_file = os.path.abspath(MARKET_MOVERS_FILE)

    def fetch_all_prices(self) -> dict[str, dict]:
        """
        Fetch all CS2 items from Skinport.
        Returns a dict keyed by market_hash_name:
        {
            "AK-47 | Redline (Field-Tested)": {
                "median_price": 12.50,
                "min_price": 11.00,
                "max_price": 14.00,
                "mean_price": 12.30,
                "suggested_price": 12.80,
                "volume": 25,
            },
            ...
        }
        Returns empty dict on failure.
        """
        logger.info("Fetching all CS2 prices from Skinport...")

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(
                    SKINPORT_ITEMS_URL,
                    params={"app_id": 730, "currency": "USD", "tradable": 0},
                    headers={"Accept-Encoding": "br"},
                )
                response.raise_for_status()
                raw = response.json()

            result = {}
            for item in raw:
                name = item.get("market_hash_name")
                if not name:
                    continue

                # Skip items with no pricing data at all
                median = item.get("median_price")
                suggested = item.get("suggested_price")
                price = median or suggested
                if not price:
                    continue

                result[name] = {
                    "median_price": round(float(price), 4),
                    "min_price": round(float(item["min_price"]), 4)
                    if item.get("min_price")
                    else round(float(price), 4),
                    "max_price": round(float(item["max_price"]), 4)
                    if item.get("max_price")
                    else round(float(price), 4),
                    "mean_price": round(float(item["mean_price"]), 4)
                    if item.get("mean_price")
                    else round(float(price), 4),
                    "suggested_price": round(float(item["suggested_price"]), 4)
                    if item.get("suggested_price")
                    else round(float(price), 4),
                    "volume": int(item.get("quantity", 0)),
                }

            logger.info(f"Fetched {len(result)} priced items from Skinport.")
            return result

        except httpx.HTTPStatusError as e:
            logger.error(f"Skinport HTTP error: {e.response.status_code}")
            return {}
        except Exception as e:
            logger.error(f"Skinport fetch failed: {e}")
            return {}

    def get_item_price(
        self, market_hash_name: str, all_prices: Optional[dict] = None
    ) -> Optional[dict]:
        """
        Extract and normalise price data for a single tracked item.
        Pass all_prices from a prior fetch_all_prices() call to avoid re-fetching.

        Returns dict matching the InfluxDB skin_prices schema:
        {
            "market_hash_name": str,
            "median_price": float,
            "volume": int,
            "lowest_sell": float,
            "highest_buy": float,
            "spread": float,
        }
        """
        prices = all_prices
        if prices is None:
            prices = self.fetch_all_prices()

        item = prices.get(market_hash_name)
        if not item:
            logger.warning(f"Item not found in Skinport data: {market_hash_name}")
            return None

        lowest_sell = item["min_price"]
        highest_buy = round(item["median_price"] * 0.95, 4)
        spread = round(lowest_sell - highest_buy, 4)

        return {
            "market_hash_name": market_hash_name,
            "median_price": item["median_price"],
            "volume": item["volume"],
            "lowest_sell": lowest_sell,
            "highest_buy": highest_buy,
            "spread": spread,
        }

    # ------------------------------------------------------------------
    # Market-wide mover detection (powers /discover command)
    # ------------------------------------------------------------------

    def load_last_prices(self) -> dict:
        """Load the previous cycle's full price snapshot from disk."""
        if not os.path.exists(self.last_prices_file):
            return {}
        try:
            with open(self.last_prices_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Could not load last prices file: {e}")
            return {}

    def save_last_prices(self, prices: dict) -> None:
        """Persist the current cycle's full price snapshot to disk."""
        try:
            with open(self.last_prices_file, "w", encoding="utf-8") as f:
                json.dump(prices, f)
        except Exception as e:
            logger.error(f"Could not save last prices file: {e}")

    def detect_movers(
        self, current: dict, previous: dict, min_pct: float = 5.0, top_n: int = 20
    ) -> list[dict]:
        """
        Compare current prices to previous cycle and find the biggest movers.
        Only includes items with at least min_pct% change.
        Returns top_n movers sorted by absolute % change descending.
        """
        movers = []

        for name, curr_data in current.items():
            prev_data = previous.get(name)
            if not prev_data:
                continue

            prev_price = prev_data.get("median_price", 0)
            curr_price = curr_data.get("median_price", 0)

            if not prev_price or not curr_price:
                continue

            pct_change = ((curr_price - prev_price) / prev_price) * 100

            if abs(pct_change) >= min_pct:
                movers.append(
                    {
                        "market_hash_name": name,
                        "prev_price": prev_price,
                        "curr_price": curr_price,
                        "pct_change": round(pct_change, 2),
                        "volume": curr_data.get("volume", 0),
                    }
                )

        movers.sort(key=lambda x: abs(x["pct_change"]), reverse=True)
        return movers[:top_n]

    def save_market_movers(self, movers: list) -> None:
        """Persist the current cycle's top movers to disk for /discover command."""
        try:
            with open(self.market_movers_file, "w", encoding="utf-8") as f:
                json.dump(movers, f, indent=2)
        except Exception as e:
            logger.error(f"Could not save market movers file: {e}")

    def load_market_movers(self) -> list:
        """Load the most recently detected market movers."""
        if not os.path.exists(self.market_movers_file):
            return []
        try:
            with open(self.market_movers_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Could not load market movers: {e}")
            return []