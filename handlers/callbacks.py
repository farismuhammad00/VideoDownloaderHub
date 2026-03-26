import os
import hashlib
from telegram import Update
from telegram.ext import ContextTypes
from services.audio_extractor import download_audio
from services.cleanup import safe_remove
from services.redis_client import redis_db, url_memory_store
import logging

logger = logging.getLogger(__name__)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data.startswith("audio|"):
        url_hash = data.split("|", 1)[1]
        
        redis = await redis_db.get_client()
        url = url_memory_store.get(url_hash)
        
        if not url and redis:
            try:
                url = await redis.get(f"url:{url_hash}")
            except Exception as e:
                logger.error(f"Failed to fetch mapped URL from Redis: {e}")
                
        if not url:
            await query.message.reply_text("❌ Link expired or invalid. Please send the video link again.")
            return

        cache_key = f"cache:audio:{url_hash}"
        
        # Check cache
        if redis:
            try:
                cached_file_id = await redis.get(cache_key)
                if cached_file_id:
                    logger.info(f"Cache hit for audio {url}")
                    try:
                        await query.message.reply_audio(
                            audio=cached_file_id,
                            caption="✅ Here is your audio (Cached)!"
                        )
                        return
                    except Exception as e:
                        logger.warning(f"Cached audio file_id invalid or send failed: {e}")
                else:
                    logger.info(f"Cache miss for audio {url}")
            except Exception as e:
                logger.error(f"Redis cache read error: {e}")
        
        status_msg = await query.message.reply_text("⏳ Extracting audio...")
        logger.info(f"Starting audio download for: {url}")
        
        download_result = await download_audio(url)
        if download_result["status"] != "success":
            await status_msg.edit_text(f"❌ Failed to extract audio:\n{download_result.get('error', 'Unknown error')}")
            return
            
        filepath = download_result["filepath"]
        
        await status_msg.edit_text("📤 Uploading audio...")
        logger.info(f"Successfully extracted audio. Uploading to Telegram for {url}")
        
        try:
            with open(filepath, 'rb') as audio_file:
                message = await query.message.reply_audio(
                    audio=audio_file,
                    caption="✅ Here is your audio!",
                    write_timeout=60,
                    read_timeout=60,
                    connect_timeout=60
                )
            await status_msg.delete()
            
            if redis and message.audio:
                try:
                    file_id = message.audio.file_id
                    await redis.set(cache_key, file_id, ex=86400)
                    logger.info(f"Stored cached audio file_id {file_id} for URL {url}")
                except Exception as e:
                    logger.error(f"Redis cache write error: {e}")
                    
            logger.info(f"Successfully sent audio for {url}")
        except Exception as e:
            logger.error(f"Error sending audio: {e}")
            await status_msg.edit_text("❌ Failed to send audio. The file might be too large.")
        finally:
            safe_remove(filepath)
