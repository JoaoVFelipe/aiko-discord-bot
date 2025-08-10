import os, json
from dotenv import load_dotenv
import redis.asyncio as redis 

load_dotenv()
_redis = redis.from_url(os.getenv("UPSTASH_REDIS_URL"), decode_responses=True)
CFG_KEY = "aiko:birthdays:cfg"

async def _load_dict():
    raw = await _redis.get(CFG_KEY)
    if not raw:
        return {"guilds": {}}
    try:
        return json.loads(raw)
    except Exception:
        return {"guilds": {}}

async def _save_dict(data: dict):
    await _redis.set(CFG_KEY, json.dumps(data, ensure_ascii=False))

async def get_guild_cfg(guild_id: str) -> dict:
    data = await _load_dict()
    g = data["guilds"].setdefault(guild_id, {"settings": {}, "users": {}})
    await _save_dict(data)
    return g["settings"]

async def update_guild_cfg(guild_id: str, **kwargs):
    data = await _load_dict()
    g = data["guilds"].setdefault(guild_id, {"settings": {}, "users": {}})
    g["settings"].update(kwargs)
    await _save_dict(data)

async def upsert_birthday_user(guild_id: str, user_id: str, ddmm: str, name: str | None = None):
    data = await _load_dict()
    g = data["guilds"].setdefault(guild_id, {"settings": {}, "users": {}})
    entry = g["users"].get(user_id, {})
    entry["ddmm"] = ddmm
    if name:
        entry["name"] = name
    g["users"][user_id] = entry
    await _save_dict(data)

async def remove_birthday_user(guild_id: str, user_id: str) -> bool:
    data = await _load_dict()
    g = data["guilds"].setdefault(guild_id, {"settings": {}, "users": {}})
    existed = user_id in g["users"]
    g["users"].pop(user_id, None)
    await _save_dict(data)
    return existed

async def list_birthday_users(guild_id: str) -> dict[str, dict]:
    data = await _load_dict()
    g = data["guilds"].get(guild_id, {"users": {}})
    return g.get("users", {})

async def find_birthdays_ddmm(ddmm: str, guild_id: str) -> list[str]:
    users = await list_birthday_users(guild_id)
    return [uid for uid, v in users.items() if v.get("ddmm") == ddmm]
