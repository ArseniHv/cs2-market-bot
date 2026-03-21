"""
Run this script to verify the InfluxDB connection is working.
Writes a dummy data point, reads it back, and confirms the round-trip.

Usage:
    python tests/test_influx_connection.py
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.db.influx_client import InfluxClientWrapper


def test_connection():
    print("Initialising InfluxDB client...")
    db = InfluxClientWrapper()

    print("Pinging InfluxDB...")
    if not db.ping():
        print("❌  FAIL: Could not reach InfluxDB at the configured URL.")
        print("   Is Docker running? Is InfluxDB up? Check: docker compose ps")
        sys.exit(1)
    print("✅  Ping successful.")

    print("\nWriting dummy skin_prices data point...")
    db.write_skin_price(
        item_name="AK-47 | Redline (Field-Tested)",
        category="rifle",
        float_range="ft",
        median_price=15.42,
        volume=120,
        lowest_sell=15.10,
        highest_buy=14.90,
        spread=0.20,
    )
    print("✅  Write complete.")

    print("\nQuerying back the dummy data point...")
    flux = """
from(bucket: "cs2_market")
  |> range(start: -5m)
  |> filter(fn: (r) => r._measurement == "skin_prices")
  |> filter(fn: (r) => r.item_name == "AK-47 | Redline (Field-Tested)")
  |> filter(fn: (r) => r._field == "median_price")
  |> last()
"""
    records = db.query(flux)

    if not records:
        print("❌  FAIL: No records returned. Write may have failed silently.")
        sys.exit(1)

    record = records[0]
    print("✅  Read successful.")
    print(f"    item_name  : {record.values.get('item_name')}")
    print(f"    field      : {record.get_field()}")
    print(f"    value      : {record.get_value()}")
    print(f"    timestamp  : {record.get_time()}")

    print("\nWriting dummy item_metadata data point...")
    db.write_item_metadata(
        item_name="AK-47 | Redline (Field-Tested)",
        float_value=0.27,
        category="rifle",
        is_tracked=True,
    )
    print("✅  Metadata write complete.")

    db.close()
    print("\n🎉  All checks passed. InfluxDB connection is healthy.")


if __name__ == "__main__":
    test_connection()