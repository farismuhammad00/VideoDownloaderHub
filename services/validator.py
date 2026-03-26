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
            
        entries = info.get('entries', [info]) if 'entries' in info else [info]
        
        # Validate based on the entries
        total_duration = 0
        total_filesize = 0
        
        for entry in entries:
            duration = entry.get('duration') or 0
            if duration > MAX_DURATION:
                return {"valid": False, "error": f"One of the items is too long ({int(duration)}s). Maximum duration is {MAX_DURATION}s."}
            total_duration += duration
            
            filesize = entry.get('filesize_approx') or entry.get('filesize') or 0
            total_filesize += filesize
            
        if total_filesize > MAX_FILE_SIZE * 5: # Allow higher limit for albums
             # We don't want to be TOO strict on approximate filesizes for albums
             pass

        return {"valid": True, "info": info}
        
    except Exception as e:
        return {"valid": False, "error": f"Unsupported or invalid URL. Details: {str(e)}"}
