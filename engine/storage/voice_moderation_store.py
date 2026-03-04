from __future__ import annotations
import json
from typing import List, Dict
from .redis_client import get_redis


class VoiceModerationStore:
    """
    Armazenamento de configurações de moderação de voz por guild.
    Estrutura de chaves:
      - {ns}:settings:{guild_id} -> HASH com configurações diversas
        - moderator_roles: JSON array de role IDs que podem moderar
        - target_roles: JSON array de role IDs que podem ser mutados
    """
    def __init__(self, url: str | None = None, namespace: str = "aiko:voice_mod"):
        self._r = get_redis(url)
        self.ns = namespace

    def _key_settings(self, guild_id: int | str) -> str:
        return f"{self.ns}:settings:{guild_id}"

    # ---------- Configurações da guild ----------
    async def get_guild_config(self, guild_id: int | str) -> Dict[str, str]:
        """
        Retorna o dict de configurações da guild (strings).
        """
        return await self._r.hgetall(self._key_settings(guild_id)) or {}

    async def get_moderator_roles(self, guild_id: int | str) -> List[int]:
        """
        Retorna a lista de role IDs que podem moderar.
        """
        cfg = await self.get_guild_config(guild_id)
        raw = cfg.get("moderator_roles", "[]")
        try:
            return json.loads(raw) if raw else []
        except Exception:
            return []

    async def get_target_roles(self, guild_id: int | str) -> List[int]:
        """
        Retorna a lista de role IDs que podem ser mutados.
        """
        cfg = await self.get_guild_config(guild_id)
        raw = cfg.get("target_roles", "[]")
        try:
            return json.loads(raw) if raw else []
        except Exception:
            return []

    async def add_moderator_role(self, guild_id: int | str, role_id: int) -> None:
        """
        Adiciona um cargo à lista de moderadores.
        """
        roles = await self.get_moderator_roles(guild_id)
        if role_id not in roles:
            roles.append(role_id)
            await self._r.hset(
                self._key_settings(guild_id),
                "moderator_roles",
                json.dumps(roles)
            )

    async def remove_moderator_role(self, guild_id: int | str, role_id: int) -> bool:
        """
        Remove um cargo da lista de moderadores.
        Retorna True se o cargo existia e foi removido.
        """
        roles = await self.get_moderator_roles(guild_id)
        if role_id in roles:
            roles.remove(role_id)
            await self._r.hset(
                self._key_settings(guild_id),
                "moderator_roles",
                json.dumps(roles)
            )
            return True
        return False

    async def add_target_role(self, guild_id: int | str, role_id: int) -> None:
        """
        Adiciona um cargo à lista de alvos.
        """
        roles = await self.get_target_roles(guild_id)
        if role_id not in roles:
            roles.append(role_id)
            await self._r.hset(
                self._key_settings(guild_id),
                "target_roles",
                json.dumps(roles)
            )

    async def remove_target_role(self, guild_id: int | str, role_id: int) -> bool:
        """
        Remove um cargo da lista de alvos.
        Retorna True se o cargo existia e foi removido.
        """
        roles = await self.get_target_roles(guild_id)
        if role_id in roles:
            roles.remove(role_id)
            await self._r.hset(
                self._key_settings(guild_id),
                "target_roles",
                json.dumps(roles)
            )
            return True
        return False
