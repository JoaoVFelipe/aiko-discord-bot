import discord
import youtube_dl
import asyncio
import re, requests, subprocess, urllib.parse, urllib.request

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

async def play_music_from_youtube(message):
    member = message.author
    voice_channel = member.voice.channel
    connection = await voice_channel.connect()

    search_string_array = message.content.lower().split(' ')
    search_string_array.pop(0)
    formmated_search_string = ' '.join(search_string_array)
    youtube_url = get_youtube_video(formmated_search_string)

    player = await YTDLSource.from_url(youtube_url, stream=True)
    connection.play(player)
    return

def get_youtube_video(search):
    # Format the search term
    query_string = urllib.parse.urlencode({"search_query": search})
    # Format the search url on youtube
    format_url = urllib.request.urlopen("https://www.youtube.com/results?" + query_string)
    # Find all the video results
    search_results = re.findall(r"watch\?v=(\S{11})", format_url.read().decode())
    # Get the first result
    clip = "https://www.youtube.com/watch?v=" + "{}".format(search_results[0])
    return clip