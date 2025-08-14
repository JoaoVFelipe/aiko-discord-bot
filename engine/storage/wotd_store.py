from __future__ import annotations
from typing import Dict, List, Iterable, Optional
from zoneinfo import ZoneInfo
from .redis_client import get_redis
from engine.events import wotd

import asyncio
import json
from datetime import datetime, timedelta

WOTD_KEY = "wotd:current"
SAO_PAULO_TZ = ZoneInfo("America/Sao_Paulo")

class WOTDStore:
    def __init__(self, url: str | None = None, namespace: str = "aiko:wotd:channels"):
        self._r = get_redis(url)
        self.ns = namespace
        self._lock = asyncio.Lock()
        self._mem: Optional[Dict[str, any]] = None

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
        result: Dict[int, List[int]] = {}
        async for key in self._scan_iter(f"{self.ns}:*"):
            try:
                gid = int(str(key).split(":")[-1])
            except ValueError:
                continue
            chans = await self._r.smembers(key)
            result[gid] = [int(x) for x in (chans or [])]
        return result

    async def _scan_iter(self, pattern: str) -> Iterable[str]:  # type: ignore
        async for k in self._r.scan_iter(match=pattern):
            yield k

    # --------- Helpers de data/TTL ---------
    @staticmethod
    def _today_date_str() -> str:
        return datetime.now(SAO_PAULO_TZ).strftime("%Y-%m-%d")

    @staticmethod
    def _seconds_until_midnight_sp() -> int:
        now = datetime.now(SAO_PAULO_TZ)
        tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return int((tomorrow - now).total_seconds())

    # --------- Persistência WOTD (apenas a vigente) ---------
    async def _get_stored_wotd(self) -> Optional[Dict[str, any]]:
        raw = await self._r.get(WOTD_KEY)
        return json.loads(raw) if raw else None

    async def _set_stored_wotd(self, payload: Dict[str, any]) -> None:
        ttl = self._seconds_until_midnight_sp()
        await self._r.set(WOTD_KEY, json.dumps(payload, ensure_ascii=False), ex=ttl)

    # --------- API pública ---------
    async def get_today_word(self) -> Dict[str, any]:
        """
        Retorna {"date", "word", "fetched_at"}.
        Se não existir ou estiver desatualizada, busca uma aleatória via /random
        e grava numa única chave com TTL até 00:00 America/Sao_Paulo.
        """
        async with self._lock:
            today = self._today_date_str()

            # 1) Cache em memória
            if self._mem and self._mem.get("date") == today:
                return self._mem

            # 2) Redis
            data = await self._get_stored_wotd()
            if data and data.get("date") == today and isinstance(data.get("word"), str):
                self._mem = data
                return data

            # 3) Gerar nova
            info = await wotd.fetch_random_word()  # dict {"orth","lookup","description"}
            payload = {
                "date": today,
                "word": info["orth"],      # exibição
                "lookup": info["lookup"],  # slug para consulta
                "fetched_at": datetime.now(SAO_PAULO_TZ).isoformat(),
            }
            await self._set_stored_wotd(payload)
            self._mem = payload
            return payload

    async def refresh_today_word(self, force: bool = False) -> Dict[str, any]:
        """
        Se force=False, apenas retorna a vigente.
        Se force=True, gera e sobrepõe a palavra de hoje (continua 1 única chave).
        """
        async with self._lock:
            if not force:
                return await self.get_today_word()

            today = self._today_date_str()
            info = await wotd.fetch_random_word()
            payload = {
                "date": today,
                "word": info["orth"],
                "lookup": info["lookup"],
                "fetched_at": datetime.now(SAO_PAULO_TZ).isoformat(),
            }
            await self._set_stored_wotd(payload)
            self._mem = payload
            return payload
