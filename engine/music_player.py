import discord
import youtube_dl
import asyncio
import validators
import re, requests, subprocess, urllib.parse, urllib.request

from engine import discord_actions, music_player

# General variables
queue = {}
queue_list_limit = 10

# Code to play music from youtube 
ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': 'downloads/%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'extract_flat': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0'  # ipv6 addresses cause issues sometimes
}

ffmpeg_options = {
    'options': '-vn',
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5', 'options': '-vn'
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False, serverQueue=None, message=None):
        data = ytdl.extract_info(url, download=False)
        if not data: 
            return False
        else:
            if 'entries' in data:
                return await music_player.manage_playlist(playlist=data['entries'], message=message, serverQueue=serverQueue)
            else:
                filename = data['url']
                return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

async def execute(message):
    serverQueue = queue.get(message.guild.id)

    if not serverQueue:
        song_url = get_youtube_url(message)
        if not song_url:
            return await discord_actions.send_message(channel=message.channel, message_text="Não fui capaz de encontrar a faixa solicitada :(")

        queueContruct = {
            "text_channel": message.channel,
            "voice_channel": "",
            "connection": "",
            "songs": [],
            "playing": True 
        }

        # Connect to user voice channel
        connection = await discord_actions.connect_voice_channel(message)

        if not connection or not connection.channel:
            await discord_actions.send_message(message.channel, 'Você precisa estar em um canal de voz para executar este comando!')
            return False
        else:
            queueContruct['connection'] = connection
            queueContruct['voice_channel'] = connection.channel
            queue[message.guild.id] = queueContruct
            player = await play(message.guild, song_url, message)
            if player:
                return await discord_actions.send_message(channel=message.channel, message_text="Tocando agora: {}".format(player.title))
            else:
                return

    elif serverQueue['playing']:
        song_url = get_youtube_url(message)
        if not song_url:
            return await discord_actions.send_message(channel=message.channel, message_text="Não fui capaz de encontrar a faixa solicitada :(")
        if len(serverQueue['songs']) == 0 and not await check_is_playing(serverQueue):
            player = await play(message.guild, song_url, message)
            return await discord_actions.send_message(channel=message.channel, message_text="Tocando agora: {}".format(player.title))
        else: 
            player = await YTDLSource.from_url(song_url, stream=True, serverQueue=serverQueue, message=message)
            if player:
                serverQueue['songs'].append({'url': song_url, 'title': player.title})
                return await discord_actions.send_message(channel=message.channel, message_text='{} foi adicionado a fila!'.format(player.title), message_description='Total de músicas na fila: {}'.format(len(serverQueue['songs'])))
    else: 
        await execute_resume(message)

async def execute_pause(message): 
    if not message.author.voice.channel:
        return await discord_actions.send_message(channel=message.channel, message_text="Você precisa estar em um canal de voz para pausar a música!")

    serverQueue = queue.get(message.guild.id)

    if not serverQueue:
        return await discord_actions.send_message(channel=message.channel, message_text="Não há músicas para pausar!")

    serverQueue['playing'] = False
    serverQueue['connection'].pause()

async def execute_resume(message): 
    if not message.author.voice.channel:
        return await discord_actions.send_message(channel=message.channel, message_text="Você precisa estar em um canal de voz para retomar a música!")

    serverQueue = queue.get(message.guild.id)

    if not serverQueue:
        return await discord_actions.send_message(channel=message.channel, message_text="Não há músicas para retomar!")

    serverQueue['playing'] = True
    serverQueue['connection'].resume()

async def execute_skip(message): 
    if not message.author.voice.channel:
        return await discord_actions.send_message(channel=message.channel, message_text="Você precisa estar em um canal de voz para pular alguma música!")

    serverQueue = queue.get(message.guild.id)

    if not serverQueue:
        return await discord_actions.send_message(channel=message.channel, message_text="Não há músicas para pular!")

    if len(serverQueue['songs']):
        serverQueue['connection'].stop()
        # await play_next(serverQueue, message.guild, message)
    else:
        serverQueue['connection'].stop()

async def execute_stop(message):
    if not message.author.voice.channel:
        return await discord_actions.send_message(channel=message.channel, message_text="Você precisa estar em um canal de voz para parar a música!")

    serverQueue = queue.get(message.guild.id)

    if not serverQueue:
        return await discord_actions.send_message(channel=message.channel, message_text="Não há músicas para parar!")
        
    serverQueue['songs'] = []
    serverQueue['connection'].stop()
    await serverQueue['connection'].disconnect()
    queue.pop(message.guild.id)
    return

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

    if not isinstance(song, str):
        to_play = song['url']
        player = await YTDLSource.from_url(to_play, stream=True, serverQueue=serverQueue, message=message)
        serverQueue['playing_now'] = {'url':song['url'], 'title':song['title']}
        queue[guild.id] = serverQueue
    else:
        player = await YTDLSource.from_url(song, stream=True, serverQueue=serverQueue, message=message)
        if player:
            serverQueue['playing_now'] = {'url':song, 'title':player.title}
            queue[guild.id] = serverQueue
    if player:
        serverQueue['connection'].play(player, after= lambda e: asyncio.run(play_next(serverQueue, guild, message)))
        return player
    else:
        return False

async def play_next(serverQueue, guild, message):
    if len(serverQueue['songs']):
        to_play = serverQueue['songs'][0]
        await play(guild, to_play, message)
        serverQueue['songs'].pop(0)
    else:
        if serverQueue and serverQueue['connection']:
            serverQueue['connection'].stop()
        return

async def check_is_playing(serverQueue):
    if serverQueue and serverQueue['connection']:
        return serverQueue['connection'].is_playing() or serverQueue['connection'].is_paused()
    else:
        return False

async def manage_playlist(playlist, message, serverQueue):
    total_queue = 0
    for item in playlist:
        serverQueue['songs'].append({'url': item['url'], 'title': item['title']})
        total_queue = total_queue + 1

    await discord_actions.send_message(channel=message.channel, message_text='{} músicas adicionadas a fila!'.format(total_queue), message_description='Total de músicas na fila: {}'.format(len(serverQueue['songs'])))
    if not await check_is_playing(serverQueue):
        return await music_player.play_next(serverQueue=serverQueue, message=message, guild=message.guild)
    else:
        return

def get_youtube_url(message):
    # Remove command word
    search_string_array = message.content.split(' ')
    search_string_array.pop(0)
    search_string = ' '.join(search_string_array)

    if validators.url(search_string) is True:
        return search_string
    else:
        search_string = search_string.lower()
        # Format the search term
        query_string = urllib.parse.urlencode({"search_query": search_string})
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

async def check_inactivity_queues():
    print("Checking for inactivity...")
    try:
        for key, instance in list(queue.items()):
                serverQueue = queue.get(key)

                if not await check_is_playing(serverQueue):
                    print("Inactivity found! Disconnecting Id:", key)

                    await discord_actions.send_message(channel=instance['text_channel'], message_text='Hey, alguém aí?', message_description='Estou desconectando devido a inatividade. Qualquer coisa estou por aqui, só chamar ;)')
                    serverQueue['connection'].stop()
                    await serverQueue['connection'].disconnect()
                    queue.pop(key)
                    print("Inactive instance disconected!")
    except:
        print("Erro ao tentar desconectar a instância do bot inativa.")
