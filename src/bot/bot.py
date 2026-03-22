"""
Telegram bot initialisation and startup.
Wires together all handlers, the alert manager, and the collector scheduler.
Runs the bot in polling mode alongside APScheduler.
"""

import asyncio
import logging
import os

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv
from telegram.ext import ApplicationBuilder, CommandHandler

from src.bot.alert_manager import AlertManager
from src.bot.handlers import BotHandlers
from src.collector.collector import Collector
from src.collector.item_manager import ItemManager
from src.collector.skinport_client import SkinportClient
from src.db.influx_client import InfluxClientWrapper

load_dotenv()

logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = int(os.getenv("TELEGRAM_CHAT_ID", "0"))
COLLECTION_INTERVAL = int(os.getenv("COLLECTION_INTERVAL_MINUTES", "30"))


async def run_collection_and_alerts(
    collector: Collector, alert_manager: AlertManager
) -> None:
    """Run one collection cycle then fire any triggered alerts."""
    collector.run_collection_cycle()
    await alert_manager.run_alerts()


def start_bot() -> None:
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN is not set in environment.")
    if not TELEGRAM_CHAT_ID:
        raise ValueError("TELEGRAM_CHAT_ID is not set in environment.")

    # Core dependencies
    db = InfluxClientWrapper()
    item_manager = ItemManager()
    skinport = SkinportClient()
    collector = Collector()

    # Build the Telegram application
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # Alert manager needs the app reference to send messages
    alert_manager = AlertManager(
        db=db,
        item_manager=item_manager,
        bot_app=app,
        chat_id=TELEGRAM_CHAT_ID,
    )

    # Handler wiring
    handlers = BotHandlers(
        db=db,
        item_manager=item_manager,
        skinport=skinport,
        alert_manager=alert_manager,
    )

    app.add_handler(CommandHandler("start", handlers.start_command))
    app.add_handler(CommandHandler("help", handlers.help_command))
    app.add_handler(CommandHandler("status", handlers.status_command))
    app.add_handler(CommandHandler("track", handlers.track_command))
    app.add_handler(CommandHandler("untrack", handlers.untrack_command))
    app.add_handler(CommandHandler("price", handlers.price_command))
    app.add_handler(CommandHandler("chart", handlers.chart_command))
    app.add_handler(CommandHandler("liquidity", handlers.liquidity_command))
    app.add_handler(CommandHandler("category", handlers.category_command))
    app.add_handler(CommandHandler("summary", handlers.summary_command))
    app.add_handler(CommandHandler("alerts", handlers.alerts_command))
    app.add_handler(CommandHandler("discover", handlers.discover_command))
    app.add_handler(CommandHandler("predict", handlers.predict_command))
    app.add_handler(CommandHandler("float", handlers.float_command))

    # Scheduler — runs collection + alerts on interval
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        run_collection_and_alerts,
        trigger="interval",
        minutes=COLLECTION_INTERVAL,
        args=[collector, alert_manager],
        id="collection_job",
        replace_existing=True,
    )

    async def post_init(application):
        """Run first collection cycle on startup."""
        logger.info("Running initial collection cycle on startup...")
        await run_collection_and_alerts(collector, alert_manager)
        scheduler.start()
        logger.info(
            f"Scheduler started — collecting every {COLLECTION_INTERVAL} minutes."
        )

    app.post_init = post_init

    logger.info("Starting Telegram bot...")
    app.run_polling(drop_pending_updates=True)