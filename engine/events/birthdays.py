from __future__ import annotations
import random
import datetime as dt
from zoneinfo import ZoneInfo
import discord
from engine.storage.birthdays_store import BirthdaysStore


TZ = ZoneInfo("America/Sao_Paulo")

BIRTHDAY_MESSAGES = [
    "🎉 Feliz aniversário! Que seu dia seja incrível! 🥳",
    "🥳 Parabéns! Muitas felicidades e realizações neste novo ano! 🎂",
    "🎂 Feliz aniversário! Aproveite cada momento! 🎉",
    "🎈 Muita alegria no seu dia! Parabéns pelo seu aniversário! 🥳",
    "🍰 Feliz aniversário! Que seja um ano incrível pra você! 🎉",
]

def get_random_birthday_message() -> str:
    return random.choice(BIRTHDAY_MESSAGES)

def _now_brt() -> dt.datetime:
    return dt.datetime.now(TZ)

async def check_announce_for_guild(guild: discord.Guild, store: BirthdaysStore) -> bool:
    """
    Verifica se deve anunciar para a guild agora (janela de 60s)
    e faz o anúncio se for o horário configurado.
    """
    cfg = await store.get_guild_cfg(guild.id)
    hour = int(cfg.get("birthday_hour", 9))
    minute = int(cfg.get("birthday_minute", 0))
    last_date = cfg.get("last_birthday_announce_date")

    now = _now_brt()
    today = now.date().isoformat()
    if last_date == today:
        return False  # já anunciou hoje

    due = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    delta_s = (now - due).total_seconds()

    # dentro da janela (horário + 59s) -> Anuncia
    if 0 <= delta_s <= 59:
        done = await announce_for_guild(guild, store)
        if done:
            await store.update_guild_cfg(guild.id, last_birthday_announce_date=today)
            return True

    return False

async def announce_for_guild(guild: discord.Guild, store: BirthdaysStore, forced: bool = False) -> bool:
    """
    Anuncia aniversariantes da guild (canal configurado; fallback: canal do sistema/primeiro permitido).
    """
    cfg = await store.get_guild_cfg(guild.id)
    channel_id = cfg.get("birthday_channel_id")
    channel = guild.get_channel(int(channel_id)) if channel_id else None

    if not channel:
        me = guild.me
        channel = guild.system_channel or next(
            (c for c in guild.text_channels if c.permissions_for(me).send_messages),
            None
        )
        if not channel:
            return False

    ddmm = _now_brt().strftime("%d/%m")
    users = await store.find_birthdays_ddmm(ddmm, guild.id)

    if not users:
        if forced:
            await channel.send("Sem aniversariantes hoje!")
            return True
        return False

    mentions = " ".join(f"<@{uid}>" for uid in users)
    msg = f"🎉 **Aniversariantes de hoje**: {mentions}\n{get_random_birthday_message()}"
    await channel.send(msg)
    return True
