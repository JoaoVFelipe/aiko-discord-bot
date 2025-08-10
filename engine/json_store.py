# engine/json_store.py
import json, os, asyncio
from typing import Dict, Any, List, Optional

_STORE_PATH = os.path.join("data", "birthdays.json")

async def _load() -> Dict[str, Any]:
    def _sync_load():
        if not os.path.exists(_STORE_PATH):
            os.makedirs(os.path.dirname(_STORE_PATH), exist_ok=True)
            return {"guilds": {}}
        with open(_STORE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return await asyncio.to_thread(_sync_load)

async def _save(data: Dict[str, Any]) -> None:
    def _sync_save():
        os.makedirs(os.path.dirname(_STORE_PATH), exist_ok=True)
        with open(_STORE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    await asyncio.to_thread(_sync_save)

async def get_guild_cfg(guild_id: str) -> Dict[str, Any]:
    data = await _load()
    g = data["guilds"].setdefault(guild_id, {"settings": {}, "users": {}})
    await _save(data)  # garante criação
    return g["settings"]

async def update_guild_cfg(guild_id: str, **kwargs) -> None:
    data = await _load()
    g = data["guilds"].setdefault(guild_id, {"settings": {}, "users": {}})
    g["settings"].update(kwargs)
    await _save(data)

# -------- usuários por GUILD --------
async def upsert_birthday_user(guild_id: str, user_id: str, ddmm: str, name: Optional[str]=None) -> None:
    data = await _load()
    g = data["guilds"].setdefault(guild_id, {"settings": {}, "users": {}})
    entry = g["users"].get(user_id, {})
    entry["ddmm"] = ddmm
    if name:
        entry["name"] = name
    g["users"][user_id] = entry
    await _save(data)

async def remove_birthday_user(guild_id: str, user_id: str) -> bool:
    data = await _load()
    g = data["guilds"].setdefault(guild_id, {"settings": {}, "users": {}})
    existed = user_id in g["users"]
    g["users"].pop(user_id, None)
    await _save(data)
    return existed

async def list_birthday_users(guild_id: str) -> Dict[str, Dict[str, str]]:
    data = await _load()
    g = data["guilds"].get(guild_id, {"users": {}})
    return g.get("users", {})

async def find_birthdays_ddmm(ddmm: str, guild_id: str) -> List[str]:
    """Retorna lista de user_ids COM aniversário dd/mm dentro da guild."""
    users = await list_birthday_users(guild_id)
    return [uid for uid, v in users.items() if v.get("ddmm") == ddmm]
