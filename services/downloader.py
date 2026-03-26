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
    file_id = str(uuid.uuid4())
    output_template = os.path.join(DOWNLOAD_DIR, f"{file_id}.%(ext)s")
    
    ydl_opts = {
        'outtmpl': output_template,
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
    
    # Use absolute path for cookies.txt
    current_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(current_dir)
    cookie_path = os.path.join(root_dir, 'cookies.txt')
    
    if os.path.exists(cookie_path):
        ydl_opts['cookiefile'] = cookie_path
    
    def extract_and_download():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            return ydl.prepare_filename(info), info
            
    try:
        loop = asyncio.get_running_loop()
        filepath, info = await loop.run_in_executor(None, extract_and_download)
        
        thumbnail_path = filepath.rsplit('.', 1)[0] + '.jpg'
        if not os.path.exists(thumbnail_path):
            thumbnail_path = filepath.rsplit('.', 1)[0] + '.webp'
            if not os.path.exists(thumbnail_path):
                thumbnail_path = None
                
        return {
            "status": "success",
            "filepath": filepath,
            "title": info.get('title', 'Video'),
            "duration": info.get('duration', 0),
            "thumbnail": thumbnail_path
        }
    except Exception as e:
        error_str = str(e)
        if "max-filesize" in error_str.lower():
            return {"status": "error", "error": f"Video is too large. Maximum size is {int(MAX_FILE_SIZE / (1024*1024))} MB."}
        return {"status": "error", "error": error_str}

async def download_video(url: str) -> dict:
    """Entry point for video downloading with retries."""
    return await retry_download(_download_video_impl, url)
