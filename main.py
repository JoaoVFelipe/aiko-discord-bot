import os
import asyncio
import logging
import signal

from dotenv import load_dotenv

import discord
from discord.ext import commands

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from zoneinfo import ZoneInfo

from engine import discord_actions, general
from engine.scheduler.jobs import register_wotd_daily_job, register_birthdays_minutely_job, register_music_inactivity_job

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
## Funções para as features que precisam rodar de tempos em tempos
scheduler = AsyncIOScheduler(
    timezone=ZoneInfo("America/Sao_Paulo"),
    job_defaults={
        "coalesce": True,         
        "max_instances": 1,      
        "misfire_grace_time": 30,  
    },
)

# ----------------- EVENTOS -----------------
@bot.event
async def on_ready():
    ## Inicia o bot e registra os eventos schedule
    log.info(f"Aiko bot conectado como {bot.user} (id={bot.user.id})")

    if not getattr(bot, "_scheduler_started", False):
        register_music_inactivity_job(scheduler, interval_minutes=10)
        register_birthdays_minutely_job(bot, scheduler)
        register_wotd_daily_job(bot, scheduler, hour=12, minute=0)
        scheduler.start()
        bot._scheduler_started = True
        bot.scheduler = scheduler
        log.info("Scheduler iniciado.")

# Comandos gerais - Fora dos cogs
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
    # Carrega cogs (responsaveis pelos comandos)
    await bot.load_extension("engine.cogs.birthdays") 
    await bot.load_extension("engine.cogs.wotd")
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
