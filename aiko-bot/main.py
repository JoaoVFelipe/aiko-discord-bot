import os
import discord
from dotenv import load_dotenv
from engine import music_player

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
        await message.channel.send('I am connected and working!')
        return
    
    if message.content.startswith('!play'):
        await music_player.execute(message)
        return
    
    if message.content.startswith('!next'):
        await music_player.execute_skip(message)
        return

    if message.content.startswith('!stop'):
        await music_player.execute_stop(message)
        return

client.run(token)