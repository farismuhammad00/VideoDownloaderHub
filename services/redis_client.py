import redis.asyncio as redis
from config import REDIS_URL
import logging

logger = logging.getLogger(__name__)

class RedisClient:
    def __init__(self):
        self._client = None
        self.connected = False

    async def connect(self):
        try:
            self._client = redis.from_url(REDIS_URL, decode_responses=True)
            await self._client.ping()
            self.connected = True
            logger.info("Successfully connected to Redis")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self._client = None
            self.connected = False

    async def get_client(self):
        """Returns the internal redis-py client or None if offline."""
        if not self.connected and self._client is None:
            # Try to connect once if missing, but avoid blocking if offline
            await self.connect()
        return self._client

    async def close(self):
        if self._client:
            await self._client.aclose()

redis_db = RedisClient()

# Simple memory fallback to store url mappings for callback_data
url_memory_store = {}
