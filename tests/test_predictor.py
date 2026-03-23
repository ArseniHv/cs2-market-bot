"""
Tests the Prophet ML prediction service.
Seeds InfluxDB with enough data points to satisfy the minimum
requirement, runs a prediction, and verifies the output.

Usage:
    python tests/test_predictor.py
"""

import sys
import os
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.db.influx_client import InfluxClientWrapper
from src.ml.predictor import PricePredictor, MINIMUM_DATA_POINTS

TEST_ITEM = "Test | Prophet Skin (Field-Tested)"


def seed_prediction_data(db: InfluxClientWrapper, n_points: int = 60) -> None:
    """
    Seed realistic price data with a gentle uptrend and some noise.
    Uses hourly intervals going back n_points * 6 hours.
    """
    import random
    random.seed(42)

    now = datetime.now(timezone.utc)
    base_price = 20.0

    for i in range(n_points):
        ts = now - timedelta(hours=(n_points - i) * 6)
        # Gentle uptrend + noise
        price = base_price + (i * 0.05) + random.uniform(-0.5, 0.5)
        db.write_skin_price(
            item_name=TEST_ITEM,
            category="rifle",
            float_range="ft",
            median_price=round(price, 2),
            volume=100 + random.randint(0, 50),
            lowest_sell=round(price * 1.01, 2),
            highest_buy=round(price * 0.95, 2),
            spread=round(price * 0.06, 2),
            timestamp=ts,
        )


def test_insufficient_data(db: InfluxClientWrapper) -> None:
    """Verify the minimum data point check works correctly."""
    print("Testing insufficient data guard...")
    predictor = PricePredictor(db)

    # Use an item that definitely has no data
    result = predictor.predict("Nonexistent | Item (Factory New)")
    assert result["success"] is False, "Should fail with no data"
    assert "Not enough data" in result["error"] or "enough" in result["error"].lower()
    assert result["data_points"] == 0
    print(f"✅  Correctly rejected: {result['error'][:60]}...")


def test_prediction(db: InfluxClientWrapper) -> None:
    """Run a full prediction on seeded data and verify output."""
    print(f"\nSeeding {MINIMUM_DATA_POINTS + 30} data points for prediction test...")
    seed_prediction_data(db, n_points=MINIMUM_DATA_POINTS + 30)
    print("✅  Data seeded.")

    print("Running Prophet prediction (this takes 20-30 seconds)...")
    predictor = PricePredictor(db)
    result = predictor.predict(TEST_ITEM)

    assert result["success"] is True, f"Prediction failed: {result.get('error')}"
    assert result["forecast_price"] is not None
    assert result["confidence_low"] is not None
    assert result["confidence_high"] is not None
    assert result["confidence_low"] <= result["forecast_price"] <= result["confidence_high"], \
        "Forecast price should be within confidence interval"
    assert result["chart"] is not None, "Chart should be generated"
    assert result["data_points"] >= MINIMUM_DATA_POINTS

    fp = result["forecast_price"]
    fl = result["confidence_low"]
    fh = result["confidence_high"]
    dp = result["data_points"]

    print(f"✅  Prediction successful:")
    print(f"    Data points used : {dp}")
    print(f"    Forecast price   : ${fp:.2f}")
    print(f"    Confidence range : ${fl:.2f} — ${fh:.2f}")
    print(f"    Chart generated  : {'yes' if result['chart'] else 'no'}")


if __name__ == "__main__":
    print("=" * 55)
    print("Prophet ML Predictor — Tests")
    print("=" * 55)

    db = InfluxClientWrapper()
    if not db.ping():
        print("❌  Cannot reach InfluxDB. Is Docker running?")
        sys.exit(1)

    test_insufficient_data(db)
    test_prediction(db)

    db.close()

    print()
    print("=" * 55)
    print("🎉  All prediction tests passed.")
    print("=" * 55)