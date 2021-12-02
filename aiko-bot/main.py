import os
import discord
from dotenv import load_dotenv
from engine import music_player

load_dotenv()

# Connects to discord
client = discord.Client()

# Registered events
@client.event
async def on_ready():
    print('Aiko bot is ready to start!')

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if message.content.startswith('!test'):
        await message.channel.send('I am connected and working!')
    
    if message.content.startswith('!play'):
        member = message.author
        voiceChannel = member.voice.channel;
        await music_player.play_music_from_youtube(voiceChannel)

client.run(os.getenv('BOT_TOKEN'))