import os
import discord
from dotenv import load_dotenv
from engine import music_player, general_actions

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
        await general_actions.send_message(messageEvent=message, messageText='I am connected and working!')
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

client.run(token)