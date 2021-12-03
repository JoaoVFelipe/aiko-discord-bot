import discord
import youtube_dl
import asyncio
import re, requests, subprocess, urllib.parse, urllib.request

from engine import general_actions

# General variables
queue = {}

# Code to play music from youtube 
ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': 'downloads/%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0'  # ipv6 addresses cause issues sometimes
}

ffmpeg_options = {
    'options': '-vn'
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
        if 'entries' in data:
            # take first item from a playlist
            data = data['entries'][0]
        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

async def execute(message):
    search_string = get_search(message)
    song_url = get_youtube_video(search_string)
    player = await YTDLSource.from_url(song_url, stream=True)

    serverQueue = queue.get(message.guild.id)

    if not serverQueue:
        queueContruct = {
            "text_channel": message.channel,
            "voice_channel": "",
            "connection": "",
            "songs": [],
            "playing": True 
        }

        queue[message.guild.id] = queueContruct
        queueContruct['songs'].append(song_url)

        # Connect to user voice channel
        connection = await general_actions.connect_voice_channel(message)

        if not connection:
            return
        else:
            queueContruct['connection'] = connection
            queueContruct['voice_channel'] = connection.channel
            await play(message.guild, queueContruct['songs'][0])
            return await general_actions.send_message(message, "Tocando agora: {}".format(player.title))
    else:
        serverQueue['songs'].append(song_url)
        if len(serverQueue['songs']) == 1:
            await play(message.guild, serverQueue['songs'][0])
            return await general_actions.send_message(message, "Tocando agora: {}".format(player.title))
        else: 
            return await general_actions.send_message(message, '{} foi adicionado a fila! Total de músicas na fila: {}'.format(player.title, len(serverQueue['songs'])-1))

async def execute_skip(message): 
    if not message.author.voice.channel:
        return await general_actions.send_message(message, "Você precisa estar em um canal de voz para pular alguma música!")

    serverQueue = queue.get(message.guild.id)

    if not serverQueue:
        return await general_actions.send_message(message, "Não há músicas para pular!")

    serverQueue['connection'].stop()

async def execute_stop(message):
    if not message.author.voice.channel:
        return await general_actions.send_message(message, "Você precisa estar em um canal de voz para parar a música!")

    serverQueue = queue.get(message.guild.id)

    if not serverQueue:
        return await general_actions.send_message(message, "Não há músicas para parar!")
        
    serverQueue['songs'] = []
    serverQueue['connection'].stop()
    return
   

async def play(guild, song):
    serverQueue = queue.get(guild.id)
    if not song:
        serverQueue['voice_channel'].leave()
        queue.pop(guild.id)
        return
    
    if not serverQueue:
        return

    player = await YTDLSource.from_url(song, stream=True)
    serverQueue['connection'].play(player, after= lambda e: asyncio.run(play_next(serverQueue, guild)))

async def play_next(serverQueue, guild):
    if len(serverQueue['songs']):
        serverQueue['songs'].pop(0)

    if len(serverQueue['songs']):
        to_play = serverQueue['songs'][0]
        await play(guild, to_play)
    else:
        return

def get_search(message):
    search_string_array = message.content.lower().split(' ')
    search_string_array.pop(0)
    formmated_search_string = ' '.join(search_string_array)
    return formmated_search_string

def get_youtube_video(search):
    # Format the search term
    query_string = urllib.parse.urlencode({"search_query": search})
    # Format the search url on youtube
    format_url = urllib.request.urlopen("https://www.youtube.com/results?" + query_string)
    # Find all the video results
    search_results = re.findall(r"watch\?v=(\S{11})", format_url.read().decode())

    if len(search_results):
        # Get the first result
        clip_url = "https://www.youtube.com/watch?v=" + "{}".format(search_results[0])
        return clip_url
    else:
        return False