# engine/events/sessions.py
from __future__ import annotations
import logging
import datetime as dt
from zoneinfo import ZoneInfo

import discord

from engine.storage.sessions_store import SessionsStore

log = logging.getLogger("aiko.sessions")
TZ = ZoneInfo("America/Sao_Paulo")

SESSION_TEMPLATES = {
    "jogo": "🎮 **Sessão de jogo agora!**",
    "filme": "🎬 **Sessão de filme agora!**",
    "churrasco": "🔥 **Churrasco rolando agora!**",
    "_generic": "📣 **Sessão agora!**",
}

def _now_brt() -> dt.datetime:
    return dt.datetime.now(TZ)

def _invite_line(inviter: discord.abc.User | discord.Member) -> tuple[str, str]:
    """
    Retorna duas versões da linha de convite:
      - invite_dm: versão para DM (usa display_name sem mention para ficar mais natural)
      - invite_channel: versão para canal (usa mention)
    Inclui canal de voz se o convidante estiver conectado.
    """
    # Nome/menção do convidante
    inviter_name = getattr(inviter, "display_name", None) or inviter.name
    inviter_mention = getattr(inviter, "mention", f"**{inviter_name}**")

    # Detecta canal de voz atual do convidante (voice/stage)
    voice_name = None
    try:
        if getattr(inviter, "voice", None) and inviter.voice and inviter.voice.channel:
            voice_name = inviter.voice.channel.name
    except Exception:
        pass

    if voice_name:
        invite_dm = f"👋 {inviter_name} está te convidando **no canal de voz {voice_name}**."
        invite_channel = f"👋 {inviter_mention} está convidando **no canal de voz {voice_name}**."
    else:
        invite_dm = f"👋 {inviter_name} está te convidando."
        invite_channel = f"👋 {inviter_mention} está convidando."

    return invite_dm, invite_channel

def _render_message(kind: str | None, extra_text: str | None, prefix: str) -> str:
    """
    Monta o corpo da mensagem usando o template do tipo + prefixo (linha do convite).
    """
    kind = (kind or "").strip().lower()
    header = SESSION_TEMPLATES.get(kind, SESSION_TEMPLATES["_generic"])
    extra = (extra_text or "").strip()
    parts = [header, prefix]
    if extra:
        parts.append(extra)
    return "\n".join(parts)

async def _send_dm(user: discord.abc.User | discord.Member, text: str) -> bool:
    try:
        await user.send(text)
        return True
    except discord.Forbidden:
        log.info(f"[sessions] Sem permissão para DM ao usuário {getattr(user, 'id', '?')}")
    except discord.HTTPException as e:
        log.exception(f"[sessions] Falha ao enviar DM para {getattr(user, 'id', '?')}: {e}")
    return False

async def _send_channel_message(channel: discord.abc.Messageable, text: str) -> bool:
    try:
        await channel.send(text)
        return True
    except discord.Forbidden:
        log.info("[sessions] Sem permissão para enviar mensagem no canal.")
    except discord.HTTPException as e:
        log.exception(f"[sessions] Falha ao enviar mensagem no canal: {e}")
    return False

async def _resolve_announce_channel(guild: discord.Guild, store: SessionsStore) -> discord.TextChannel | None:
    cfg = await store.get_guild_cfg(guild.id)
    channel_id = cfg.get("session_channel_id")
    channel = guild.get_channel(int(channel_id)) if channel_id else None

    if not channel:
        me = guild.me
        channel = guild.system_channel or next(
            (c for c in guild.text_channels if c.permissions_for(me).send_messages),
            None
        )
    return channel

def _normalize_mode(mode_str: str | None) -> str:
    m = (mode_str or "").strip().lower()
    if m in ("dm", "channel", "both"):
        return m
    return "both"

async def notify_users_now(
    guild: discord.Guild,
    users: list[discord.Member],
    kind: str | None,
    extra_text: str | None,
    store: SessionsStore,
    inviter: discord.Member | discord.User | None = None,
    force_mode: str | None = None,
) -> dict:
    """
    Envia notificação instantânea para a lista de usuários.
    - Sem persistência de sessão.
    - Inclui quem está convidando e, se houver, o canal de voz do convidante.
    - Respeita o modo configurado na guild (dm/channel/both), a menos que force_mode seja fornecido.
    - Retorna um dict com contagem de sucessos/erros.
    """
    cfg = await store.get_guild_cfg(guild.id)
    mode = _normalize_mode(force_mode or cfg.get("session_mode"))

    # Prefixos específicos para DM/canal (linha do convidante)
    invite_dm_prefix, invite_channel_prefix = _invite_line(inviter or guild.me)

    # Mensagens base
    dm_text = _render_message(kind, extra_text, prefix=invite_dm_prefix)
    channel_text_base = _render_message(kind, extra_text, prefix=invite_channel_prefix)

    # Monta menções (para a versão de canal)
    mentions = " ".join(u.mention for u in users) if users else ""
    channel_text = f"{mentions}\n{channel_text_base}" if mentions else channel_text_base

    channel = None
    if mode in ("channel", "both"):
        channel = await _resolve_announce_channel(guild, store)

    results = {
        "dm_success": 0,
        "dm_fail": 0,
        "channel_success": 0,
        "channel_fail": 0,
    }

    # 1) DMs
    if mode in ("dm", "both") and users:
        for u in users:
            ok = await _send_dm(u, dm_text)
            if ok:
                results["dm_success"] += 1
            else:
                results["dm_fail"] += 1

    # 2) Canal
    if mode in ("channel", "both") and channel:
        ok = await _send_channel_message(channel, channel_text)
        if ok:
            results["channel_success"] += 1
        else:
            results["channel_fail"] += 1

    # Hook para notificação externa (push/SMS) pode usar dm_text ou channel_text_base como payload

    return results
