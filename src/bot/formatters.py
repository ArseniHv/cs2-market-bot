"""
Telegram message formatters.
All bot responses are assembled here — keeps handler code clean.
All prices in USD. Telegram MarkdownV2 is used throughout.
"""

from src.analytics.models import (
    InflationResult,
    LiquidityResult,
    SpikeResult,
    TrendResult,
    CategoryResult,
)


def escape_md(text: str) -> str:
    """Escape special characters for Telegram MarkdownV2."""
    special = r"\_*[]()~`>#+-=|{}.!"
    for ch in special:
        text = text.replace(ch, f"\\{ch}")
    return text


def trend_emoji(classification: str) -> str:
    return {
        "strong uptrend": "🚀",
        "uptrend": "📈",
        "sideways": "➡️",
        "downtrend": "📉",
        "strong downtrend": "💀",
    }.get(classification, "❓")


def format_price_message(
    item_name: str,
    price_data: dict,
    inflation: InflationResult | None,
    trend: TrendResult | None,
) -> str:
    """Format the /price command response."""
    name = escape_md(item_name)
    price = escape_md(f"${price_data['median_price']:.2f}")
    vol = escape_md(str(price_data["volume"]))
    sell = escape_md(f"${price_data['lowest_sell']:.2f}")
    buy = escape_md(f"${price_data['highest_buy']:.2f}")
    spread = escape_md(f"${price_data['spread']:.2f}")

    lines = [
        f"💰 *{name}*",
        f"Median price: `{price}`",
        f"Lowest sell:  `{sell}`",
        f"Highest buy:  `{buy}`",
        f"Spread:       `{spread}`",
        f"Volume \\(24h\\): `{vol}`",
    ]

    if inflation:
        dev = inflation.deviation_pct
        sign = "+" if dev >= 0 else ""
        dev_str = escape_md(f"{sign}{dev:.1f}%")
        lines.append(f"30d change:   `{dev_str}`")
        if inflation.alert_label:
            lines.append(f"Alert: {inflation.alert_label}")

    if trend:
        emoji = trend_emoji(trend.classification)
        cls = escape_md(trend.classification)
        lines.append(f"Trend: {emoji} {cls}")

    return "\n".join(lines)


def format_liquidity_message(result: LiquidityResult) -> str:
    """Format the /liquidity command response."""
    name = escape_md(result.item_name)
    score = escape_md(f"{result.score:.4f}")
    interp = escape_md(result.interpretation)
    vol = escape_md(f"{result.rolling_7d_avg_volume:.1f}")
    price = escape_md(f"${result.median_price:.2f}")

    return (
        f"💧 *Liquidity — {name}*\n"
        f"Score:          `{score}`\n"
        f"Interpretation: `{interp}`\n"
        f"7d avg volume:  `{vol}`\n"
        f"Median price:   `{price}`"
    )


def format_category_message(result: CategoryResult) -> str:
    """Format the /category command response."""
    cat = escape_md(result.category.title())
    index = escape_md(f"${result.median_price_index:.2f}")
    inflation = escape_md(f"{result.inflation_rate:+.2f}%")
    most = escape_md(result.most_liquid_item)
    least = escape_md(result.least_liquid_item)

    return (
        f"📊 *Category: {cat}*\n"
        f"Items tracked:  `{result.item_count}`\n"
        f"Price index:    `{index}`\n"
        f"Inflation \\(30d\\): `{inflation}`\n"
        f"Most liquid:  `{most}`\n"
        f"Least liquid: `{least}`"
    )


def format_summary_message(movers: list[dict]) -> str:
    """Format the /summary command response — top 5 movers."""
    if not movers:
        return "No movement data yet\\. Run a collection cycle first\\."

    lines = ["📋 *Top Movers Today*\n"]
    for i, m in enumerate(movers, 1):
        name = escape_md(m["item_name"])
        dev = m["deviation_pct"]
        sign = "+" if dev >= 0 else ""
        dev_str = escape_md(f"{sign}{dev:.1f}%")
        price = escape_md(f"${m['avg_7d']:.2f}")
        label = m.get("alert_label", "")
        lines.append(f"{i}\\. *{name}*")
        lines.append(f"   Price: `{price}` \\| Change: `{dev_str}` {label}")

    return "\n".join(lines)


def format_alert_message(alert: dict) -> str:
    """Format a push alert message."""
    tier = alert["tier"]
    item = escape_md(alert["item_name"])
    dev = alert["deviation_pct"]
    sign = "+" if dev >= 0 else ""
    dev_str = escape_md(f"{sign}{dev:.1f}%")
    price = escape_md(f"${alert['current_price']:.2f}")
    avg = escape_md(f"${alert['avg_30d']:.2f}")
    trend = escape_md(alert.get("trend", "unknown"))
    label = alert.get("label", "")

    if alert.get("type") == "anomaly":
        return (
            f"⚠️ *Possible Data Anomaly*\n"
            f"{item}\n"
            f"Price: `{price}` \\({dev_str} vs 30d avg `{avg}`\\)\n"
            f"Volume is normal — may not be a real event\\."
        )

    if tier == 3:
        header = "🚨 *SUPERFLAG: EXTREME ANOMALY* 🚨"
    elif tier == 2:
        header = f"🟠 *SIGNIFICANT SPIKE*"
    else:
        header = f"🟡 *Mild Movement*"

    vol_line = ""
    if alert.get("volume_confirmed"):
        vol_line = "\nVolume: elevated ✅"

    return (
        f"{header}\n"
        f"{item}\n"
        f"Price: `{price}` \\({dev_str} vs 30d avg `{avg}`\\)\n"
        f"Trend: {trend}{vol_line}"
    )


def format_discover_message(movers: list[dict], tracked_names: list[str]) -> str:
    """Format the /discover command — market-wide movers."""
    if not movers:
        return (
            "No market movers detected yet\\.\n"
            "Data is compared between collection cycles — "
            "run the collector at least twice\\."
        )

    lines = ["🔍 *Market\\-Wide Movers*\n"]
    for i, m in enumerate(movers[:15], 1):
        name = m["market_hash_name"]
        dev = m["pct_change"]
        sign = "+" if dev >= 0 else ""
        emoji = "📈" if dev > 0 else "📉"
        name_esc = escape_md(name)
        dev_str = escape_md(f"{sign}{dev:.1f}%")
        price_str = escape_md(f"${m['curr_price']:.2f}")
        already = " ✅" if name in tracked_names else ""
        lines.append(
            f"{i}\\. {emoji} *{name_esc}*{already}\n"
            f"   `{price_str}` \\({dev_str}\\)"
        )

    lines.append(
        "\n_Use /track ITEM\\_NAME to start tracking any item\\._"
    )
    return "\n".join(lines)


def format_status_message(
    tracked_count: int,
    last_collection: str | None,
    alerts_enabled: bool,
) -> str:
    """Format the /status command response."""
    status = "🟢 enabled" if alerts_enabled else "🔴 disabled"
    last = escape_md(last_collection or "Never")
    return (
        f"🤖 *Bot Status*\n"
        f"Tracked items:   `{tracked_count}`\n"
        f"Last collection: `{last}`\n"
        f"Push alerts:     {status}"
    )