import os
import asyncio
import shutil
import logging
from pyrogram import Client, filters
from pyrogram.types import Message
from torrentp import TorrentDownloader

# --- Config ---
API_ID = int(os.environ.get("API_ID", ""))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
DOWNLOAD_DIR = "./downloads"
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2GB Telegram Bot API limit

if not all([API_ID, API_HASH, BOT_TOKEN]):
    raise ValueError("API_ID, API_HASH, and BOT_TOKEN must be set as environment variables.")

if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("leechbot")

app = Client("leechbot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- Helpers ---

async def download_torrent(link: str, dest: str):
    td = TorrentDownloader(link, dest)
    await td.start_download()
    files = []
    for root, _, filenames in os.walk(dest):
        for f in filenames:
            files.append(os.path.join(root, f))
    return files

def cleanup_folder(folder: str):
    try:
        shutil.rmtree(folder)
        os.makedirs(folder)
    except Exception as e:
        logger.warning(f"Cleanup failed: {e}")

def is_file_too_large(file_path):
    return os.path.getsize(file_path) > MAX_FILE_SIZE

def get_mention(message: Message, bot_username: str):
    """Checks if the bot is mentioned in the group message."""
    if message.entities:
        for entity in message.entities:
            if entity.type == "mention" and bot_username in message.text:
                return True
    return False

# --- Error Handler ---

@app.on_message(filters.command("leech"))
async def leech_handler(client: Client, message: Message):
    try:
        # Only respond in group if bot is mentioned or command is used directly
        if message.chat.type in ("group", "supergroup"):
            me = await app.get_me()
            if not (message.text and (f"@{me.username}" in message.text or message.text.startswith("/leech"))):
                return

        if len(message.command) < 2:
            await message.reply_text("Usage: /leech <magnet link or .torrent URL>")
            return

        link = message.command[1]
        status = await message.reply_text("Downloading torrent...")

        try:
            files = await download_torrent(link, DOWNLOAD_DIR)
        except Exception as e:
            await status.edit(f"❌ Failed to download: {e}")
            logger.error(f"Download error: {e}")
            cleanup_folder(DOWNLOAD_DIR)
            return

        if not files:
            await status.edit("❌ No files found after download.")
            cleanup_folder(DOWNLOAD_DIR)
            return

        too_large = [f for f in files if is_file_too_large(f)]
        to_upload = [f for f in files if not is_file_too_large(f)]

        if too_large:
            msg = "\n".join([os.path.basename(f) for f in too_large])
            await message.reply_text(f"⚠️ Skipped files (too large for Telegram):\n{msg}")

        if not to_upload:
            await status.edit("❌ All files are too large to upload to Telegram (max 2GB).")
            cleanup_folder(DOWNLOAD_DIR)
            return

        await status.edit("Uploading to Telegram...")

        for file_path in to_upload:
            try:
                await message.reply_document(file_path)
            except Exception as e:
                await message.reply_text(f"❌ Failed to upload {os.path.basename(file_path)}: {e}")
                logger.error(f"Upload error: {e}")

        await status.edit("✅ Done!")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        await message.reply_text(f"❌ Unexpected error: {e}")
    finally:
        cleanup_folder(DOWNLOAD_DIR)

# Optional: /start command for greeting
@app.on_message(filters.command("start"))
async def start_handler(client: Client, message: Message):
    await message.reply_text("👋 Hello! Send /leech <magnet link or .torrent URL> to download and upload torrents here.")

# Global error handler (Pyrogram handles most, but you can use try/except in handlers)
# For advanced error logging, see: https://docs.python-telegram-bot.org/en/v21.8/examples.errorhandlerbot.html

if __name__ == "__main__":
    app.run()
