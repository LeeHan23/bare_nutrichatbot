import redis
import os
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL")
if REDIS_URL:
    cache = redis.from_url(REDIS_URL)
else:
    cache = None

def get_from_cache(key: str):
    if cache:
        return cache.get(key)
    return None

def set_in_cache(key: str, value: str, ttl: int = 3600):
    if cache:
        cache.set(key, value, ex=ttl)