"""
Formatters for the /float command response.
"""

from src.bot.formatters import escape_md
from src.csfloat.csfloat_client import FLOAT_LABELS


def format_float_message(
    item_name: str,
    grouped: dict[str, dict],
    best_value_tier: str | None,
) -> str:
    """
    Format the /float command response showing price breakdown by wear.
    Highlights the best value float range.
    """
    if not grouped:
        return (
            f"❌ No CSFloat listings found for: {escape_md(item_name)}\n"
            "The item may not be listed on CSFloat right now\\."
        )

    name = escape_md(item_name)
    lines = [f"🔬 *Float Breakdown — {name}*\n"]

    tier_order = ["fn", "mw", "ft", "ww", "bs"]

    for tier in tier_order:
        data = grouped.get(tier)
        if not data:
            continue

        label = escape_md(data["label"])
        avg = escape_md(f"${data['avg_price']:.2f}")
        low = escape_md(f"${data['min_price']:.2f}")
        high = escape_md(f"${data['max_price']:.2f}")
        avg_fl = escape_md(f"{data['avg_float']:.4f}")
        count = data["count"]

        best_marker = " 🏆 _best value_" if tier == best_value_tier else ""

        lines.append(
            f"*{label}*{best_marker}\n"
            f"  Avg: `{avg}` \\(range: `{low}` — `{high}`\\)\n"
            f"  Avg float: `{avg_fl}` \\| Listings: `{count}`"
        )

    lines.append(
        f"\n_Data from CSFloat • {sum(d['count'] for d in grouped.values())} "
        f"listings analysed_"
    )

    return "\n".join(lines)