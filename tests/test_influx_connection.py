"""
Verifies:
1. InfluxDB connection — write and read back a data point
2. Skinport bulk fetch — confirms the API is reachable and returns data
3. Full pipeline — simulates one collection cycle for a tracked item

Usage:
    python tests/test_influx_connection.py
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.db.influx_client import InfluxClientWrapper
from src.collector.skinport_client import SkinportClient
from src.collector.item_manager import ItemManager
from src.collector.influx_writer import InfluxWriter


def test_influxdb():
    print("=" * 50)
    print("1. InfluxDB connection")
    print("=" * 50)

    db = InfluxClientWrapper()

    print("Pinging InfluxDB...")
    if not db.ping():
        print("❌  FAIL: Cannot reach InfluxDB. Is Docker running?")
        sys.exit(1)
    print("✅  Ping successful.")

    print("Writing dummy data point...")
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

    print("Reading back dummy data point...")
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
        print("❌  FAIL: No records returned.")
        sys.exit(1)

    r = records[0]
    print(f"✅  Read successful — value: {r.get_value()} at {r.get_time()}")
    db.close()


def test_skinport():
    print()
    print("=" * 50)
    print("2. Skinport bulk fetch")
    print("=" * 50)

    client = SkinportClient()
    print("Fetching all prices from Skinport (this may take a few seconds)...")
    prices = client.fetch_all_prices()

    if not prices:
        print("❌  FAIL: Skinport returned empty data.")
        sys.exit(1)

    print(f"✅  Fetched {len(prices)} items from Skinport.")

    # Spot-check a specific item
    test_item = "AK-47 | Redline (Field-Tested)"
    item_data = client.get_item_price(test_item, prices)
    if item_data:
        print(f"✅  Spot-check '{test_item}':")
        print(f"    median_price : ${item_data['median_price']:.2f}")
        print(f"    volume       : {item_data['volume']}")
        print(f"    lowest_sell  : ${item_data['lowest_sell']:.2f}")
    else:
        print(f"⚠️   '{test_item}' not found in Skinport data (item may not be listed).")


def test_pipeline():
    print()
    print("=" * 50)
    print("3. Full pipeline — one tracked item write")
    print("=" * 50)

    db = InfluxClientWrapper()
    writer = InfluxWriter(db)
    item_manager = ItemManager()
    skinport = SkinportClient()

    tracked = item_manager.get_all()
    print(f"Tracked items in items.json: {len(tracked)}")

    if not tracked:
        print("⚠️   No tracked items found. Add items to data/items.json.")
        return

    all_prices = skinport.fetch_all_prices()
    if not all_prices:
        print("❌  FAIL: Could not fetch Skinport prices for pipeline test.")
        sys.exit(1)

    item = tracked[0]
    name = item["market_hash_name"]
    print(f"Testing pipeline with: {name}")

    price_data = skinport.get_item_price(name, all_prices)
    if price_data is None:
        print(f"⚠️   '{name}' not found in Skinport data. Try a different tracked item.")
        return

    writer.write_price_point(item, price_data)
    print(f"✅  Pipeline write successful — ${price_data['median_price']:.2f}")

    db.close()


if __name__ == "__main__":
    test_influxdb()
    test_skinport()
    test_pipeline()

    print()
    print("🎉  All checks passed.")