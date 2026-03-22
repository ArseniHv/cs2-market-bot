"""
Client for Steam Market price history endpoint.
Used only for historical data seeding on first run (--seed flag).
Rate limited to ~20 requests/minute — always delays between requests.
Responses are cached locally to avoid re-fetching during development.
"""

import json
import logging
import os
import time
from typing import Optional
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

STEAM_HISTORY_URL = (
    "https://steamcommunity.com/market/pricehistory/"
    "?appid=730&market_hash_name={item_name}"
)

CACHE_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "cache"
)


class SteamHistoryClient:
    """
    Fetches historical price data from the Steam Market.
    Caches responses to local JSON files to avoid re-fetching.
    """

    def __init__(
        self,
        request_delay: float = 3.0,
        timeout: int = 30,
        cache_dir: str = CACHE_DIR,
    ):
        self.request_delay = request_delay
        self.timeout = timeout
        self.cache_dir = os.path.abspath(cache_dir)
        os.makedirs(self.cache_dir, exist_ok=True)

    def _cache_path(self, market_hash_name: str) -> str:
        """Return the local cache file path for an item."""
        safe_name = market_hash_name.replace(" ", "_").replace("|", "-").replace("/", "-")
        return os.path.join(self.cache_dir, f"{safe_name}.json")

    def _load_cache(self, market_hash_name: str) -> Optional[list]:
        """Load cached price history if it exists."""
        path = self._cache_path(market_hash_name)
        if os.path.exists(path):
            logger.info(f"Loading cached history for: {market_hash_name}")
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return None

    def _save_cache(self, market_hash_name: str, data: list) -> None:
        """Save price history to local cache."""
        path = self._cache_path(market_hash_name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        logger.info(f"Cached history for: {market_hash_name}")

    def fetch_history(
        self,
        market_hash_name: str,
        use_cache: bool = True,
    ) -> Optional[list]:
        """
        Fetch price history for a single item from Steam Market.
        Returns a list of [date_str, price, volume] entries, or None on failure.

        Always respects request_delay to avoid Steam rate limiting.
        Caches responses locally — set use_cache=False to force re-fetch.
        """
        if use_cache:
            cached = self._load_cache(market_hash_name)
            if cached is not None:
                return cached

        encoded_name = quote(market_hash_name, safe="")
        url = STEAM_HISTORY_URL.format(item_name=encoded_name)

        logger.info(f"Fetching Steam history for: {market_hash_name}")
        logger.info(f"Sleeping {self.request_delay}s before request (rate limit)...")
        time.sleep(self.request_delay)

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(url)
                response.raise_for_status()
                data = response.json()

                prices = data.get("prices", [])
                if not prices:
                    logger.warning(f"No price history returned for: {market_hash_name}")
                    return None

                self._save_cache(market_hash_name, prices)
                logger.info(
                    f"Fetched {len(prices)} history points for: {market_hash_name}"
                )
                return prices

        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error fetching history for {market_hash_name}: "
                f"{e.response.status_code}"
            )
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching history for {market_hash_name}: {e}")
            return None

    def parse_history_to_points(self, raw_history: list) -> list[dict]:
        """
        Convert raw Steam history entries to normalised dicts ready for InfluxDB.

        Steam returns entries as: ["Nov 15 2023 01: +0", price_float, volume_str]
        We parse the date and normalise volume to int.
        """
        from datetime import datetime, timezone

        points = []
        for entry in raw_history:
            try:
                date_str = entry[0]  # e.g. "Nov 15 2023 01: +0"
                price = float(entry[1])
                volume = int(float(entry[2]))

                # Strip the trailing timezone part Steam appends
                clean_date = date_str.split(":")[0].strip()
                dt = datetime.strptime(clean_date, "%b %d %Y %H")
                dt = dt.replace(tzinfo=timezone.utc)

                points.append(
                    {
                        "timestamp": dt,
                        "median_price": price,
                        "volume": volume,
                        "lowest_sell": price,
                        "highest_buy": price * 0.95,
                        "spread": price * 0.05,
                    }
                )
            except (IndexError, ValueError, TypeError) as e:
                logger.debug(f"Skipping malformed history entry {entry}: {e}")
                continue

        return points