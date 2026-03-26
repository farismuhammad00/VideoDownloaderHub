import os
import asyncio
import uuid
import logging
import yt_dlp
from config import DOWNLOAD_DIR, MAX_FILE_SIZE, MAX_DURATION

logger = logging.getLogger(__name__)

def download_filter(info, *args, **kwargs):
    duration = info.get('duration')
    if duration and duration > MAX_DURATION:
        return f"Video is too long ({int(duration)}s). Maximum is {MAX_DURATION}s."
    return None

async def retry_download(func, *args, retries=3, **kwargs):
    """Wrapper to retry download on failure"""
    for attempt in range(1, retries + 1):
        try:
            result = await func(*args, **kwargs)
            if result.get("status") == "success":
                return result
                
            error_msg = result.get("error", "").lower()
            if "unsupported" in error_msg or "too large" in error_msg or "too long" in error_msg or "max-filesize" in error_msg:
                return result
                
            if attempt == retries:
                logger.error(f"All {retries} retry attempts failed for {args}")
                return {"status": "error", "error": "❌ Failed to download after multiple attempts. Please try again later."}
                
            delay = 2 ** (attempt - 1)
            logger.warning(f"Attempt {attempt} failed: {error_msg}. Retrying in {delay}s...")
            await asyncio.sleep(delay)
        except Exception as e:
            if attempt == retries:
                logger.error(f"All {retries} retry attempts crashed for {args}")
                return {"status": "error", "error": "❌ Failed to download after multiple attempts. Please try again later."}
            delay = 2 ** (attempt - 1)
            logger.warning(f"Attempt {attempt} exception: {e}. Retrying in {delay}s...")
            await asyncio.sleep(delay)
    
    return {"status": "error", "error": "❌ Failed to download after multiple attempts. Please try again later."}

async def _download_video_impl(url: str) -> dict:
    # Use absolute path for cookies.txt
    current_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(current_dir)
    cookie_path = os.path.join(root_dir, 'cookies.txt')
    
    ydl_opts_base = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/bestvideo+bestaudio/best',
        'merge_output_format': 'mp4',
        'writethumbnail': True,
        'postprocessors': [{'key': 'FFmpegThumbnailsConvertor', 'format': 'jpg'}],
        'quiet': True,
        'no_warnings': True,
        'extractor_args': {'youtube': ['player_client=ios', 'web']},
        'max_filesize': MAX_FILE_SIZE,
        'match_filter': download_filter,
    }
    
    if os.path.exists(cookie_path):
        ydl_opts_base['cookiefile'] = cookie_path
        
    try:
        loop = asyncio.get_running_loop()
        
        # 1. Extract Info first without downloading to see structure
        def get_info():
            with yt_dlp.YoutubeDL(ydl_opts_base) as ydl:
                return ydl.extract_info(url, download=False)
        
        info = await loop.run_in_executor(None, get_info)
        
        if not info:
            return {"status": "error", "error": "Could not extract media info."}

        # 2. Flatten entries
        entries = info.get('entries', [info]) if 'entries' in info else [info]
        media_items = []
        
        for entry in entries:
            file_id = str(uuid.uuid4())
            output_template = os.path.join(DOWNLOAD_DIR, f"{file_id}.%(ext)s")
            
            # Decide if it's a video or photo
            vcodec = entry.get('vcodec')
            is_video = vcodec is not None and vcodec != 'none'
            # Some extractors for images might not have vcodec at all
            if not is_video and entry.get('url') and ('.jpg' in entry['url'] or '.png' in entry['url'] or entry.get('ext') in ['jpg', 'png', 'jpeg', 'webp']):
                is_photo = True
            else:
                is_photo = False
                # If it's not explicitly a photo but has no vcodec, it might still be a video if it has formats
                if not is_video and entry.get('formats'):
                    is_video = True

            # 3. Download the specific entry
            item_ydl_opts = ydl_opts_base.copy()
            item_ydl_opts['outtmpl'] = output_template
            
            def download_entry(entry_url):
                with yt_dlp.YoutubeDL(item_ydl_opts) as ydl:
                    # We use the original entry URL or the direct URL
                    download_url = entry_url if 'http' in entry_url else url
                    item_info = ydl.extract_info(download_url, download=True)
                    return ydl.prepare_filename(item_info), item_info

            try:
                # If entry has a direct URL, use it, otherwise use the entry's ID if it's a sub-id
                entry_url = entry.get('webpage_url') or entry.get('url') or url
                filepath, item_info = await loop.run_in_executor(None, download_entry, entry_url)
                
                thumbnail_path = filepath.rsplit('.', 1)[0] + '.jpg'
                if not os.path.exists(thumbnail_path):
                    thumbnail_path = filepath.rsplit('.', 1)[0] + '.webp'
                    if not os.path.exists(thumbnail_path):
                        thumbnail_path = None
                
                media_items.append({
                    "type": "video" if is_video else "photo",
                    "filepath": filepath,
                    "title": item_info.get('title', 'Media'),
                    "duration": item_info.get('duration', 0),
                    "thumbnail": thumbnail_path
                })
            except Exception as e:
                logger.warning(f"Failed to download entry {entry.get('id')}: {e}")
                continue

        if not media_items:
            return {"status": "error", "error": "No downloadable media found in this post."}
            
        return {
            "status": "success",
            "media": media_items
        }
        
    except Exception as e:
        error_str = str(e)
        if "max-filesize" in error_str.lower():
            return {"status": "error", "error": f"Media is too large. Maximum size is {int(MAX_FILE_SIZE / (1024*1024))} MB."}
        return {"status": "error", "error": error_str}

async def download_video(url: str) -> dict:
    """Entry point for video downloading with retries."""
    return await retry_download(_download_video_impl, url)
