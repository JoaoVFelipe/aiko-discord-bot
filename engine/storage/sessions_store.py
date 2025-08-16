# engine/storage/sessions_store.py
from __future__ import annotations
from typing import Dict
from .redis_client import get_redis

class SessionsStore:
    """
    Configurações de sessões instantâneas por guild.
    Estrutura de chaves:
      - {ns}:settings:{guild_id} -> HASH com configs:
          - session_channel_id: str | None
          - session_mode: 'dm' | 'channel' | 'both'
          - session_external_notify: '0' ou '1' (reserva para integrações futuras)
    """
    def __init__(self, url: str | None = None, namespace: str = "aiko:sessions"):
        self._r = get_redis(url)
        self.ns = namespace

    def _key_settings(self, guild_id: int | str) -> str:
        return f"{self.ns}:settings:{guild_id}"

    async def get_guild_cfg(self, guild_id: int | str) -> Dict[str, str]:
        return await self._r.hgetall(self._key_settings(guild_id)) or {}

    async def update_guild_cfg(self, guild_id: int | str, **kwargs) -> None:
        if not kwargs:
            return
        mapping = {k: ("" if v is None else str(v)) for k, v in kwargs.items()}
        await self._r.hset(self._key_settings(guild_id), mapping=mapping)
