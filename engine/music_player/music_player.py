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

    # Se existe fila, está parado e apenas pausado
    if server_queue and not server_queue.playing and server_queue.connection and server_queue.connection.is_paused():
        await execute_resume(message)
        return await discord_actions.send_message(message.channel, "🎶 Prontinho! A música voltou a tocar.")

    song_url = await get_youtube_url(message)
    if not song_url:
        return await discord_actions.send_message(
            message.channel,
            "😕 Hmm... Não consegui encontrar essa faixa. Será que você pode tentar com outro nome ou link?"
        )

    if not server_queue:
        connection = await discord_actions.ensure_voice_connection(message, None)
        if not connection:
            return

        server_queue = GuildQueue(
            guild_id=guild_id,
            text_channel=message.channel,
            voice_channel=connection.channel,
            connection=connection
        )
        queues[guild_id] = server_queue

        await server_queue.play_entry(
            bot=message.guild.me,
            entry={"url": song_url, "title": "Carregando..."}
        )

        return await discord_actions.send_message(
            message.channel,
            f"🎧 Tocando agora: *{server_queue.playing_now['title']}*. Espero que curta!"
        )
    
    connection = await discord_actions.ensure_voice_connection(message, server_queue)
    if not connection:
        return
    try:
        info = await asyncio.wait_for(YTDLSource.extract_info(song_url), timeout=20)
    except asyncio.TimeoutError:
        return await discord_actions.send_message(
            message.channel,
            "⌛ Demorou demais para buscar a faixa. Tenta novamente por favor?"
        )

    if not info:
        return await discord_actions.send_message(
            channel=message.channel,
            message_text="⚠️ Tive um probleminha ao buscar as informações dessa faixa. Pode tentar de novo pra mim?"
        )

    if 'entries' in info and info.get('_type') == 'playlist':
        return await manage_playlist(
            playlist=info['entries'],
            message=message,
            server_queue=server_queue
        )

    player = await YTDLSource.from_url(song_url, stream=True, message=message)
    if not player:
        return

    server_queue.add_song({'url': song_url, 'title': player.title})

    await discord_actions.send_message(
        channel=message.channel,
        message_text=f"➕ Adicionei *{player.title}* à fila."
    )

    if not server_queue.is_playing():
        await server_queue.play_next(bot=message.guild.me)


async def execute_pause(message):
    server_queue = queues.get(message.guild.id)
    if not server_queue:
        return await discord_actions.send_message(message.channel, "😶 Nenhuma música tocando no momento, então não tenho o que pausar...")
    server_queue.pause()


async def execute_resume(message):
    server_queue = queues.get(message.guild.id)
    if not server_queue:
        return await discord_actions.send_message(message.channel, "🎼 Hmm, não tem nada tocando agora... Quer escolher algo pra animar a call?")
    server_queue.resume()


async def execute_skip(message):
    server_queue = queues.get(message.guild.id)
    if not server_queue:
        return await discord_actions.send_message(message.channel, "🤔 Não tem nenhuma música tocando agora...")
    server_queue.skip()


async def execute_stop(message):
    server_queue = queues.get(message.guild.id)
    if not server_queue:
        return await discord_actions.send_message(
            message.channel,
            "🔇 Não encontrei nenhuma música tocando. Acho que já estamos em silêncio."
        )
    
    server_queue.clear()
    try:
        await server_queue.disconnect()
    finally:
        queues.pop(message.guild.id, None)

async def execute_jump_to(message):
    server_queue = queues.get(message.guild.id)
    if not server_queue:
        return await discord_actions.send_message(message.channel, "📭 Nenhuma música na fila por enquanto. Quer que eu toque algo pra animar?")

    args = message.content.split()
    if len(args) < 2:
        return await discord_actions.send_message(message.channel, "🔢 Me diga qual número da música você quer pular, por favor!")

    try:
        to_jump_position = int(args[1]) - 1
    except ValueError:
        return await discord_actions.send_message(message.channel, "❌ Hmm, acho que esse sua fila não tem esse número... Tenta outro pra mim?")

    if server_queue.jump_to(to_jump_position):
        return
    return await discord_actions.send_message(message.channel, "🧐 Essa posição parece não existir... Quer tentar outro número?")


async def execute_list_queue(message):
    server_queue = queues.get(message.guild.id)
    if not server_queue:
        return await discord_actions.send_message(message.channel, "😅 Ainda não temos nenhuma música tocando por aqui.")

    summary = server_queue.get_queue_summary(limit=queue_list_limit)
    playing_now = f"🎶 Agora estamos curtindo: {server_queue.playing_now['title']}" if server_queue.playing_now else "Nada tocando no momento."
    return await discord_actions.send_message(channel=message.channel, message_text=playing_now, message_description=summary)


async def manage_playlist(playlist, message, server_queue):
    count = 0
    for item in playlist:
        if 'url' in item and 'title' in item:
            server_queue.add_song({'url': item['url'], 'title': item['title']})
            count += 1

    await discord_actions.send_message(
        channel=message.channel,
        message_text=f'📚 Adicionei {count} musicas à fila pra você!',
        message_description=f'🎵 Agora temos {len(server_queue.songs)} músicas na fila!'
    )

    if not server_queue.is_playing():
        await server_queue.play_next(bot=message.guild.me)


async def get_youtube_url(message):
    """
    Versão assíncrona: usa aiohttp (não bloqueia o event loop).
    - Se o input já for URL válida, retorna direto.
    - Caso contrário, tenta buscar no YouTube. Se falhar, usa fallback `ytsearch1:<query>`.
    """
    import aiohttp

    parts = message.content.split(' ')
    parts.pop(0)
    query = ' '.join(parts).strip()

    if validators.url(query):
        return query

    if not query:
        return False

    # Tenta scraping leve (com timeout curto)
    params = {"search_query": query.lower()}
    url = f"https://www.youtube.com/results?{urllib.parse.urlencode(params)}"

    try:
        timeout = aiohttp.ClientTimeout(total=6)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers={"User-Agent": "Mozilla/5.0"}) as resp:
                if resp.status != 200:
                    # fallback direto para ytsearch1
                    return f"ytsearch1:{query}"
                text = await resp.text()
    except Exception:
        # Qualquer erro de rede -> fallback ytsearch
        return f"ytsearch1:{query}"

    results = re.findall(r"watch\?v=(\S{11})", text)
    if results:
        return f"https://www.youtube.com/watch?v={results[0]}"

    # Fallback confiável para o extractor do yt-dlp
    return f"ytsearch1:{query}"



async def check_inactivity_queues():
    print("Checking for inactivity...")
    for guild_id, instance in list(queues.items()):
        try:
            # Se não está tocando ou a conexão caiu, encerra
            not_playing = not instance.is_playing()
            disconnected = not getattr(instance.connection, "is_connected", lambda: False)()
            if not_playing or disconnected:
                try:
                    await discord_actions.send_message(
                        channel=instance.text_channel,
                        message_text='👋 Hey~ Tá todo mundo quieto...',
                        message_description='💤 Como não estão ouvindo mais nada, vou me desconectar por enquanto. Me chama se precisar! ✨'
                    )
                except:
                    pass
                # garante parada e desconexão
                try:
                    instance.skip()
                except:
                    pass
                try:
                    await instance.disconnect()
                except:
                    pass
                queues.pop(guild_id, None)
                print(f"Desconectado por inatividade: {guild_id}")
        except Exception as e:
            print(f"[inactivity] erro na guild {guild_id}: {e}")

