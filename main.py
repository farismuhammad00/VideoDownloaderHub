import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
import uvicorn
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters

from config import BOT_TOKEN, WEBHOOK_URL, PORT
from services.redis_client import redis_db

# Handlers (We will create these soon)
from handlers.start import start_command
from handlers.download import process_url
from handlers.callbacks import button_callback

# Setup logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.DEBUG
)
logger = logging.getLogger(__name__)

# Verify token
if not BOT_TOKEN:
    logger.error("BOT_TOKEN is missing! Please set it in your environment variables.")

# Initialize Telegram Application
ptb_app = Application.builder().token(BOT_TOKEN).build()

# Register handlers
ptb_app.add_handler(CommandHandler("start", start_command))
ptb_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process_url))
ptb_app.add_handler(CallbackQueryHandler(button_callback))

@asynccontextmanager
async def lifespan(app: FastAPI):
    import subprocess
    try:
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, check=True)
        logger.info(f"FFmpeg detected: {result.stdout.splitlines()[0]}")
    except Exception as e:
        logger.error(f"FFmpeg is missing or failed to run! Audio extraction will not work: {e}")

    # Connect Redis
    await redis_db.connect()

    # Initialize the PTB application
    logger.info("Initializing Telegram Bot...")
    await ptb_app.initialize()
    logger.info("Setting webhook...")
    if WEBHOOK_URL:
        # Ensure correct URL format
        webhook_endpoint = f"{WEBHOOK_URL.rstrip('/')}/webhook"
        await ptb_app.bot.set_webhook(url=webhook_endpoint)
        logger.info(f"Webhook set to {webhook_endpoint}")
    else:
        logger.warning("WEBHOOK_URL not configured! Provide it as an environment variable.")
    await ptb_app.start()
    
    yield
    
    # Shutdown the PTB application
    logger.info("Stopping Telegram Bot...")
    await redis_db.close()
    await ptb_app.stop()
    await ptb_app.shutdown()

app = FastAPI(lifespan=lifespan)

@app.post("/webhook")
async def process_webhook(request: Request):
    """
    Webhook endpoint for Telegram to send updates.
    """
    try:
        data = await request.json()
        update = Update.de_json(data, ptb_app.bot)
        # Push update to Telegram's background queue instead of blocking the request
        await ptb_app.update_queue.put(update)
        return {"ok": True}
    except Exception as e:
        logger.error(f"Error processing update: {e}", exc_info=True)
        return {"ok": False, "error": str(e)}

@app.get("/")
def index():
    return {"message": "Telegram Video Downloader Bot is running."}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, log_level="info")
