"""
Tests CSFloat API integration.
Verifies the client can fetch listings, group by float range,
and that float-range data is written to InfluxDB correctly.

Usage:
    python tests/test_csfloat.py
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.csfloat.csfloat_client import CSFloatClient, classify_float, FLOAT_RANGES
from src.db.influx_client import InfluxClientWrapper


def test_float_classification():
    print("Testing float value classification...")
    assert classify_float(0.01) == "fn", "0.01 should be Factory New"
    assert classify_float(0.07) == "mw", "0.07 should be Minimal Wear"
    assert classify_float(0.15) == "ft", "0.15 should be Field-Tested"
    assert classify_float(0.38) == "ww", "0.38 should be Well-Worn"
    assert classify_float(0.45) == "bs", "0.45 should be Battle-Scarred"
    assert classify_float(0.99) == "bs", "0.99 should be Battle-Scarred"
    print("✅  Float classification correct.")


def test_csfloat_api():
    print("\nTesting CSFloat API connection...")

    try:
        client = CSFloatClient()
    except ValueError as e:
        print(f"❌  FAIL: {e}")
        sys.exit(1)

    test_item = "AK-47 | Redline (Field-Tested)"
    print(f"Fetching listings for: {test_item}")

    listings = client.fetch_listings(test_item, limit=50)

    if not listings:
        print(
            "⚠️   No listings returned — item may not be listed on CSFloat right now.\n"
            "    This is not necessarily an error. Try a different item if needed."
        )
        return

    print(f"✅  Fetched {len(listings)} listings.")

    grouped = client.group_by_float_range(listings)
    print(f"✅  Grouped into {len(grouped)} float ranges:")
    for tier, data in grouped.items():
        print(
            f"    {data['label']:15} — avg: ${data['avg_price']:.2f} "
            f"| min: ${data['min_price']:.2f} "
            f"| count: {data['count']} "
            f"| avg float: {data['avg_float']:.4f}"
        )

    best = client.find_best_value_range(grouped, {})
    if best:
        print(f"✅  Best value range: {grouped[best]['label']}")


def test_influx_float_write():
    print("\nTesting float-range InfluxDB write...")
    db = InfluxClientWrapper()

    if not db.ping():
        print("❌  Cannot reach InfluxDB.")
        sys.exit(1)

    db.write_float_range_price(
        item_name="AK-47 | Redline (Field-Tested)",
        float_range="ft",
        avg_price=12.50,
        min_price=11.00,
        max_price=14.00,
        avg_float=0.25,
        listing_count=5,
    )
    print("✅  Float-range data written to InfluxDB.")

    hist = db.get_float_range_historical_avgs("AK-47 | Redline (Field-Tested)")
    if hist:
        print(f"✅  Historical averages retrieved: {hist}")
    else:
        print("⚠️   No historical averages yet — needs more data points over time.")

    db.close()


if __name__ == "__main__":
    print("=" * 55)
    print("CSFloat Integration — Tests")
    print("=" * 55)

    test_float_classification()
    test_csfloat_api()
    test_influx_float_write()

    print()
    print("=" * 55)
    print("🎉  CSFloat tests complete.")
    print("=" * 55)