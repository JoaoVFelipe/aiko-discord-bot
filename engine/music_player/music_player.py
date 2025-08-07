import discord
import asyncio
import validators
import re, urllib.parse, urllib.request

from engine import discord_actions
from engine.music_player.guild_queue import GuildQueue
from engine.music_player.ytdl_source import YTDLSource

queues = {}  # {guild_id: GuildQueue}
queue_list_limit = 10


async def execute(message):
    guild_id = message.guild.id
    server_queue = queues.get(guild_id)

    if server_queue and not server_queue.playing and server_queue.connection.is_paused():
        await execute_resume(message)
        return await discord_actions.send_message(message.channel, "Música retomada!")

    song_url = get_youtube_url(message)
    if not song_url:
        return await discord_actions.send_message(message.channel, "Não fui capaz de encontrar a faixa solicitada :(")

    if not server_queue:
        connection = await discord_actions.connect_voice_channel(message)
        if not connection:
            return await discord_actions.send_message(message.channel, "Você precisa estar em um canal de voz!")

        server_queue = GuildQueue(
            guild_id=guild_id,
            text_channel=message.channel,
            voice_channel=connection.channel,
            connection=connection
        )
        queues[guild_id] = server_queue

        await server_queue.play(bot=message.guild.me, song_url=song_url)
        return await discord_actions.send_message(message.channel, f"Tocando agora: {server_queue.playing_now['title']}")

    # Verifica metadados antes de baixar o áudio
    info = await YTDLSource.extract_info(song_url)
    if not info:
        return await discord_actions.send_message(
            channel=message.channel,
            message_text="Não foi possível obter informações sobre a faixa solicitada."
        )

    # Se for playlist, adiciona todas à fila
    if 'entries' in info and info.get('_type') == 'playlist':
        return await manage_playlist(
            playlist=info['entries'],
            message=message,
            server_queue=server_queue
        )

    # Se for música individual, cria o player
    player = await YTDLSource.from_url(song_url, stream=True, message=message)
    if not player:
        return

    server_queue.add_song({'url': song_url, 'title': player.title})

    await discord_actions.send_message(
        channel=message.channel,
        message_text=f"Música adicionada à fila: {player.title}"
    )

    # Se nada estiver tocando, inicia
    if not server_queue.is_playing():
        await server_queue.play(bot=message.guild.me, song_url=song_url)


async def execute_pause(message):
    server_queue = queues.get(message.guild.id)
    if not server_queue:
        return await discord_actions.send_message(message.channel, "Não há músicas para pausar!")
    server_queue.pause()


async def execute_resume(message):
    server_queue = queues.get(message.guild.id)
    if not server_queue:
        return await discord_actions.send_message(message.channel, "Não há músicas para retomar!")
    server_queue.resume()


async def execute_skip(message):
    server_queue = queues.get(message.guild.id)
    if not server_queue:
        return await discord_actions.send_message(message.channel, "Não há músicas para pular!")
    server_queue.skip()


async def execute_stop(message):
    server_queue = queues.get(message.guild.id)
    if not server_queue:
        return await discord_actions.send_message(message.channel, "Não há músicas para parar!")
    server_queue.clear()
    await server_queue.disconnect()
    queues.pop(message.guild.id, None)


async def execute_jump_to(message):
    server_queue = queues.get(message.guild.id)
    if not server_queue:
        return await discord_actions.send_message(message.channel, "Não há uma lista em execução!")

    args = message.content.split()
    if len(args) < 2:
        return await discord_actions.send_message(message.channel, "Informe a posição da música na fila!")

    try:
        to_jump_position = int(args[1]) - 1
    except ValueError:
        return await discord_actions.send_message(message.channel, "Insira uma posição válida!")

    if server_queue.jump_to(to_jump_position):
        return
    return await discord_actions.send_message(message.channel, "Insira uma posição válida!")


async def execute_list_queue(message):
    server_queue = queues.get(message.guild.id)
    if not server_queue:
        return await discord_actions.send_message(message.channel, "Nenhuma fila de música iniciada!")

    summary = server_queue.get_queue_summary(limit=queue_list_limit)
    playing_now = f"Tocando agora: {server_queue.playing_now['title']}" if server_queue.playing_now else "Nada tocando no momento."
    return await discord_actions.send_message(channel=message.channel, message_text=playing_now, message_description=summary)


async def manage_playlist(playlist, message, server_queue):
    count = 0
    for item in playlist:
        if 'url' in item and 'title' in item:
            server_queue.add_song({'url': item['url'], 'title': item['title']})
            count += 1

    await discord_actions.send_message(
        channel=message.channel,
        message_text=f'{count} músicas adicionadas à fila!',
        message_description=f'Total de músicas na fila: {len(server_queue.songs)}'
    )

    if not server_queue.is_playing():
        await server_queue.play(bot=message.guild.me, song_url=server_queue.songs[0]['url'])


def get_youtube_url(message):
    parts = message.content.split(' ')
    parts.pop(0)
    query = ' '.join(parts)

    if validators.url(query):
        return query

    encoded = urllib.parse.urlencode({"search_query": query.lower()})
    with urllib.request.urlopen(f"https://www.youtube.com/results?{encoded}") as response:
        results = re.findall(r"watch\?v=(\S{11})", response.read().decode())
    return f"https://www.youtube.com/watch?v={results[0]}" if results else False


async def check_inactivity_queues():
    print("Checking for inactivity...")
    for guild_id, instance in list(queues.items()):
        if not instance.is_playing():
            await discord_actions.send_message(
                channel=instance.text_channel,
                message_text='Hey, alguém aí?',
                message_description='Estou desconectando por inatividade. Qualquer coisa é só me chamar!'
            )
            instance.skip()
            await instance.disconnect()
            queues.pop(guild_id, None)
            print(f"Desconectado por inatividade: {guild_id}")
