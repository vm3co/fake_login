import os
import redis.asyncio as redis
from app.services.log_manager import Logger

logger = Logger().get_logger()

class RedisClient:
    _instance = None
    _pool = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RedisClient, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if RedisClient._pool is None:
            try:
                redis_host = os.getenv("REDIS_HOST", "localhost")
                redis_port = int(os.getenv("REDIS_PORT", 6379))
                logger.info(f"Initializing Redis connection pool to {redis_host}:{redis_port}")
                
                RedisClient._pool = redis.ConnectionPool(
                    host=redis_host,
                    port=redis_port,
                    db=0,
                    decode_responses=True
                )
            except Exception as e:
                logger.error(f"Failed to initialize Redis pool: {e}")

    async def get_client(self) -> redis.Redis:
        """
        獲取一個 Redis 客戶端實例 (Context Manager 支援)
        :return: redis.Redis
        """
        if RedisClient._pool is None:
             self.__init__()
             
        return redis.Redis(connection_pool=RedisClient._pool)

    async def close(self):
        """
        關閉連線池 (通常在 App Shutdown 時呼叫)
        """
        if RedisClient._pool:
            await RedisClient._pool.disconnect()
            logger.info("Redis connection pool closed.")
