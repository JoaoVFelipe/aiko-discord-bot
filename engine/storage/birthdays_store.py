from __future__ import annotations
import json
from typing import Dict, List, Optional
from .redis_client import get_redis

class BirthdaysStore:
    """
    Armazenamento de aniversários por guild, no padrão do WOTDStore.
    Estrutura de chaves:
      - {ns}:settings:{guild_id}  -> HASH com configurações diversas
      - {ns}:users:{guild_id}     -> HASH onde field=user_id, value=JSON {"ddmm": "DD/MM", "name": "..."}
    """
    def __init__(self, url: str | None = None, namespace: str = "aiko:birthdays"):
        self._r = get_redis(url)
        self.ns = namespace

    def _key_settings(self, guild_id: int | str) -> str:
        return f"{self.ns}:settings:{guild_id}"

    def _key_users(self, guild_id: int | str) -> str:
        return f"{self.ns}:users:{guild_id}"

    # ---------- Configurações da guild ----------
    async def get_guild_cfg(self, guild_id: int | str) -> Dict[str, str]:
        """
        Retorna o dict de configurações da guild (strings).
        """
        return await self._r.hgetall(self._key_settings(guild_id)) or {}

    async def update_guild_cfg(self, guild_id: int | str, **kwargs) -> None:
        """
        Faz upsert de configurações (todas como string).
        """
        if not kwargs:
            return
        # Converte valores para string para manter consistência
        mapping = {k: ("" if v is None else str(v)) for k, v in kwargs.items()}
        await self._r.hset(self._key_settings(guild_id), mapping=mapping)

    # ---------- Usuários / aniversários ----------
    async def upsert_birthday_user(
        self,
        guild_id: int | str,
        user_id: int | str,
        ddmm: str,
        name: Optional[str] = None,
    ) -> None:
        """
        Cria/atualiza o registro de aniversário do usuário.
        ddmm no formato 'DD/MM'.
        """
        payload = {"ddmm": ddmm}
        if name:
            payload["name"] = name
        await self._r.hset(self._key_users(guild_id), user_id, json.dumps(payload, ensure_ascii=False))

    async def remove_birthday_user(self, guild_id: int | str, user_id: int | str) -> bool:
        """
        Remove usuário; retorna True se existia.
        """
        removed = await self._r.hdel(self._key_users(guild_id), user_id)
        return bool(removed)

    async def list_birthday_users(self, guild_id: int | str) -> Dict[str, Dict]:
        """
        Retorna dict[user_id] = {"ddmm": "DD/MM", "name": "...?"}
        """
        raw = await self._r.hgetall(self._key_users(guild_id))
        result: Dict[str, Dict] = {}
        for uid, val in (raw or {}).items():
            try:
                result[str(uid)] = json.loads(val) if isinstance(val, str) else val
            except Exception:
                # Em caso de lixo, ignora ou defina um padrão mínimo
                pass
        return result

    async def find_birthdays_ddmm(self, ddmm: str, guild_id: int | str) -> List[str]:
        """
        Retorna a lista de user_ids com aniversário no ddmm.
        (Implementação simples: filtra em memória. Se necessário, dá para criar índice por ddmm.)
        """
        users = await self.list_birthday_users(guild_id)
        return [uid for uid, v in users.items() if v.get("ddmm") == ddmm]
