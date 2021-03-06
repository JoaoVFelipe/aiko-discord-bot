import discord

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