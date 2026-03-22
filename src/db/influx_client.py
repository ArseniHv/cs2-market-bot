import os
from datetime import datetime, timezone
from typing import Optional

from dotenv import load_dotenv
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

load_dotenv()

INFLUXDB_URL = os.getenv("INFLUXDB_URL", "http://localhost:8086")
INFLUXDB_TOKEN = os.getenv("INFLUXDB_TOKEN")
INFLUXDB_ORG = os.getenv("INFLUXDB_ORG", "cs2bot")
INFLUXDB_BUCKET = os.getenv("INFLUXDB_BUCKET", "cs2_market")


class InfluxClientWrapper:
    """
    Thin wrapper around the InfluxDB Python client.
    Provides clean write and query helpers used throughout the project.
    """

    def __init__(self):
        if not INFLUXDB_TOKEN:
            raise ValueError("INFLUXDB_TOKEN is not set in environment.")

        self._client = InfluxDBClient(
            url=INFLUXDB_URL,
            token=INFLUXDB_TOKEN,
            org=INFLUXDB_ORG,
        )
        self._write_api = self._client.write_api(write_options=SYNCHRONOUS)
        self._query_api = self._client.query_api()

    # ------------------------------------------------------------------
    # Write helpers
    # ------------------------------------------------------------------

    def write_skin_price(
        self,
        item_name: str,
        category: str,
        float_range: str,
        median_price: float,
        volume: int,
        lowest_sell: float,
        highest_buy: float,
        spread: float,
        timestamp: Optional[datetime] = None,
    ) -> None:
        """Write a single skin_prices data point to InfluxDB."""
        ts = timestamp or datetime.now(timezone.utc)

        point = (
            Point("skin_prices")
            .tag("item_name", item_name)
            .tag("category", category)
            .tag("float_range", float_range)
            .field("median_price", float(median_price))
            .field("volume", int(volume))
            .field("lowest_sell", float(lowest_sell))
            .field("highest_buy", float(highest_buy))
            .field("spread", float(spread))
            .time(ts, "s")
        )

        self._write_api.write(bucket=INFLUXDB_BUCKET, record=point)

    def write_item_metadata(
        self,
        item_name: str,
        float_value: float,
        category: str,
        is_tracked: bool,
    ) -> None:
        """Write or update metadata for a tracked item."""
        point = (
            Point("item_metadata")
            .tag("item_name", item_name)
            .field("float_value", float(float_value))
            .field("category", category)
            .field("is_tracked", bool(is_tracked))
            .time(datetime.now(timezone.utc), "s")
        )

        self._write_api.write(bucket=INFLUXDB_BUCKET, record=point)

    def write_float_range_price(
        self,
        item_name: str,
        float_range: str,
        avg_price: float,
        min_price: float,
        max_price: float,
        avg_float: float,
        listing_count: int,
    ) -> None:
        """Write float-range price data point to item_metadata measurement."""
        from datetime import datetime, timezone
        point = (
            Point("item_metadata")
            .tag("item_name", item_name)
            .tag("float_range", float_range)
            .field("avg_price", float(avg_price))
            .field("min_price", float(min_price))
            .field("max_price", float(max_price))
            .field("avg_float", float(avg_float))
            .field("listing_count", int(listing_count))
            .time(datetime.now(timezone.utc), "s")
        )
        self._write_api.write(bucket=INFLUXDB_BUCKET, record=point)

    def get_float_range_historical_avgs(
        self, item_name: str
    ) -> dict:
        """
        Fetch historical average prices per float range for an item.
        Returns dict keyed by float range abbreviation.
        """
        flux = f"""
from(bucket: "{INFLUXDB_BUCKET}")
  |> range(start: -30d)
  |> filter(fn: (r) => r._measurement == "item_metadata")
  |> filter(fn: (r) => r.item_name == "{item_name}")
  |> filter(fn: (r) => r._field == "avg_price")
  |> group(columns: ["float_range"])
  |> mean()
"""
        records = self.query(flux)
        result = {}
        for record in records:
            tier = record.values.get("float_range")
            if tier:
                result[tier] = round(float(record.get_value()), 2)
        return result

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def query(self, flux_query: str) -> list:
        """
        Execute a raw Flux query and return a list of FluxRecord objects.
        Always structure Flux queries as:
          filter by _measurement → filter by tags → apply time range
        """
        tables = self._query_api.query(flux_query, org=INFLUXDB_ORG)
        records = []
        for table in tables:
            for record in table.records:
                records.append(record)
        return records

    def query_dataframe(self, flux_query: str):
        """
        Execute a Flux query and return results as a Pandas DataFrame.
        Returns an empty DataFrame if no results found.
        """
        import pandas as pd

        tables = self._query_api.query_data_frame(flux_query, org=INFLUXDB_ORG)

        if isinstance(tables, list):
            if not tables:
                return pd.DataFrame()
            return pd.concat(tables, ignore_index=True)

        return tables if not tables.empty else pd.DataFrame()

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    def ping(self) -> bool:
        """Returns True if InfluxDB is reachable."""
        try:
            self._client.ping()
            return True
        except Exception:
            return False

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()