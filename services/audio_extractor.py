import os
import asyncio
import uuid
import logging
import subprocess
import yt_dlp
from config import DOWNLOAD_DIR, MAX_FILE_SIZE, MAX_DURATION

logger = logging.getLogger(__name__)

def download_filter(info, *args, **kwargs):
    duration = info.get('duration')
    if duration and duration > MAX_DURATION:
        return f"Audio is too long ({int(duration)}s). Maximum is {MAX_DURATION}s."
    return None

def test_ffmpeg_installation() -> bool:
    """Internal test function to confirm FFmpeg works correctly."""
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        return True
    except Exception as e:
        logger.error(f"FFmpeg is missing or not working: {e}")
        return False

async def retry_download(func, *args, retries=3, **kwargs):
    """Wrapper to retry download on failure"""
    for attempt in range(1, retries + 1):
        try:
            result = await func(*args, **kwargs)
            if result.get("status") == "success":
                return result
                
            error_msg = result.get("error", "").lower()
            if "unsupported" in error_msg or "too large" in error_msg or "too long" in error_msg or "unavailable" in error_msg or "max-filesize" in error_msg:
                return result
                
            if attempt == retries:
                logger.error(f"All {retries} retry attempts failed for audio {args}")
                return {"status": "error", "error": "❌ Failed to process audio after multiple attempts."}
                
            delay = 2 ** (attempt - 1)
            logger.warning(f"Audio Attempt {attempt} failed: {error_msg}. Retrying in {delay}s...")
            await asyncio.sleep(delay)
        except Exception as e:
            if attempt == retries:
                logger.error(f"All {retries} retry attempts crashed for audio {args}")
                return {"status": "error", "error": "❌ Failed to process audio after multiple attempts."}
            delay = 2 ** (attempt - 1)
            logger.warning(f"Audio Attempt {attempt} exception: {e}. Retrying in {delay}s...")
            await asyncio.sleep(delay)
    return {"status": "error", "error": "❌ Failed to process audio."}

async def _download_audio_impl(url: str) -> dict:
    if not test_ffmpeg_installation():
        return {"status": "error", "error": "Audio conversion is currently unavailable. Please check the logs."}
        
    file_id = str(uuid.uuid4())
    output_template = os.path.join(DOWNLOAD_DIR, f"{file_id}.%(ext)s")
    
    ydl_opts = {
        'outtmpl': output_template,
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
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
            # The name changes after ffmpeg processing to .mp3
            base_filename = ydl.prepare_filename(info)
            audio_filename = base_filename.rsplit('.', 1)[0] + '.mp3'
            return audio_filename, info
            
    try:
        logger.info(f"Starting audio extraction for: {url}")
        loop = asyncio.get_running_loop()
        filepath, info = await loop.run_in_executor(None, extract_and_download)
        
        logger.info(f"Successfully processed audio for: {url}")
        return {
            "status": "success",
            "filepath": filepath,
            "title": info.get('title', 'Audio'),
            "duration": info.get('duration', 0)
        }
    except yt_dlp.utils.PostProcessingError as e:
        logger.error(f"Post-processing error during audio extraction: {e}")
        return {"status": "error", "error": "Audio conversion is currently unavailable."}
    except Exception as e:
        error_str = str(e)
        if "max-filesize" in error_str.lower():
            return {"status": "error", "error": f"Audio source is too large. Maximum size is {int(MAX_FILE_SIZE / (1024*1024))} MB."}
        logger.error(f"Failed to download or extract audio: {e}")
        return {"status": "error", "error": error_str}

async def download_audio(url: str) -> dict:
    """Entry point for audio processing with retries."""
    return await retry_download(_download_audio_impl, url)
