import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

PORT = int(os.getenv("PORT", "8000"))

# Validation matching prompt requirements
MAX_DURATION = 10 * 60  # 10 minutes max
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB max

DOWNLOAD_DIR = "downloads"

if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)
