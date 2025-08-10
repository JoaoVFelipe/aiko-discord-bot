import discord
import asyncio

async def ensure_voice_connection(message, server_queue=None, attempts: int = 3):
    """
    Restabelece a conexão de voz de forma confiável mesmo após falhas (ex.: 4006).
    - Evita ficar preso em estado "zumbi"
    - Não depende de flags antigas (_connecting)
    - Faz conexão direta no channel alvo (sem wrappers), com retries controlados

    Retorna:
      - VoiceClient conectado, ou
      - None (se não foi possível conectar)
    """
    import asyncio
    import discord

    # ---- Descobre o canal de voz alvo do autor ----
    voice_state = getattr(message.author, "voice", None)
    target_channel = getattr(voice_state, "channel", None)
    if not target_channel:
        # Sem canal alvo: avisa e sai
        try:
            await send_message(
                channel=message.channel,
                message_text="📢 Ops! Parece que você não está em um canal de voz. Consegue entrar em um para eu começar?"
            )
        except:
            pass
        return None

    # ---- Lock por guild para evitar corridas entre múltiplos !play ----
    # guardado no próprio atributo da função para não depender de globais
    if not hasattr(ensure_voice_connection, "_locks"):
        ensure_voice_connection._locks = {}
    locks = ensure_voice_connection._locks
    lock = locks.setdefault(message.guild.id, asyncio.Lock())

    async with lock:
        # Sempre limpe flags antigas para não herdar estados de tentativas anteriores
        if server_queue is not None:
            setattr(server_queue, "_connecting", False)

        vc: discord.VoiceClient | None = message.guild.voice_client

        # Helper: verifica se a conexão está utilizável
        def is_stale(conn: discord.VoiceClient | None) -> bool:
            try:
                if conn is None:
                    return True
                if not conn.is_connected():
                    return True
                # Algumas falhas deixam ws None
                if getattr(conn, "ws", None) is None:
                    return True
                if getattr(conn, "channel", None) is None:
                    return True
            except Exception:
                return True
            return False

        # Se já conectado e saudável → move se necessário e retorna
        if not is_stale(vc):
            if vc.channel.id != target_channel.id:
                await vc.move_to(target_channel)
            if server_queue is not None:
                server_queue.connection = vc
            return vc

        # Se a conexão atual está zumbi, desconecta com força
        if vc is not None:
            try:
                await vc.disconnect(force=True)
            except Exception:
                pass
            vc = None
            if server_queue is not None:
                server_queue.connection = None
            await asyncio.sleep(0.75)

        # ---- Tenta conectar do zero, com algumas tentativas ----
        last_exc = None
        for i in range(max(1, attempts)):
            try:
                # Conexão direta sem wrapper para evitar herdar estados ruins
                vc = await target_channel.connect(reconnect=False, timeout=10)
                if vc and vc.is_connected():
                    if server_queue is not None:
                        server_queue.connection = vc
                    return vc
            except Exception as e:
                last_exc = e
                # Em casos de 4006/fechamento prematuro, dá um respiro maior
                msg = str(e)
                if "4006" in msg or isinstance(e, discord.errors.ConnectionClosed):
                    await asyncio.sleep(1.5)
                else:
                    await asyncio.sleep(0.9)

                # Tenta garantir que não ficou nada pendurado
                try:
                    tmp_vc = message.guild.voice_client
                    if tmp_vc is not None:
                        await tmp_vc.disconnect(force=True)
                except Exception:
                    pass
                if server_queue is not None:
                    server_queue.connection = None

        # Falhou após as tentativas: informa o usuário apenas aqui (uma vez)
        try:
            await send_message(
                channel=message.channel,
                message_text="⚠️ Tive um probleminha ao conectar no canal de voz. Pode tentar de novo em alguns segundos?"
            )
        except:
            pass
        return None


async def connect_voice_channel(message):
    member = message.author
    if not member.voice:
        return False

    voice_channel = member.voice.channel

    if not voice_channel:
        return False

    connection = await voice_channel.connect()
    return connection

async def disconnect_voice_channel(message):
    member = message.author
    if not member.voice:
        return False

    voice_channel = member.voice.channel

    if not voice_channel:
        return False

    connection = await voice_channel.disconnect()

async def send_message(channel=None, message_title='', message_fields=[], message_text='** **', message_description='** **'):
    if channel:
        embed = discord.Embed(
            title=message_title,
            colour=discord.Colour.from_rgb(88, 52, 235)
        )
        
        if len(message_fields) > 0:
            for message_field in message_fields:
                embed.add_field(
                    name=message_field['message_text'],
                    value=message_field['message_description'],
                    inline=message_field['inline'] or False
                )
        
        elif (message_text != '** **' or message_description != '** **'):
            embed.add_field(
                    name=message_text,
                    value=message_description,
                    inline=False
                )

        return await channel.send(embed=embed)
    else: 
        return