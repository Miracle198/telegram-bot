"""
Telegram bot that posts a random anime picture with an English quote
to a channel/group every day at 20:00 (Europe/Helsinki).

Stack: aiogram 3.x + APScheduler (AsyncIOScheduler) + Pillow + requests.
Commands:
  /start      - shows your Telegram ID (handy for filling in config.json)
  /test_anime - (admins only) generate and post a picture right now
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

import pytz
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import BufferedInputFile, Message
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from image_maker import create_image

# =====================================================================
# 1. SETTINGS (read from config.json)
# =====================================================================

CONFIG_FILE = Path(__file__).parent / "config.json"


def load_config() -> dict:
    """Reads config.json and validates the required fields."""
    if not CONFIG_FILE.exists():
        sys.exit("config.json not found. Copy config.example.json to config.json and fill it in.")

    try:
        with CONFIG_FILE.open(encoding="utf-8") as f:
            config = json.load(f)
    except json.JSONDecodeError as error:
        sys.exit(f"config.json is not valid JSON: {error}")

    for key in ("token", "channel_id", "admin_ids"):
        if not config.get(key):
            sys.exit(f'Field "{key}" is missing or empty in config.json.')

    try:
        config["channel_id"] = int(config["channel_id"])  # e.g. -1001234567890
        config["admin_ids"] = [int(i) for i in config["admin_ids"]]
    except (TypeError, ValueError):
        sys.exit('"channel_id" must be an integer and "admin_ids" a list of integers.')

    return config


CONFIG = load_config()

BOT_TOKEN: str = CONFIG["token"]
CHANNEL_ID: int = CONFIG["channel_id"]      # where the pictures are posted
ADMIN_IDS: list[int] = CONFIG["admin_ids"]  # who may use /test_anime
FONT_PATH: str | None = CONFIG.get("font_path")  # optional; default is Montserrat-Bold.ttf in the root

# Time zone and posting time (defaults: Europe/Kyiv, 20:00)
try:
    TIMEZONE = pytz.timezone(CONFIG.get("timezone", "Europe/Helsinki"))
except pytz.UnknownTimeZoneError:
    sys.exit(f'Unknown time zone in config.json: {CONFIG.get("timezone")}')

try:
    SEND_HOUR, SEND_MINUTE = map(int, CONFIG.get("send_time", "20:00").split(":"))
except ValueError:
    sys.exit('"send_time" must look like "20:00".')

router = Router()


# =====================================================================
# 2. POSTING THE PICTURE
# =====================================================================

async def send_anime_picture(bot: Bot) -> str:
    """
    Fetches an image from the API, overlays a quote and posts it to the channel.
    Returns the quote that was used.
    """
    # Временная строка для проверки ID в консоли
    print(f"\n[DEBUG] Попытка отправить картинку на ID: {CHANNEL_ID}\n")

    # requests and Pillow are blocking libraries, so they run in a separate thread
    # to keep the bot's event loop responsive
    buffer, phrase = await asyncio.to_thread(create_image, FONT_PATH)

    photo = BufferedInputFile(buffer.read(), filename="anime.jpg")
    await bot.send_photo(chat_id=CHANNEL_ID, photo=photo)
    logging.info("Picture posted to %s. Quote: %s", CHANNEL_ID, phrase)
    return phrase


async def scheduled_job(bot: Bot) -> None:
    """Scheduler task. Errors never crash the bot; admins are notified instead."""
    try:
        await send_anime_picture(bot)
    except Exception as error:
        logging.exception("Scheduled posting failed")
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(admin_id, f"⚠️ Scheduled post failed:\n{error}")
            except Exception:
                pass  # the admin may have never started the bot - just skip


# =====================================================================
# 3. COMMANDS
# =====================================================================

@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    """Shows the user's ID so it can be copied into config.json."""
    await message.answer(
        f"Hello! Your Telegram ID: <code>{message.from_user.id}</code>\n"
        f"I post an anime picture to the channel every day at "
        f"{SEND_HOUR:02d}:{SEND_MINUTE:02d} ({TIMEZONE.zone})."
    )


@router.message(Command("test_anime"), F.from_user.id.in_(ADMIN_IDS))
async def cmd_test_anime(message: Message, bot: Bot) -> None:
    """Admin-only: posts a picture immediately without screen freezing."""
    try:
        await send_anime_picture(bot)
    except Exception as error:
        logging.exception("/test_anime failed")
        await message.answer(f"❌ Error: {error}")

@router.message(Command("test_anime"))
async def cmd_test_anime_denied(message: Message) -> None:
    """Reply for users who are not in admin_ids."""
    await message.answer("⛔ This command is for admins only.")


# =====================================================================
# 4. STARTUP
# =====================================================================

async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(router)

    # Scheduler pinned to the Helsinki time zone: 20:00 Finland time regardless of the server clock
    scheduler = AsyncIOScheduler(timezone=TIMEZONE)
    scheduler.add_job(
        scheduled_job,
        trigger=CronTrigger(hour=SEND_HOUR, minute=SEND_MINUTE, timezone=TIMEZONE),
        args=[bot],
        id="daily_anime",
        misfire_grace_time=300,  # still runs if the bot was late by up to 5 minutes
        coalesce=True,           # merge missed runs into one
    )
    scheduler.start()  # must be started inside the running event loop

    logging.info("Bot started. Next post: %s", scheduler.get_job("daily_anime").next_run_time)

    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped.")
