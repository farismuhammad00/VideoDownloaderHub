import os
import hashlib
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from services.validator import validate_url
from services.downloader import download_video
from services.cleanup import safe_remove
from services.redis_client import redis_db, url_memory_store
from middlewares.anti_spam import anti_spam
from utils.progress import update_progress_message
import logging
import re

logger = logging.getLogger(__name__)

def extract_url(text: str) -> str:
    """Finds the first occurrence of a valid media URL in a string."""
    url_pattern = r'https?://[^\s<>"]+|www\.[^\s<>"]+'
    urls = re.findall(url_pattern, text)
    
    for url in urls:
        # Clean trailing punctuation
        url = url.rstrip(".,;!?'\")]}")
        
        # Skip generic app store links or homepages often included in share text
        lower_url = url.lower()
        if "tiktoklite" in lower_url or "play.google.com" in lower_url or "apps.apple.com" in lower_url:
            continue
            
        return url
        
    return None

async def process_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    message_text = update.message.text.strip()
    
    url = extract_url(message_text)
    
    if not url:
        return
        
    # Check Anti-Spam
    if not await anti_spam.check_user(user_id):
        await update.message.reply_text("🚫 Please slow down! You represent too many requests. Wait a moment.")
        return
        
    redis = await redis_db.get_client()
    url_hash = hashlib.md5(url.encode()).hexdigest()
    cache_key = f"cache:video:{url_hash}"
    
    # Check cache
    if redis:
        try:
            cached_file_id = await redis.get(cache_key)
            if cached_file_id:
                logger.info(f"Cache hit for video {url}")
                
                # Store URL map for the callback button
                url_memory_store[url_hash] = url
                await redis.set(f"url:{url_hash}", url, ex=86400)
                
                keyboard = [[InlineKeyboardButton("🎧 Download as Audio", callback_data=f"audio|{url_hash}")]]
                try:
                    await update.message.reply_video(
                        video=cached_file_id,
                        caption="✅ Here is your video (Cached)!",
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                    return
                except Exception as e:
                    logger.warning(f"Cached video file_id invalid or send failed, redownloading: {e}")
            else:
                logger.info(f"Cache miss for video {url}")
        except Exception as e:
            logger.error(f"Redis cache read error: {e}")
                
    # Store URL map for the callback button before making the actual request
    url_memory_store[url_hash] = url
    if redis:
        try:
            await redis.set(f"url:{url_hash}", url, ex=86400)
        except: pass
                
    status_msg = await update.message.reply_text("🔍 Validating link...")
    
    # Validation
    validation_result = await validate_url(url)
    if not validation_result["valid"]:
        await update_progress_message(status_msg, f"❌ {validation_result['error']}")
        return
        
    await update_progress_message(status_msg, "⏳ Downloading video...")
    # Download
    logger.info(f"Starting media download for: {url}")
    download_result = await download_video(url)
    if download_result["status"] != "success":
        await update_progress_message(status_msg, f"❌ Failed to download:\n{download_result.get('error', 'Unknown error')}")
        return
        
    media_items = download_result.get("media", [])
    if not media_items:
        await update_progress_message(status_msg, "❌ No downloadable media found.")
        return
        
    await update_progress_message(status_msg, f"📤 Uploading {len(media_items)} item(s) to Telegram...")
    logger.info(f"Successfully downloaded {len(media_items)} items. Uploading to Telegram for {url}")
    
    from telegram import InputMediaPhoto, InputMediaVideo
    
    try:
        if len(media_items) == 1:
            # Single item logic (keep existing behavior but adapted to the list)
            item = media_items[0]
            filepath = item["filepath"]
            thumbnail = item.get("thumbnail")
            
            keyboard = [[InlineKeyboardButton("🎧 Download as Audio", callback_data=f"audio|{url_hash}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            async def send_single_media(as_document=False, use_thumb=True):
                thumb_path = thumbnail if use_thumb and thumbnail and os.path.exists(thumbnail) and thumbnail.endswith('.jpg') else None
                if item["type"] == "photo":
                    return await update.message.reply_photo(photo=filepath, caption="✅ Here is your photo!", reply_markup=reply_markup)
                
                if as_document:
                    return await update.message.reply_document(
                        document=filepath,
                        caption="✅ Here is your media (sent as document due to format)! ",
                        reply_markup=reply_markup
                    )
                else:
                    return await update.message.reply_video(
                        video=filepath,
                        caption="✅ Here is your video!",
                        supports_streaming=True,
                        thumbnail=thumb_path,
                        reply_markup=reply_markup
                    )

            try:
                message = await send_single_media(as_document=False, use_thumb=True)
            except Exception as e:
                logger.warning(f"Failed to send as default: {e}. Retrying as document...")
                message = await send_single_media(as_document=True, use_thumb=False)
                
            if redis and message and (message.video or message.document or message.photo):
                try:
                    target = message.video or message.document or message.photo
                    await redis.set(cache_key, target.file_id, ex=86400)
                except: pass
        else:
            # Multi-item logic (Media Group)
            # Split into chunks of 10 (Telegram limit)
            for i in range(0, len(media_items), 10):
                chunk = media_items[i:i + 10]
                media_group = []
                for idx, item in enumerate(chunk):
                    caption = f"✅ Media {i+idx+1}/{len(media_items)}" if idx == 0 else ""
                    if item["type"] == "video":
                        media_group.append(InputMediaVideo(
                            media=open(item["filepath"], 'rb'),
                            caption=caption,
                            supports_streaming=True,
                            thumbnail=open(item["thumbnail"], 'rb') if item.get("thumbnail") and os.path.exists(item["thumbnail"]) else None
                        ))
                    else:
                        media_group.append(InputMediaPhoto(
                            media=open(item["filepath"], 'rb'),
                            caption=caption
                        ))
                
                await update.message.reply_media_group(media=media_group)
                # Close all open files in media_group
                for m in media_group:
                    if hasattr(m.media, 'close'): m.media.close()
                    if hasattr(m, 'thumbnail') and m.thumbnail and hasattr(m.thumbnail, 'close'): m.thumbnail.close()

        await status_msg.delete()
        logger.info(f"Successfully sent all media for {url}")
        
    except Exception as e:
        logger.error(f"Error sending media: {e}", exc_info=True)
        await update_progress_message(status_msg, f"❌ Failed to send media.\nReason: {str(e)[:50]}...")
    finally:
        # Cleanup all files
        for item in media_items:
            safe_remove(item["filepath"])
            if item.get("thumbnail"):
                safe_remove(item["thumbnail"])
```
