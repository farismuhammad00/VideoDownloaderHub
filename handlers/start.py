from telegram import Update
from telegram.ext import ContextTypes

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_message = (
        "👋 Welcome to the Video Downloader Bot!\n\n"
        "Send me a link from YouTube, Instagram, TikTok, or Twitter, and I'll download the media for you.\n\n"
        "Features:\n"
        "🎬 Download Videos\n"
        "🎧 Extract Audio\n\n"
        "Please note: Max duration is 10 mins and max size is 50MB."
    )
    await update.message.reply_text(welcome_message)
