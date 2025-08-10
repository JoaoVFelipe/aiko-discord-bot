import discord, datetime as dt
from discord.ext import commands
from engine.json_store import upsert_birthday_user, remove_birthday_user, list_birthday_users, update_guild_cfg

from engine.events import birthdays

class Birthdays(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ----- comandos -----
    @commands.command(name="bdayadd")
    @commands.has_permissions(manage_guild=True)
    async def bday_add(self, ctx, ddmm: str):
        """Adiciona aniversário."""
        member = ctx.author
        try:
            d, m = map(int, ddmm.split("/"))
            assert 1 <= d <= 31 and 1 <= m <= 12
        except Exception:
            return await ctx.reply("Formato inválido. Use **dd/mm** (ex.: 10/08).")
        await upsert_birthday_user(str(ctx.guild.id), str(ctx.author.id), ddmm, name=member.display_name)
        await ctx.reply(f"✅ Adicionado: {member.mention} → {ddmm}")

    @commands.command(name="bdayremove")
    @commands.has_permissions(manage_guild=True)
    async def bday_remove(self, ctx, member: discord.Member):
        """Remove aniversário do membro especificado."""
        ok = await remove_birthday_user(str(ctx.guild.id), str(member.id))
        await ctx.reply("✅ Removido." if ok else "Nada para remover.")

    @commands.command(name="bdaylist")
    async def bday_list(self, ctx):
        """Lista os aniversários do servidor."""

        users = await list_birthday_users(str(ctx.guild.id))
        if not users:
            return await ctx.reply("Nenhum aniversário cadastrado neste servidor.")
        lines = [f"<@{uid}> — {info.get('ddmm')}" for uid, info in users.items()]
        await ctx.reply("**Aniversários deste servidor:**\n" + "\n".join(lines))

    @commands.command(name="bdaychannel")
    @commands.has_permissions(manage_guild=True)
    async def set_bday_channel(self, ctx: commands.Context, channel: discord.TextChannel | None):
        """Define o canal onde os aniversários serão anunciados através do channel_id."""

        cid = channel.id if channel else None
        await update_guild_cfg(str(ctx.guild.id), birthday_channel_id=str(cid) if cid else None)
        await ctx.reply(f"Canal de aniversários definido para: {channel.mention if channel else 'padrão do servidor'} ✅")

    @commands.command(name="bdaytime")
    @commands.has_permissions(manage_guild=True)
    async def set_bday_time(self, ctx: commands.Context, time_str: str):
        """Define o horário de anúncio no formato HH:MM (BRT)."""
        try:
            hour, minute = map(int, time_str.split(":"))
        except ValueError:
            return await ctx.reply("Formato inválido. Use **HH:MM** (ex.: 09:30).")

        if not (0 <= hour <= 23):
            return await ctx.reply("Informe uma **hora** entre 0 e 23.")
        if not (0 <= minute <= 59):
            return await ctx.reply("Informe os **minutos** entre 0 e 59.")

        await update_guild_cfg(
            str(ctx.guild.id),
            birthday_hour=hour,
            birthday_minute=minute
        )
        await ctx.reply(
            f"Hora de anúncio (BRT) definida: **{hour:02d}:{minute:02d}** ✅"
        )

    @commands.command(name="bdaystoday")
    async def birthdays_today(self, ctx: commands.Context):
        await birthdays.announce_for_guild(ctx.guild, True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Birthdays(bot))