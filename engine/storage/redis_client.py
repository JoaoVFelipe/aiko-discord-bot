from __future__ import annotations
import os

from dotenv import load_dotenv
import redis.asyncio as redis

load_dotenv()

DEFAULT_URL_ENV_VARS = ("UPSTASH_REDIS_URL", "REDIS_URL")

def get_redis(url: str | None = None) -> "redis.Redis":
    if not url:
        for env in DEFAULT_URL_ENV_VARS:
            if os.getenv(env):
                url = os.getenv(env)
                break
    url = url or "redis://localhost:6379/0"
    return redis.from_url(url, decode_responses=True)
