import os
import discord

import yt_dlp as youtube_dl
from yt_dlp.utils import DownloadError

import asyncio
import validators
import re, urllib.parse, urllib.request

import imageio_ffmpeg as ffmpeg

from engine import discord_actions, music_player

# --------- Configurações globais ---------
queue = {}
queue_list_limit = 10

COOKIES_PATH = os.getenv('COOKIES_PATH')

# yt-dlp options
ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': 'downloads/%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': False,  # permite playlist (tratada no código)
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch',
    'source_address': '0.0.0.0',
    'cookiefile': COOKIES_PATH
}

# FFMPEG_PATH = os.path.join(os.path.dirname(__file__), '..', 'assets', 'ffmpeg', 'bin', 'ffmpeg.exe')
FFMPEG_PATH = ffmpeg.get_ffmpeg_exe()

ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -nostdin',
    'options': '-f s16le -ar 48000 -ac 2 -vn -loglevel panic'
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)


class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=True, serverQueue=None, message=None):
        try:
            data = await asyncio.to_thread(lambda: ytdl.extract_info(url, download=False))
        except DownloadError as e:
            error_msg = str(e).lower()
            # Verifica se é vídeo que exige login
            if "sign in to confirm" in error_msg or "private" in error_msg:
                await discord_actions.send_message(
                    channel=message.channel,
                    message_text="❌ Não consegui reproduzir essa música! Provavelmente é um link privado. Por favor, tente outro link!"
                )
                return False
            # Outros erros do YouTube
            await discord_actions.send_message(
                channel=message.channel,
                message_text="❌ Não consegui reproduzir essa música! Tive um erro inesperado, por favor informe o desenvolvedor!"
            )
            return False

        if not data:
            return False

        # Playlist → envia para função de gerenciamento
        if 'entries' in data and data.get('_type') == 'playlist':
            return await music_player.manage_playlist(
                playlist=data['entries'],
                message=message,
                serverQueue=serverQueue
            )

        # Stream direto
        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, executable=FFMPEG_PATH, **ffmpeg_options), data=data)


# --------- Comandos principais ----------
async def execute(message):
    serverQueue = queue.get(message.guild.id)

    if serverQueue and not serverQueue['playing'] and serverQueue['connection'].is_paused():
        await execute_resume(message)
        return await discord_actions.send_message(
            channel=message.channel,
            message_text="Música retomada!"
        )

    song_url = get_youtube_url(message)
    if not song_url:
        return await discord_actions.send_message(
            channel=message.channel,
            message_text="Não fui capaz de encontrar a faixa solicitada :("
        )

    if not serverQueue:
        # Cria nova fila
        queueContruct = {
            "text_channel": message.channel,
            "voice_channel": "",
            "connection": "",
            "songs": [],
            "playing": True
        }

        # Conecta ao canal de voz
        connection = await discord_actions.connect_voice_channel(message)
        if not connection or not connection.channel:
            return await discord_actions.send_message(
                message.channel,
                'Você precisa estar em um canal de voz para executar este comando!'
            )

        queueContruct['connection'] = connection
        queueContruct['voice_channel'] = connection.channel
        queue[message.guild.id] = queueContruct

        player = await play(message.guild, song_url, message)
        if player:
            return await discord_actions.send_message(
                channel=message.channel,
                message_text=f"Tocando agora: {player.title}"
            )
    else:
        # Já existe fila em execução
        player = await YTDLSource.from_url(song_url, stream=True, serverQueue=serverQueue, message=message)
        if player:
            serverQueue['songs'].append({'url': song_url, 'title': player.title})
            return await discord_actions.send_message(
                channel=message.channel,
                message_text=f'{player.title} foi adicionado à fila!',
                message_description=f'Total de músicas na fila: {len(serverQueue["songs"])}'
            )


async def execute_pause(message):
    if not message.author.voice.channel:
        return await discord_actions.send_message(
            channel=message.channel,
            message_text="Você precisa estar em um canal de voz para pausar a música!"
        )

    serverQueue = queue.get(message.guild.id)
    if not serverQueue:
        return await discord_actions.send_message(channel=message.channel, message_text="Não há músicas para pausar!")

    serverQueue['playing'] = False
    serverQueue['connection'].pause()


async def execute_resume(message):
    if not message.author.voice.channel:
        return await discord_actions.send_message(
            channel=message.channel,
            message_text="Você precisa estar em um canal de voz para retomar a música!"
        )

    serverQueue = queue.get(message.guild.id)
    if not serverQueue:
        return await discord_actions.send_message(
            channel=message.channel,
            message_text="Não há músicas para retomar!"
        )

    if serverQueue['connection'].is_paused():
        serverQueue['connection'].resume()
        serverQueue['playing'] = True
        return await discord_actions.send_message(
            channel=message.channel,
            message_text="Música retomada!"
        )


async def execute_skip(message):
    if not message.author.voice.channel:
        return await discord_actions.send_message(
            channel=message.channel,
            message_text="Você precisa estar em um canal de voz para pular alguma música!"
        )

    serverQueue = queue.get(message.guild.id)
    if not serverQueue:
        return await discord_actions.send_message(channel=message.channel, message_text="Não há músicas para pular!")

    serverQueue['connection'].stop()


