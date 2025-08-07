import os
import asyncio
import logging

import signal
import sys

import discord
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv

from engine import discord_actions, general
from engine.music_player import music_player

# Configura logging para melhor depuração
logging.basicConfig(level=logging.INFO)

# Carrega variáveis de ambiente
load_dotenv()
TOKEN = os.getenv('BOT_TOKEN')

# Configura intents necessários
intents = discord.Intents.default()
intents.message_content = True

# Cria cliente do Discord
client = discord.Client(intents=intents)

# Scheduler para tarefas agendadas
scheduler = AsyncIOScheduler()

async def timed_job():
    """Função executada periodicamente pelo scheduler"""
    result = await music_player.check_inactivity_queues()
    print(result)

# ----------------- EVENTOS -----------------
@client.event
async def on_ready():
    print(f"Aiko bot conectado como {client.user}")
    # Inicia scheduler quando o bot estiver pronto
    if not scheduler.running:
        scheduler.add_job(timed_job, "interval", minutes=15)
        scheduler.start()
        print("Scheduler iniciado.")

@client.event
async def on_message(message: discord.Message):
    # Ignora mensagens do próprio bot
    if message.author.bot:
        return

    content = message.content.strip()

    # ------------- Comandos ---------------
    if content.startswith('!test'):
        await discord_actions.send_message(
            channel=message.channel, 
            message_text='I am connected and working!'
        )

    elif content.startswith('!help'):
        await general.execute_help(message)
        
    # ----------- Music player commands --------------
    elif content.startswith('!play'):
        await music_player.execute(message)
    
    elif content.startswith('!resume'):
        await music_player.execute_resume(message)

    elif content.startswith('!pause'):
        await music_player.execute_pause(message)

    elif content.startswith('!next'):
        await music_player.execute_skip(message)

    elif content.startswith('!stop'):
        await music_player.execute_stop(message)

    elif content.startswith('!queue'):
        await music_player.execute_list_queue(message)

    elif content.startswith('!jump_to'):
        await music_player.execute_jump_to(message)

    # # ------------ AI commands ------------------
    # if message.content.startswith('!aiko'):
    #    await ai_chat.execute_ai_command(message)
# ----------------- EXECUÇÃO -----------------
if __name__ == "__main__":
    if not TOKEN:
        raise ValueError("O token do bot não foi definido no .env (BOT_TOKEN).")
    print("Iniciando bot...")
    client.run(TOKEN)

def shutdown_handler(sig, frame):
    print("Encerrando bot...")
    # Desconecta do Discord
    loop = asyncio.get_event_loop()
    loop.create_task(client.close())
    loop.stop()
    sys.exit(0)

signal.signal(signal.SIGINT, shutdown_handler)
signal.signal(signal.SIGTERM, shutdown_handler)