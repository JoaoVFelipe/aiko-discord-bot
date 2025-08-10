import os
import asyncio
import logging
import signal
import sys

from dotenv import load_dotenv

import discord
from discord.ext import commands

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED
from apscheduler.triggers.interval import IntervalTrigger

from zoneinfo import ZoneInfo

from engine import discord_actions, general
from engine.music_player import music_player
from engine.events import birthdays

# ----------------- LOGGING -----------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("aiko.main")

# ----------------- ENV -----------------
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise ValueError("O token do bot não foi definido no .env (BOT_TOKEN).")

# ----------------- INTENTS/BOT -----------------
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True 

bot = commands.Bot(command_prefix="!#", intents=intents, help_command=None)

# ----------------- SCHEDULER -----------------
scheduler = AsyncIOScheduler(
    timezone=ZoneInfo("America/Sao_Paulo"),
    job_defaults={
        "coalesce": True,          # junta execuções atrasadas em 1
        "max_instances": 1,        # evita overlaps do mesmo job
        "misfire_grace_time": 30,  # tolerância para pequenos atrasos
    },
)

def _job_listener(event):
    if event.exception:
        log.exception(f"[scheduler] Job {getattr(event, 'job_id', '?')} falhou", exc_info=event.exception)
    else:
        log.debug(f"[scheduler] Job {getattr(event, 'job_id', '?')} executado com sucesso")

scheduler.add_listener(_job_listener, EVENT_JOB_ERROR | EVENT_JOB_EXECUTED)

async def inactivity_check_job():
    try:
        result = await music_player.check_inactivity_queues()
        if result:
            log.info(f"[music] {result}")
    except Exception as e:
        log.exception(f"Erro no inactivity_check_job: {e}")

async def birthday_announcement_job():
    """Roda 1x/min e tenta anunciar para cada guild, se 'já deu a hora' e não anunciou hoje."""
    try:
        # itera pelas guilds atuais do bot
        for guild in bot.guilds:
            try:
                announced = await birthdays.check_announce_for_guild(guild)
                if announced:
                    log.info(f"[events - birthdays] Anúncio enviado em guild {guild.id}")
            except Exception as eg:
                log.exception(f"Erro ao anunciar em guild {guild.id}: {eg}")
    except Exception as e:
        log.exception(f"Erro no birthday_announcement_job: {e}")

# ----------------- EVENTOS -----------------
@bot.event
async def on_ready():
    log.info(f"Aiko bot conectado como {bot.user} (id={bot.user.id})")

    if not getattr(bot, "_scheduler_started", False):
        scheduler.add_job(
            inactivity_check_job,
            trigger=IntervalTrigger(minutes=15),
            id="music_inactivity_check",
            replace_existing=True,
            next_run_time=None,
        )

        scheduler.add_job(
            birthday_announcement_job,
            trigger=IntervalTrigger(minutes=1),
            id="bday_announcement_check",
            replace_existing=True,
        )

        scheduler.start()
        bot._scheduler_started = True

        bot.scheduler = scheduler

        log.info("Scheduler iniciado.")

# Comandos simples fora do cog (mantidos)
@bot.command(name="test")
async def test_cmd(ctx: commands.Context):
    await discord_actions.send_message(channel=ctx.channel, message_text="I am connected and working!")

@bot.command(name="help")
async def help_cmd(ctx: commands.Context):
    await general.execute_help(ctx.message)

@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    from discord.ext.commands import MissingPermissions, BadArgument, UserInputError, CommandNotFound
    if isinstance(error, CommandNotFound):
        return
    if isinstance(error, MissingPermissions):
        return await ctx.reply("Você não tem permissão para executar este comando.")
    if isinstance(error, (BadArgument, UserInputError)):
        return await ctx.reply("Argumentos inválidos para este comando.")
    log.exception(f"Erro em comando: {error}")
    try:
        await ctx.reply("⚠️ Ocorreu um erro ao executar este comando.")
    except:
        pass

# ----------------- BOOTSTRAP -----------------
async def startup():
    # Carrega cogs
    await bot.load_extension("engine.cogs.birthdays") 
    await bot.load_extension("engine.cogs.player")  

def _install_signal_handlers(loop: asyncio.AbstractEventLoop):
    def _handle(sig):
        log.info(f"Recebido sinal {sig.name}, encerrando…")
        if scheduler.running:
            scheduler.shutdown(wait=False)
        loop.create_task(bot.close())

    for s in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(s, _handle, s)
        except NotImplementedError:
            signal.signal(s, lambda *_: asyncio.create_task(bot.close()))

if __name__ == "__main__":
    log.info("Iniciando bot...")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    _install_signal_handlers(loop)

    try:
        loop.run_until_complete(startup())
        bot.run(TOKEN)
    except KeyboardInterrupt:
        pass
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=False)
        log.info("Encerrado.")
