import asyncio
from telegram import Message

async def update_progress_message(message: Message, text: str):
    """
    Safely update a progress message in Telegram.
    """
    try:
        if message.text != text:
            await message.edit_text(text)
    except Exception:
        pass
