import os
import logging

logger = logging.getLogger(__name__)

def safe_remove(filepath: str):
    if not filepath:
        return
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
            logger.debug(f"Removed file: {filepath}")
    except Exception as e:
        logger.error(f"Failed to remove file {filepath}: {e}")
