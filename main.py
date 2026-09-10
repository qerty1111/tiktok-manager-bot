import asyncio
import logging
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from config import BOT_TOKEN, ADMIN_IDS
from database.db import init_db
from handlers import start, account, upload, profile, interaction

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

async def main():
    if not BOT_TOKEN or BOT_TOKEN == "your_bot_token_here":
        logger.error("BOT_TOKEN is not set! Please set BOT_TOKEN in .env file.")
        print("\n[!] Ошибка: Токен бота не задан. Укажите BOT_TOKEN в файле .env или передайте его мне.\n")
        return

    if not ADMIN_IDS:
        logger.warning("ADMIN_IDS is empty; set it in .env before exposing the bot publicly.")

    # Initialize SQLite database
    await init_db()
    logger.info("Database initialized successfully.")

    # Initialize Bot and Dispatcher
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN)
    )
    dp = Dispatcher()

    # Register Routers
    dp.include_router(start.router)
    dp.include_router(account.router)
    dp.include_router(upload.router)
    dp.include_router(profile.router)
    dp.include_router(interaction.router)

    logger.info("Starting TikTok Manager Bot polling...")
    try:
        # Delete webhook before polling
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
