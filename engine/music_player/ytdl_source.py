import os
import yt_dlp
import discord
import asyncio
import imageio_ffmpeg as ffmpeg

FFMPEG_PATH = ffmpeg.get_ffmpeg_exe()
COOKIES_PATH = os.getenv('COOKIES_PATH')

ytdl_format_options = {
    'format': 'bestaudio/best',
    'noplaylist': False, 
    'extract_flat': False,
    'quiet': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch',
    'source_address': '0.0.0.0',
    'cookiefile': COOKIES_PATH
}

ffmpeg_options = {
    'options': '-vn'
}

ytdl = yt_dlp.YoutubeDL(ytdl_format_options)


class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False, message=None):
        loop = loop or asyncio.get_event_loop()

        try:
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
        except Exception as e:
            if message:
                await message.channel.send(f"Erro ao buscar a música: {str(e)}")
            return None

        if 'entries' in data:
            return data

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, executable=FFMPEG_PATH, **ffmpeg_options), data=data)
    
    @staticmethod
    async def extract_info(url):
        loop = asyncio.get_event_loop()
        try:
            return await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=False))
        except Exception as e:
            print(f"[Erro ao extrair info]: {e}")
            return None
