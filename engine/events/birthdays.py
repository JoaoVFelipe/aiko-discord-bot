# engine/events/birthdays.py
import random
import discord
import datetime as dt
from zoneinfo import ZoneInfo
from engine.json_store import find_birthdays_ddmm, get_guild_cfg, update_guild_cfg

TZ = ZoneInfo("America/Sao_Paulo")

BIRTHDAY_MESSAGES = [
    "🎉 Feliz aniversário! Que seu dia seja incrível! 🥳",
    "🥳 Parabéns! Muitas felicidades e realizações neste novo ano! 🎂",
    "🎂 Feliz aniversário! Aproveite cada momento! 🎉",
    "🎈 Muita alegria no seu dia! Parabéns pelo seu aniversário! 🥳",
    "🍰 Feliz aniversário! Que seja um ano incrível pra você! 🎉",
]

def get_random_birthday_message():
    return random.choice(BIRTHDAY_MESSAGES)

def _now_brt():
    return dt.datetime.now(TZ)

async def check_announce_for_guild(guild: discord.Guild) -> bool:
    cfg = await get_guild_cfg(str(guild.id))
    hour = int(cfg.get("birthday_hour", 9))
    minute = int(cfg.get("birthday_minute", 0))
    last_date = cfg.get("last_birthday_announce_date")

    now = _now_brt()
    today = now.date().isoformat()
    if last_date == today:
        return False  # já anunciou hoje

    # horário alvo de HOJE
    due = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

    # dispara apenas dentro da janela [due, due+59s]
    delta_s = (now - due).total_seconds()
    if 0 <= delta_s <= 59:
        done = await announce_for_guild(guild)
        if done:
            await update_guild_cfg(str(guild.id), last_birthday_announce_date=today)
            return True

    # fora da janela → não anuncia
    return False

async def announce_for_guild(guild: discord.Guild) -> bool:
    cfg = await get_guild_cfg(str(guild.id))
    channel_id = cfg.get("birthday_channel_id")
    channel = guild.get_channel(int(channel_id)) if channel_id else None
    if not channel:
        me = guild.me
        channel = guild.system_channel or next((c for c in guild.text_channels if c.permissions_for(me).send_messages), None)
    if not channel:
        return False

    ddmm = _now_brt().strftime("%d/%m")
    users = await find_birthdays_ddmm(ddmm, str(guild.id))  # <-- FILTRA por guild
    if not users:
        return False

    mentions = " ".join(f"<@{uid}>" for uid in users)
    msg = f"🎉 **Aniversariantes de hoje**: {mentions}\n{random.choice(BIRTHDAY_MESSAGES)}"
    await channel.send(msg)
    return True
