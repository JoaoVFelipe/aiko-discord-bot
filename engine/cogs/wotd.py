from discord.ext import commands
import discord
from engine.events import wotd
from engine.storage.wotd_store import WOTDStore

class WordOfTheDay(commands.Cog):
    def __init__(self, bot: commands.Bot, store: WOTDStore):
        self.bot = bot
        self.store = store

    @commands.hybrid_command(name="wotd", description="Envia a palavra do dia agora (Dicionário Aberto)")
    async def palavra_do_dia(self, ctx: commands.Context):
        await wotd.post_wotd(ctx.channel)

    @commands.hybrid_command(name="rword", description="Envia uma palavra aleatória (Dicionário Aberto)")
    async def random_word(self, ctx: commands.Context):
        await wotd.post_random_word(ctx.channel)


    @commands.hybrid_group(name="wotdchannel", description="Configurar canais para Palavra do Dia", invoke_without_command=True)
    async def wotd_group(self, ctx: commands.Context):
        await ctx.reply("Subcomandos: `/wotdchannel add`, `/wotdchannel remove`, `/wotdchannel list`")

    @wotd_group.command(name="add", description="Registrar canal para receber a palavra do dia")
    @commands.has_guild_permissions(manage_guild=True)
    async def wotd_add(self, ctx: commands.Context, channel: discord.TextChannel | None = None):
        ch = channel or ctx.channel
        await self.store.add_channel(ctx.guild.id, ch.id)
        await ctx.reply(f"Canal registrado: {ch.mention}")

    @wotd_group.command(name="remove", description="Remover canal da lista")
    @commands.has_guild_permissions(manage_guild=True)
    async def wotd_remove(self, ctx: commands.Context, channel: discord.TextChannel | None = None):
        ch = channel or ctx.channel
        await self.store.remove_channel(ctx.guild.id, ch.id)
        await ctx.reply(f"Canal removido: {ch.mention}")

    @wotd_group.command(name="list", description="Listar canais configurados")
    @commands.has_guild_permissions(manage_guild=True)
    async def wotd_list(self, ctx: commands.Context):
        ids = await self.store.list_channels(ctx.guild.id)
        if not ids:
            await ctx.reply("Nenhum canal configurado ainda.")
            return
        mentions = []
        for cid in ids:
            ch = self.bot.get_channel(cid)
            mentions.append(ch.mention if isinstance(ch, discord.TextChannel) else f"<#{cid}>")
        await ctx.reply("Canais configurados para Palavra do Dia:\n" + "\n".join(f"• {m}" for m in mentions))

async def setup(bot: commands.Bot):
    store = WOTDStore()
    await bot.add_cog(WordOfTheDay(bot, store))
