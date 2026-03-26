import time
import logging
from services.redis_client import redis_db

logger = logging.getLogger(__name__)

class RedisAntiSpamMiddleware:
    def __init__(self, time_window=60, max_requests=5, cooldown=5):
        self.time_window = time_window
        self.max_requests = max_requests
        self.cooldown = cooldown
        
        # Fallback memory storage
        self.users = {}

    async def check_user(self, user_id: int) -> bool:
        redis = await redis_db.get_client()
        now = time.time()
        
        if not redis:
            logger.warning("Redis not available, using memory fallback for anti-spam")
            return self._memory_check(user_id, now)

        try:
            spam_key = f"spam:{user_id}"
            last_req_key = f"spam:last_req:{user_id}"
            
            last_req = await redis.get(last_req_key)
            if last_req and (now - float(last_req)) < self.cooldown:
                return False
                
            requests = await redis.incr(spam_key)
            
            if requests == 1:
                await redis.expire(spam_key, self.time_window)
            
            if requests > self.max_requests:
                return False
                
            await redis.set(last_req_key, str(now), ex=self.cooldown)
            return True
        except Exception as e:
            logger.error(f"Redis anti-spam error: {e}")
            return self._memory_check(user_id, now)

    def _memory_check(self, user_id: int, now: float) -> bool:
        if user_id not in self.users:
            self.users[user_id] = [now]
            return True
            
        timestamps = self.users[user_id]
        if timestamps and (now - timestamps[-1]) < self.cooldown:
            return False
            
        timestamps = [ts for ts in timestamps if now - ts < self.time_window]
        
        if len(timestamps) >= self.max_requests:
            self.users[user_id] = timestamps
            return False
            
        timestamps.append(now)
        self.users[user_id] = timestamps
        return True

anti_spam = RedisAntiSpamMiddleware()
