"""
Telegram bot command handlers.
All handlers are async — uses python-telegram-bot v21 async API exclusively.
"""

import logging
import os

from telegram import Update
from telegram.ext import ContextTypes

from src.analytics.engine import AnalyticsEngine
from src.analytics.inflation import calculate_inflation
from src.analytics.trend import calculate_trend
from src.bot.charts import generate_price_chart
from src.bot.formatters import (
    escape_md,
    format_category_message,
    format_discover_message,
    format_liquidity_message,
    format_price_message,
    format_status_message,
    format_summary_message,
)
from src.collector.item_manager import ItemManager
from src.collector.skinport_client import SkinportClient
from src.db.influx_client import InfluxClientWrapper

logger = logging.getLogger(__name__)

HELP_TEXT = r"""
*CS2 Market Analytics Bot*

*Price & tracking*
/price ITEM\_NAME — current price, 24h change, trend
/chart ITEM\_NAME — price history chart \(30 days\)
/track ITEM\_NAME — add item to tracking list
/untrack ITEM\_NAME — remove item from tracking

*Analytics*
/liquidity ITEM\_NAME — liquidity score with interpretation
/category CATEGORY — category\-level analytics
/summary — top 5 movers across tracked items
/discover — market\-wide price movers \(all CS2 items\)

*Predictions & float*
/predict ITEM\_NAME — 7\-day ML price forecast
/float ITEM\_NAME — float\-range price breakdown

*Settings*
/alerts on — enable push notifications
/alerts off — disable push notifications
/status — bot status and tracked item count
/help — this message
"""


class BotHandlers:
    def __init__(
        self,
        db: InfluxClientWrapper,
        item_manager: ItemManager,
        skinport: SkinportClient,
        alert_manager,
    ):
        self.db = db
        self.item_manager = item_manager
        self.skinport = skinport
        self.alert_manager = alert_manager
        self.engine = AnalyticsEngine(db, item_manager)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _parse_item_name(self, args: tuple) -> str | None:
        """Join command args into a full item name."""
        if not args:
            return None
        return " ".join(args)

    async def _send(
        self,
        update: Update,
        text: str,
        parse_mode: str = "MarkdownV2",
    ) -> None:
        await update.message.reply_text(text, parse_mode=parse_mode)

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    async def help_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self._send(update, HELP_TEXT)

    async def start_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self._send(update, HELP_TEXT)

    async def status_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        msg = format_status_message(
            tracked_count=self.item_manager.count(),
            last_collection=self.alert_manager.get_last_collection(),
            alerts_enabled=self.alert_manager.alerts_enabled(),
        )
        await self._send(update, msg)

    async def track_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        item_name = self._parse_item_name(context.args)
        if not item_name:
            await self._send(
                update,
                "Usage: /track ITEM\\_NAME\nExample: /track AK\\-47 \\| Redline \\(Field\\-Tested\\)",
            )
            return

        added = self.item_manager.add_item(item_name)
        if added:
            name = escape_md(item_name)
            await self._send(update, f"✅ Now tracking: *{name}*")
        else:
            await self._send(update, "⚠️ Item is already in your tracking list\\.")

    async def untrack_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        item_name = self._parse_item_name(context.args)
        if not item_name:
            await self._send(update, "Usage: /untrack ITEM\\_NAME")
            return

        removed = self.item_manager.remove_item(item_name)
        if removed:
            name = escape_md(item_name)
            await self._send(update, f"🗑 Removed from tracking: *{name}*")
        else:
            await self._send(update, "⚠️ Item not found in your tracking list\\.")

    async def price_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        item_name = self._parse_item_name(context.args)
        if not item_name:
            await self._send(update, "Usage: /price ITEM\\_NAME")
            return

        await update.message.reply_text("Fetching price data…")

        price_data = self.skinport.get_item_price(item_name)
        if price_data is None:
            await self._send(
                update,
                f"❌ No price data found for: {escape_md(item_name)}"
            )
            return

        inflation = calculate_inflation(item_name, self.db)
        trend = calculate_trend(item_name, self.db)

        msg = format_price_message(item_name, price_data, inflation, trend)
        await self._send(update, msg)

    async def chart_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        item_name = self._parse_item_name(context.args)
        if not item_name:
            await self._send(update, "Usage: /chart ITEM\\_NAME")
            return

        await update.message.reply_text("Generating chart…")

        buf = generate_price_chart(item_name, self.db)
        if buf is None:
            await self._send(
                update,
                f"❌ Not enough historical data to chart: {escape_md(item_name)}"
            )
            return

        await update.message.reply_photo(
            photo=buf,
            caption=f"📈 {item_name} — last 30 days",
        )

    async def liquidity_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        item_name = self._parse_item_name(context.args)
        if not item_name:
            await self._send(update, "Usage: /liquidity ITEM\\_NAME")
            return

        from src.analytics.liquidity import calculate_liquidity
        result = calculate_liquidity(item_name, self.db)

        if result is None:
            await self._send(
                update,
                f"❌ Not enough data for liquidity analysis: {escape_md(item_name)}"
            )
            return

        await self._send(update, format_liquidity_message(result))

    async def category_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        category = self._parse_item_name(context.args)
        if not category:
            valid = escape_md("rifle, pistol, knife, gloves, case, other")
            await self._send(
                update,
                f"Usage: /category CATEGORY\nValid categories: {valid}"
            )
            return

        result = self.engine.get_category(category)
        if result is None:
            await self._send(
                update,
                f"❌ No tracked items found for category: {escape_md(category)}"
            )
            return

        await self._send(update, format_category_message(result))

    async def summary_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await update.message.reply_text("Calculating top movers…")
        movers = self.engine.get_top_movers(n=5)
        await self._send(update, format_summary_message(movers))

    async def alerts_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        arg = context.args[0].lower() if context.args else ""
        if arg == "on":
            self.alert_manager.set_alerts_enabled(True)
            await self._send(update, "🔔 Push alerts *enabled*\\.")
        elif arg == "off":
            self.alert_manager.set_alerts_enabled(False)
            await self._send(update, "🔕 Push alerts *disabled*\\.")
        else:
            await self._send(update, "Usage: /alerts on or /alerts off")

    async def discover_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        movers = self.skinport.load_market_movers()
        tracked = self.item_manager.get_names()
        msg = format_discover_message(movers, tracked)
        await self._send(update, msg)

    async def predict_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Placeholder — implemented in Part 6."""
        await self._send(
            update,
            "⏳ /predict is coming in a future update\\."
        )

    async def float_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Placeholder — implemented in Part 5."""
        await self._send(
            update,
            "⏳ /float is coming in a future update\\."
        )