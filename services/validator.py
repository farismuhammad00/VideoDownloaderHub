import os
import asyncio
import yt_dlp
from config import MAX_DURATION, MAX_FILE_SIZE

async def validate_url(url: str) -> dict:
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': True,
        'extractor_args': {'youtube': ['player_client=ios', 'web']},
    }
    
    # Use absolute path for cookies.txt
    current_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(current_dir)
    cookie_path = os.path.join(root_dir, 'cookies.txt')
    
    if os.path.exists(cookie_path):
        ydl_opts['cookiefile'] = cookie_path
    
    def extract_info():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=False)
            
    try:
        loop = asyncio.get_running_loop()
        info = await loop.run_in_executor(None, extract_info)
        
        if not info:
            return {"valid": False, "error": "Could not extract information from the URL."}
            
        duration = info.get('duration') or 0
        if duration > MAX_DURATION:
            return {"valid": False, "error": f"Video is too long ({int(duration)}s). Maximum duration is {MAX_DURATION}s."}
            
        # Filesize is often missing or approximate in extract_flat, 
        # but if it exists we can check it.
        filesize = info.get('filesize_approx') or info.get('filesize') or 0
        if filesize > MAX_FILE_SIZE:
            return {"valid": False, "error": f"Video is too large. Maximum size is {int(MAX_FILE_SIZE / (1024*1024))} MB."}
            
        return {"valid": True, "info": info}
        
    except Exception as e:
        return {"valid": False, "error": f"Unsupported or invalid URL. Details: {str(e)}"}
