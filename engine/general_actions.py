import discord

async def connect_voice_channel(message):
    member = message.author
    voice_channel = member.voice.channel

    if not voice_channel:
        await send_message(message, 'Você precisa estar em um canal de voz para executar este comando!')
        return False

    connection = await voice_channel.connect()
    return connection

async def send_message(messageEvent=None, messageText='** **', messageDescription='** **', messageTitle=''):
    if messageEvent:
        embed = discord.Embed(
            title=messageTitle,
            colour=discord.Colour.from_rgb(88, 52, 235)
        )
        embed.add_field(
            name=messageText,
            value=messageDescription,
            inline=False
        )
        return await messageEvent.channel.send(embed=embed)
    else: 
        return