async def execute_stop(message):
    if not message.author.voice.channel:
        return await discord_actions.send_message(
            channel=message.channel,
            message_text="Você precisa estar em um canal de voz para parar a música!"
        )

    serverQueue = queue.get(message.guild.id)
    if not serverQueue:
        return await discord_actions.send_message(channel=message.channel, message_text="Não há músicas para parar!")

    serverQueue['songs'] = []
    serverQueue['connection'].stop()
    await serverQueue['connection'].disconnect()
    queue.pop(message.guild.id, None)


async def execute_jump_to(message):
    if not message.author.voice.channel:
        return await discord_actions.send_message(channel=message.channel, message_text="Você precisa estar em um canal de voz para parar a música!")

    serverQueue = queue.get(message.guild.id)

    if not serverQueue:
        return await discord_actions.send_message(channel=message.channel, message_text="Não há uma lista em execução!")
        
    search_string_array = message.content.split(' ')
    search_string_array.pop(0)

    try:
        to_jump_position = int(search_string_array[0])
    except ValueError:
        # Handle the exception
        return await discord_actions.send_message(channel=message.channel, message_text="Insira um número referente a posição da música na fila!", message_description="Dica: digite !queue para ver a lista de músicas!")

    if to_jump_position:
        to_jump_position = to_jump_position - 1
        if len(serverQueue['songs']) >= to_jump_position:
            serverQueue['connection'].stop()
            serverQueue['songs'] = serverQueue['songs'][to_jump_position:]
            await play_next(serverQueue, message.guild, message)
        else:
            return await discord_actions.send_message(channel=message.channel, message_text="Insira um valor que exista na fila!", message_description="Dica: digite !queue para ver a lista de músicas!")
    return

async def execute_list_queue(message):
    serverQueue = queue.get(message.guild.id)

    if not message.author.voice.channel:
        return await discord_actions.send_message(channel=message.channel, message_text="Você precisa estar em um canal de voz para listar músicas!")

    if not serverQueue:
        return await discord_actions.send_message(channel=message.channel, message_text="Nenhuma fila de música iniciada!")

    else:
        song_list = serverQueue['songs']
        
        playing_now_text = 'Tocando agora: {}'.format(serverQueue['playing_now']['title'])

        if(len(song_list)):
            song_list_text = 'Próximas na fila: \n'
            index = 1
            for song in song_list:
                if queue_list_limit >= index:
                    song_list_text = song_list_text + '#{} - {}\n'.format(index, song['title'])
                    index = index + 1
                else:
                    song_list_text = song_list_text + 'E mais {} música(s)!'.format(len(song_list) - queue_list_limit)
                    break
        else:
            song_list_text = 'A fila de reprodução está vazia!'

        return await discord_actions.send_message(channel=message.channel, message_text=playing_now_text, message_description=song_list_text)


async def play(guild, song, message):
    serverQueue = queue.get(guild.id)
    if not song:
        await serverQueue['connection'].disconnect()
        queue.pop(guild.id)
        return
    if not serverQueue:
        return

    player = await YTDLSource.from_url(song, stream=True, serverQueue=serverQueue, message=message)
    if player:
        serverQueue['playing_now'] = {'url': song, 'title': player.title}
        queue[guild.id] = serverQueue
        serverQueue['connection'].play(
            player,
            after=lambda e: asyncio.run(play_next(serverQueue, guild, message))
        )
        return player
    return False


async def play_next(serverQueue, guild, message):
    if len(serverQueue['songs']):
        to_play = serverQueue['songs'].pop(0)
        await play(guild, to_play['url'], message)
    else:
        if serverQueue and serverQueue['connection']:
            serverQueue['connection'].stop()


async def check_is_playing(serverQueue):
    return serverQueue and serverQueue['connection'] and (
        serverQueue['connection'].is_playing() or serverQueue['connection'].is_paused()
    )


async def manage_playlist(playlist, message, serverQueue):
    total_queue = 0
    for item in playlist:
        serverQueue['songs'].append({'url': item['url'], 'title': item['title']})
        total_queue += 1

    await discord_actions.send_message(
        channel=message.channel,
        message_text=f'{total_queue} músicas adicionadas à fila!',
        message_description=f'Total de músicas na fila: {len(serverQueue["songs"])}'
    )
    if not await check_is_playing(serverQueue):
        return await music_player.play_next(serverQueue=serverQueue, message=message, guild=message.guild)


def get_youtube_url(message):
    search_string_array = message.content.split(' ')
    search_string_array.pop(0)
    search_string = ' '.join(search_string_array)

    if validators.url(search_string):
        return search_string

    query_string = urllib.parse.urlencode({"search_query": search_string.lower()})
    format_url = urllib.request.urlopen(f"https://www.youtube.com/results?{query_string}")
    search_results = re.findall(r"watch\?v=(\S{11})", format_url.read().decode())
    return f"https://www.youtube.com/watch?v={search_results[0]}" if search_results else False


async def check_inactivity_queues():
    print("Checking for inactivity...")
    try:
        for key, instance in list(queue.items()):
            if not await check_is_playing(instance):
                print(f"Inactivity found! Disconnecting Id: {key}")
                await discord_actions.send_message(
                    channel=instance['text_channel'],
                    message_text='Hey, alguém aí?',
                    message_description='Estou desconectando devido a inatividade. Qualquer coisa estou por aqui, só chamar ;)'
                )
                instance['connection'].stop()
                await instance['connection'].disconnect()
                queue.pop(key)
                print("Inactive instance disconnected!")
    except Exception as e:
        print("Erro ao tentar desconectar a instância do bot inativa.", e)
