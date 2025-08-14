from apscheduler.triggers.cron import CronTrigger
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

import discord
import logging

from pytz import timezone
from zoneinfo import ZoneInfo

from engine.music_player import music_player
from engine.events.wotd import post_wotd
from engine.events.birthdays import check_announce_for_guild

from engine.storage.wotd_store import WOTDStore
from engine.storage.birthdays_store import BirthdaysStore


TZ = timezone("America/Sao_Paulo")
log = logging.getLogger("aiko.main")

def register_music_inactivity_job(
    scheduler: AsyncIOScheduler,
    interval_minutes: int = 10,
) -> None:
    """
    Verifica periodicamente filas inativas para desconectar o bot de canais de voz.
    """
    async def _job():
        try:
            result = await music_player.check_inactivity_queues()
            if result:
                log.debug("[player - music] Inactivity check result: %s", result)
        except Exception:
            log.exception("Erro ao verificar inatividade das filas de música")
    scheduler.add_job(
        _job,
        trigger=IntervalTrigger(minutes=interval_minutes),
        id="music_inactivity_check",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=30,
    )

def register_birthdays_minutely_job(bot: discord.Client, scheduler: AsyncIOScheduler) -> None:
    """
    Roda a cada minuto e verifica todas as guilds para anunciar os aniversários no horário solicitado.
    """
    store = BirthdaysStore()

    async def _job():
        # bot.guilds pode estar vazio até o cache aquecer; trate isso como no restante da app
        for guild in list(bot.guilds):
            try:
                announced = await check_announce_for_guild(guild, store)
                if announced:
                    log.info(f"[events - birthdays] Anúncio enviado em guild {guild.id}")
            except Exception as eg:
                log.exception(f"Erro ao anunciar em guild {guild.id}: {eg}")
                pass
    scheduler.add_job(
        _job,
        trigger=CronTrigger(minute="*", timezone=TZ),
        id="birthdays_minutely_check",
        replace_existing=True,
    )


def register_wotd_daily_job(bot, scheduler, hour=12, minute=0):
    tz = ZoneInfo("America/Sao_Paulo")
    store = WOTDStore()

    async def _job():
        try:
            data = await store.get_today_word()
            word = data.get("word")
            lookup_word = data.get("lookup")

            mapping = await store.all_guild_channels()
            for guild_id, chan_ids in mapping.items():
                for cid in chan_ids:
                    try:
                        ch = bot.get_channel(cid) or await bot.fetch_channel(cid)
                        if isinstance(ch, (discord.TextChannel, discord.Thread)):
                            await post_wotd(ch, word, lookup_word=lookup_word)
                            log.info(f"[events - wotd] Palavra do dia enviada no canal {cid}")
                    except discord.Forbidden:
                        log.exception(f"Erro ao anunciar em canal {cid}: Sem permissão para falar")
                    except discord.HTTPException as e:
                        log.exception(f"Erro ao anunciar em canal {cid}: {e}")
        except Exception as e:
            log.exception("Falha ao executar job de WOTD: %s", e)

    scheduler.add_job(
        _job,
        trigger=CronTrigger(hour=hour, minute=minute, timezone=tz),
        id="wotd_daily",
        replace_existing=True,
        coalesce=True,         
        misfire_grace_time=300, 
    )