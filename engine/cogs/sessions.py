# engine/cogs/sessions.py
from __future__ import annotations
import discord
from discord.ext import commands

from engine.storage.sessions_store import SessionsStore
from engine.events.sessions import notify_users_now

class Sessions(commands.Cog):
    """
    Comandos para sessões instantâneas (notificações agora).
    """
    def __init__(self, bot: commands.Bot, store: SessionsStore):
        self.bot = bot
        self.store = store

    # ---------- Comandos de Config da Guild ----------
    @commands.command(name="sessionchannel")
    @commands.has_permissions(manage_guild=True)
    async def set_session_channel(self, ctx: commands.Context, channel: discord.TextChannel | None):
        """
        Define o canal padrão para anúncios de sessão (ou limpa, passando 'None').
        """
        cid = channel.id if channel else None
        await self.store.update_guild_cfg(str(ctx.guild.id), session_channel_id=str(cid) if cid else None)
        await ctx.reply(
            f"Canal de sessões definido para: {channel.mention if channel else 'padrão do servidor'} ✅"
        )

    @commands.command(name="sessionmode")
    @commands.has_permissions(manage_guild=True)
    async def set_session_mode(self, ctx: commands.Context, mode: str):
        """
        Define o modo de notificação: dm | channel | both.
        """
        m = (mode or "").strip().lower()
        if m not in ("dm", "channel", "both"):
            return await ctx.reply("Modo inválido. Use: **dm**, **channel** ou **both**.")
        await self.store.update_guild_cfg(str(ctx.guild.id), session_mode=m)
        await ctx.reply(f"Modo de notificação definido: **{m}** ✅")

    # ---------- Comando principal: sessão instantânea ----------
    @commands.command(name="sessionnow")
    async def session_now(self, ctx: commands.Context, kind: str | None = None, *, extra: str | None = None):
        """
        Dispara uma sessão instantânea (agora) para usuários mencionados.
        Uso:
          !sessionnow [tipo] [mensagem livre] (mencione @pessoas)
        Exemplos:
          !sessionnow jogo Partida rápida? @fulano @ciclano
          !sessionnow filme Vamos ver "X"? @fulano
        Observações:
          - O modo de envio (dm/channel/both) segue a configuração da guild (veja !sessionmode).
          - Se ninguém for mencionado, o comando falha.
        """
        if not ctx.guild:
            return await ctx.reply("Este comando só pode ser usado em servidores.")
        mention_users = list(ctx.message.mentions or [])
        if not mention_users:
            return await ctx.reply("Mencione pelo menos uma pessoa para notificar. Ex.: `!sessionnow jogo Bora? @fulano`")

        # Opcional: permitir forçar o modo via sufixo (--dm, --channel, --both)
        force_mode = None
        if extra:
            lowered = extra.lower()
            if "--dm" in lowered:
                force_mode = "dm"
                extra = extra.replace("--dm", "").strip()
            elif "--channel" in lowered:
                force_mode = "channel"
                extra = extra.replace("--channel", "").strip()
            elif "--both" in lowered:
                force_mode = "both"
                extra = extra.replace("--both", "").strip()

        results = await notify_users_now(
            guild=ctx.guild,
            users=mention_users,
            kind=kind,
            extra_text=extra,
            store=self.store,
            inviter=ctx.author,
            force_mode=force_mode,
        )


        # Resumo amigável
        parts = []
        if results["dm_success"] or results["dm_fail"]:
            parts.append(f"DMs ✅ {results['dm_success']} / ❌ {results['dm_fail']}")
        if results["channel_success"] or results["channel_fail"]:
            parts.append(f"Canal ✅ {results['channel_success']} / ❌ {results['channel_fail']}")

        summary = " | ".join(parts) if parts else "Nenhuma saída enviada."
        await ctx.reply(f"Notificações enviadas. {summary}")

async def setup(bot: commands.Bot):
    store = SessionsStore()
    await bot.add_cog(Sessions(bot, store))
