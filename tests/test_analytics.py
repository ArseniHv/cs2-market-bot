"""
Unit tests for all analytics components.
Uses seeded in-memory test data written to InfluxDB before each test.
Run with: python tests/test_analytics.py
"""

import sys
import os
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.db.influx_client import InfluxClientWrapper
from src.analytics.liquidity import calculate_liquidity, interpret_liquidity
from src.analytics.inflation import calculate_inflation
from src.analytics.spike import calculate_spike
from src.analytics.trend import calculate_trend, classify_trend
from src.analytics.tiers import get_alert_tier
from src.analytics.alert_cooldown import AlertCooldownManager

# ── Test item ──────────────────────────────────────────────────────────────
TEST_ITEM = "Test | Analytics Skin (Field-Tested)"
TEST_CATEGORY = "rifle"
TEST_FLOAT = "ft"


def seed_test_data(db: InfluxClientWrapper, prices: list[float]) -> None:
    """Write a series of price points for the test item going back N days."""
    now = datetime.now(timezone.utc)
    for i, price in enumerate(prices):
        ts = now - timedelta(hours=(len(prices) - i) * 12)
        volume = 100 + (i * 3)
        db.write_skin_price(
            item_name=TEST_ITEM,
            category=TEST_CATEGORY,
            float_range=TEST_FLOAT,
            median_price=price,
            volume=volume,
            lowest_sell=price * 1.01,
            highest_buy=price * 0.95,
            spread=price * 0.06,
            timestamp=ts,
        )


# ── Tier logic tests (no DB needed) ───────────────────────────────────────

def test_tiers():
    print("Testing tier logic...")
    assert get_alert_tier(5) == (0, ""), f"Expected no alert for 5%"
    assert get_alert_tier(20)[0] == 1, f"Expected tier 1 for 20%"
    assert get_alert_tier(40)[0] == 2, f"Expected tier 2 for 40%"
    assert get_alert_tier(60)[0] == 3, f"Expected tier 3 for 60%"
    assert get_alert_tier(-20)[0] == 1, f"Expected tier 1 for -20%"
    print("✅  Tier logic correct.")


def test_trend_classify():
    print("Testing trend classification...")
    assert classify_trend(3.0) == "strong uptrend"
    assert classify_trend(1.0) == "uptrend"
    assert classify_trend(0.0) == "sideways"
    assert classify_trend(-1.0) == "downtrend"
    assert classify_trend(-3.0) == "strong downtrend"
    print("✅  Trend classification correct.")


def test_liquidity_interpret():
    print("Testing liquidity interpretation...")
    assert interpret_liquidity(1.5) == "highly liquid"
    assert interpret_liquidity(0.7) == "moderate"
    assert interpret_liquidity(0.3) == "illiquid"
    print("✅  Liquidity interpretation correct.")


# ── DB-backed tests ────────────────────────────────────────────────────────

def test_liquidity(db: InfluxClientWrapper):
    print("Testing liquidity calculator...")
    result = calculate_liquidity(TEST_ITEM, db)
    assert result is not None, "Liquidity result should not be None"
    assert result.score > 0, "Liquidity score should be positive"
    assert result.interpretation in ["highly liquid", "moderate", "illiquid"]
    print(f"✅  Liquidity: score={result.score}, interpretation={result.interpretation}")


def test_inflation(db: InfluxClientWrapper):
    print("Testing inflation detector...")
    result = calculate_inflation(TEST_ITEM, db)
    assert result is not None, "Inflation result should not be None"
    assert isinstance(result.deviation_pct, float)
    assert result.alert_tier in [0, 1, 2, 3]
    print(
        f"✅  Inflation: deviation={result.deviation_pct:.2f}%, "
        f"tier={result.alert_tier}, label='{result.alert_label}'"
    )


def test_spike(db: InfluxClientWrapper):
    print("Testing spike detector...")
    result = calculate_spike(TEST_ITEM, db)
    assert result is not None, "Spike result should not be None"
    assert isinstance(result.z_score, float)
    print(
        f"✅  Spike: z_score={result.z_score}, "
        f"deviation={result.deviation_pct:.2f}%, tier={result.alert_tier}"
    )


def test_trend(db: InfluxClientWrapper):
    print("Testing trend analyzer...")
    result = calculate_trend(TEST_ITEM, db)
    assert result is not None, "Trend result should not be None"
    assert result.classification in [
        "strong uptrend", "uptrend", "sideways", "downtrend", "strong downtrend"
    ]
    print(f"✅  Trend: slope={result.slope}%, classification={result.classification}")


def test_cooldown():
    print("Testing alert cooldown manager...")
    cooldown = AlertCooldownManager(
        state_file=os.path.join("data", "alerts", "test_cooldown.json")
    )
    item = "Test | Cooldown Item"

    # Should fire on first alert
    assert cooldown.should_alert_inflation(item, 1) is True
    # Should NOT fire again at same tier
    assert cooldown.should_alert_inflation(item, 1) is False
    # Should fire when escalating to higher tier
    assert cooldown.should_alert_inflation(item, 2) is True
    # Should NOT fire again at tier 2
    assert cooldown.should_alert_inflation(item, 2) is False
    # Reset when price cools
    assert cooldown.should_alert_inflation(item, 0) is False
    # Should fire again after reset
    assert cooldown.should_alert_inflation(item, 1) is True

    cooldown.reset_item(item)

    # Clean up test file
    test_file = os.path.join("data", "alerts", "test_cooldown.json")
    if os.path.exists(test_file):
        os.remove(test_file)

    print("✅  Cooldown logic correct.")


def main():
    print("=" * 55)
    print("Analytics Engine — Unit Tests")
    print("=" * 55)

    # Pure logic tests (no DB)
    print("\n── Logic tests (no DB) ──────────────────────────────")
    test_tiers()
    test_trend_classify()
    test_liquidity_interpret()
    test_cooldown()

    # DB-backed tests
    print("\n── DB-backed tests ──────────────────────────────────")
    db = InfluxClientWrapper()
    if not db.ping():
        print("❌  Cannot reach InfluxDB. Is Docker running?")
        sys.exit(1)

    print(f"Seeding test data for '{TEST_ITEM}'...")

    # Seed stable baseline prices then spike at the end
    stable = [10.0 + (i * 0.05) for i in range(50)]   # 50 slowly rising points
    spike = [10.0, 10.1, 10.2, 9.9, 10.3, 10.1, 25.0]  # spike at end
    seed_test_data(db, stable + spike)
    print("✅  Test data seeded.")

    print()
    test_liquidity(db)
    test_inflation(db)
    test_spike(db)
    test_trend(db)

    db.close()

    print()
    print("=" * 55)
    print("🎉  All analytics tests passed.")
    print("=" * 55)


if __name__ == "__main__":
    main()