import asyncio
import logging
import os
from pyrogram import Client
from pyrogram.types import BotCommand
from config import API_ID, API_HASH, BOT_TOKEN
from core.queue_manager import worker_loop

# Basic Logging setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Initialize client
app = Client(
    "video_merger_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    plugins=dict(root="handlers")
)

async def set_bot_commands(client: Client):
    """Sets the bot commands in the Telegram menu."""
    commands = [
        BotCommand("start", "Start the bot"),
        BotCommand("help", "How to use the bot"),
        BotCommand("setintro", "Set a video as intro"),
        BotCommand("viewintro", "Check current intro"),
        BotCommand("delintro", "Delete current intro"),
        BotCommand("replace", "Set replacement rules (old=new)"),
        BotCommand("viewreplace", "View replacement rules"),
        BotCommand("delreplace", "Delete a replacement rule"),
        BotCommand("setprefix", "Set prefix to remove"),
        BotCommand("viewprefix", "View prefixes"),
        BotCommand("delprefix", "Delete a prefix"),
        BotCommand("clearthumb", "Clear the saved thumbnail"),
        BotCommand("speedtest", "Check server speed")
    ]
    await client.set_bot_commands(commands)
    logger.info("Bot commands menu set successfully!")

async def main():
    logger.info("Starting Bot...")
    await app.start()
    
    # Set Menu Commands
    await set_bot_commands(app)
    
    logger.info("Starting Background Queue Worker...")
    # Keep a strong reference so the task is never garbage-collected,
    # and log loudly if it ever exits unexpectedly.
    worker_task = asyncio.create_task(worker_loop(app))

    def _on_worker_done(t: asyncio.Task):
        if t.cancelled():
            logger.warning("Queue worker task was cancelled.")
        elif t.exception():
            logger.critical("Queue worker task crashed!", exc_info=t.exception())

    worker_task.add_done_callback(_on_worker_done)
    
    logger.info("Bot is running and ready to receive commands!")
    from pyrogram import idle
    await idle()
    
    logger.info("Stopping Bot...")
    await app.stop()

if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    os.makedirs("downloads", exist_ok=True)
    app.run(main())
