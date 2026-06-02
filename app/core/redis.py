# pyrefly: ignore [missing-import]
import redis.asyncio as redis
from app.core.config import settings

class RedisManager:
    def __init__(self):
        self.redis_client = None

    async def init_redis(self):
        if settings.REDIS_URL:
            self.redis_client = redis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True
            )
            # Test connection
            try:
                await self.redis_client.ping()
                print("Redis connected successfully")
            except Exception as e:
                print(f"Failed to connect to Redis: {e}")
                self.redis_client = None

    async def close_redis(self):
        if self.redis_client:
            await self.redis_client.close()

redis_manager = RedisManager()
