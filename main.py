import os
import discord
import asyncio

from dotenv import load_dotenv
from engine import music_player, discord_actions, general

load_dotenv()

# Connects to discord
client = discord.Client()
token = os.getenv('BOT_TOKEN')

# Registered events
@client.event
async def on_ready():
    print('Aiko bot is ready to start!')

@client.event
async def on_message(message):
    if message.author == client.user or message.author.bot:
        return

    if message.content.startswith('!test'):
        await discord_actions.send_message(message_event=message, message_text='I am connected and working!')
        return

    if message.content.startswith('!help'):
        await general.execute_help(message)
        return

    ############ MUSIC COMMANDS ##############
    if message.content.startswith('!play'):
        await music_player.execute(message)
        return

    if message.content.startswith('!pause'):
        await music_player.execute_pause(message)
        return

    if message.content.startswith('!next'):
        await music_player.execute_skip(message)
        return

    if message.content.startswith('!stop'):
        await music_player.execute_stop(message)
        return
        
    if message.content.startswith('!queue'):
        await music_player.execute_list_queue(message)
        return

    if message.content.startswith('!jump_to'):
        await music_player.execute_jump_to(message)
        return

client.run(token)