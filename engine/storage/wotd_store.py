from __future__ import annotations
from typing import Dict, List, Iterable
from .redis_client import get_redis

class WOTDStore:
    """
    Armazena os canais por guild que devem receber a 'palavra do dia'.

    Estrutura de chaves:
      - {ns}:{guild_id}  -> SET com channel_ids (inteiros)
    """
    def __init__(self, url: str | None = None, namespace: str = "aiko:wotd:channels"):
        self._r = get_redis(url)
        self.ns = namespace

    def _key(self, guild_id: int | str) -> str:
        return f"{self.ns}:{guild_id}"

    # --------- Operações por guild ---------
    async def add_channel(self, guild_id: int | str, channel_id: int | str) -> None:
        await self._r.sadd(self._key(guild_id), int(channel_id))

    async def remove_channel(self, guild_id: int | str, channel_id: int | str) -> None:
        await self._r.srem(self._key(guild_id), int(channel_id))

    async def list_channels(self, guild_id: int | str) -> List[int]:
        members = await self._r.smembers(self._key(guild_id))
        return [int(m) for m in (members or [])]

    async def clear_guild(self, guild_id: int | str) -> None:
        await self._r.delete(self._key(guild_id))

    # --------- Agregação ---------
    async def all_guild_channels(self) -> Dict[int, List[int]]:
        """
        Retorna { guild_id: [channel_ids...] } usando SCAN (não bloqueia).
        """
        result: Dict[int, List[int]] = {}
        async for key in self._scan_iter(f"{self.ns}:*"):
            try:
                gid = int(str(key).split(":")[-1])
            except ValueError:
                # ignora chaves que não seguem o padrão esperado
                continue
            chans = await self._r.smembers(key)
            result[gid] = [int(x) for x in (chans or [])]
        return result

    async def _scan_iter(self, pattern: str) -> Iterable[str]: # type: ignore
        """
        Wrapper assíncrono para scan_iter do redis.asyncio.
        """
        async for k in self._r.scan_iter(match=pattern):
            yield k
