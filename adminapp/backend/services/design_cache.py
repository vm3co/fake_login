import json
from urllib.parse import urlparse
from backend.services.redis_client import RedisClient
from backend.services.log_manager import Logger

logger = Logger().get_logger()
CACHE_TTL = 86400  # 24小時

def url_to_cache_key(url: str) -> str:
    """轉換 URL 為 Redis Cache Key"""
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url
    parsed = urlparse(url)
    return f"design_tokens:{parsed.netloc}"

async def get_cached_design(url: str) -> dict | None:
    """從 Redis 獲取設計快取"""
    key = url_to_cache_key(url)
    try:
        redis_client = RedisClient()
        client = await redis_client.get_client()
        data_str = await client.get(key)
        if data_str:
            logger.info(f"[CACHE HIT] 命中設計快取: {key}")
            return json.loads(data_str)
        return None
    except Exception as e:
        logger.error(f"讀取設計快取失敗 ({key}): {e}")
        return None

async def set_cached_design(url: str, data: dict) -> None:
    """將設計資料寫入 Redis 快取"""
    key = url_to_cache_key(url)
    try:
        redis_client = RedisClient()
        client = await redis_client.get_client()
        await client.setex(key, CACHE_TTL, json.dumps(data))
        logger.info(f"[CACHE SET] 寫入設計快取: {key}")
    except Exception as e:
        logger.error(f"寫入設計快取失敗 ({key}): {e}")
