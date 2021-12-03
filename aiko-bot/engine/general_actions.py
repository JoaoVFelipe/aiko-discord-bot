async def connect_voice_channel(message):
    member = message.author
    voice_channel = member.voice.channel

    if not voice_channel:
        await send_message(message, 'Você precisa estar em um canal de voz para executar este comando!')
        return False

    connection = await voice_channel.connect()
    return connection

async def send_message(messageEvent, messageText):
    return await messageEvent.channel.send(messageText)