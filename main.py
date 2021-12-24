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
        
    if message.content.startswith('!queue'):
        await music_player.execute_list_queue(message)
        return

    if message.content.startswith('!jump_to'):
        await music_player.execute_jump_to(message)
        return

@client.event
async def on_voice_state_update(member, before, after):
    if not member.bot or member.id != client.user.id:
        return

    elif before.channel is None:
        voice = after.channel.guild.voice_client
        time = 0
        while True:
            await asyncio.sleep(1)
            time = time + 1
            print('TIMER', time)
            if voice.is_playing() and not voice.is_paused():
                time = 0
            if time == 20:
                print("Disconnecting due to inactivity")
                await music_player.clear_queue_disconect(voice, after.channel.guild)
            if not voice.is_connected():
                break
        

client.run(token)