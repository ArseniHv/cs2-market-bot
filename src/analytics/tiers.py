"""
Tiered alert system used by both inflation detector and spike detector.

Tiers:
  0 → no alert         (< 15%)
  1 → 🟡 mild          (15–30%)
  2 → 🟠 significant   (30–50%)
  3 → 🚨 SUPERFLAG     (50%+)

Superflag additional condition: volume must be >1.5x rolling average.
If price deviation >50% but volume is normal → "⚠️ possible data anomaly".
"""


def get_alert_tier(deviation_pct: float) -> tuple[int, str]:
    """
    Map a percentage deviation to an alert tier and label.
    Works on absolute value — handles both positive and negative deviations.
    """
    abs_dev = abs(deviation_pct)

    if abs_dev < 15:
        return 0, ""
    elif abs_dev < 30:
        return 1, "🟡 mild movement"
    elif abs_dev < 50:
        return 2, "🟠 significant spike"
    else:
        return 3, "🚨 SUPERFLAG: EXTREME ANOMALY"


def format_alert_message(
    item_name: str,
    current_price: float,
    deviation_pct: float,
    avg_30d: float,
    volume_ratio: float,
    trend_label: str,
    tier: int,
    label: str,
) -> str:
    """
    Format a push alert message for Telegram.
    Returns empty string if tier is 0 (no alert).
    """
    if tier == 0:
        return ""

    direction = "+" if deviation_pct >= 0 else ""

    if tier == 3:
        header = "🚨 SUPERFLAG: EXTREME ANOMALY 🚨"
    elif tier == 2:
        header = "🟠 SIGNIFICANT SPIKE"
    else:
        header = "🟡 Mild Movement"

    return (
        f"{header}\n"
        f"{item_name}\n"
        f"Price: ${current_price:.2f} ({direction}{deviation_pct:.1f}% vs 30d avg)\n"
        f"Volume: {volume_ratio:.1f}x normal\n"
        f"Trend: {trend_label}"
    )