import youtube_dl
import discord
import asyncio

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

async def play_music_from_youtube(voiceChannel):
    connection = await voiceChannel.connect()
    player = await YTDLSource.from_url('https://www.youtube.com/watch?v=dQw4w9WgXcQ', loop=False, stream=True)
    connection.play(player)
    return

def get_youtube_video(search):
    # Format the search term
    query_string = urllib.parse.urlencode({"search_query": search})
    # Format the search url on youtube
    formatUrl = urllib.request.urlopen("https://www.youtube.com/results?" + query_string)
    # Find all the video results
    search_results = re.findall(r"watch\?v=(\S{11})", formatUrl.read().decode())
    # Get the first result
    clip2 = "https://www.youtube.com/watch?v=" + "{}".format(search_results[0])