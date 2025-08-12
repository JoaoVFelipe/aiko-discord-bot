import asyncio
from typing import Optional, Dict, List
from engine.music_player.ytdl_source import YTDLSource
from engine import discord_actions


class GuildQueue:
    def __init__(self, guild_id, text_channel, voice_channel, connection):
        self.guild_id = guild_id
        self.text_channel = text_channel
        self.voice_channel = voice_channel
        self.connection = connection

        self.songs: List[Dict[str, str]] = []
        self.playing_now: Optional[Dict[str, str]] = None
        self.playing: bool = False

        # Concurrency & lifecycle
        self._loop = asyncio.get_running_loop()
        self._lock = asyncio.Lock() 
        self._stopped_manually = False     
    # ---------- fila ----------
    def add_song(self, song: dict):
        self.songs.append(song)

    def add_playlist(self, playlist: list[dict]):
        self.songs.extend(playlist)

    def clear(self):
        # limpa fila e estado atual; não desconecta
        self.songs.clear()
        self.playing_now = None
        self.playing = False
        self._stopped_manually = True  # evita auto-avançar no after atual

    def jump_to(self, position: int):
        if 0 <= position < len(self.songs):
            # “corta” a fila até a posição e para a atual; after chamará play_next
            self.songs = self.songs[position:]
            self._stopped_manually = False
            if self.connection:
                self.connection.stop()
            return True
        return False

    def is_playing(self):
        # Tratar pausado como “ocupado”, para não iniciar outra trilha por engano
        return bool(self.connection) and (self.connection.is_playing() or self.connection.is_paused())

    def skip(self):
        if self.connection:
            self._stopped_manually = False 
            self.connection.stop() 

    def pause(self):
        if self.connection:
            self.connection.pause()
            self.playing = False

    def resume(self):
        if self.connection:
            self.connection.resume()
            self.playing = True

    async def disconnect(self):
        try:
            if self.connection:
                await self.connection.disconnect()
        finally:
            self.connection = None
            self.clear()

    def get_queue_summary(self, limit=10) -> str:
        if not self.songs:
            return "📭 Nenhuma música na fila por enquanto. Quer que eu toque algo pra animar?"
        lines = []
        for i, song in enumerate(self.songs[:limit], 1):
            lines.append(f"#{i} - {song['title']}")
        if len(self.songs) > limit:
            lines.append(f"➕ E tem mais {len(self.songs) - limit} músicas na fila esperando a vez!")
        return '\n'.join(lines)

    # ---------- reprodução ----------
    async def play_next(self, bot):
        """Consome a fila e toca o próximo item (único ponto que dá pop(0))."""
        async with self._lock:
            if self._stopped_manually:
                self._stopped_manually = False
                return

            if not self.songs:
                self.playing = False
                self.playing_now = None
                return

            entry = self.songs.pop(0)
            await self._play_entry(bot, entry)

    async def play_entry(self, bot, entry: Dict[str, str]):
        """Toca uma entrada específica (sem mexer na fila)."""
        async with self._lock:
            if self.songs and self.songs[0].get("url") == entry.get("url"):
                self.songs.pop(0)
            await self._play_entry(bot, entry)

    async def _play_entry(self, bot, entry: Dict[str, str]):
        """Prepara player e inicia reprodução."""
        if not self.connection:
            await discord_actions.send_message(
                channel=self.text_channel,
                message_text="⚠️ Não estou conectado ao canal de voz."
            )
            self.playing = False
            return

        player = await YTDLSource.from_url(entry["url"], stream=True, message=None)
        if not player:
            await discord_actions.send_message(
                channel=self.text_channel,
                message_text=f"❌ Não consegui reproduzir: {entry.get('title') or entry['url']}"
            )
            self.playing = False
            self.playing_now = None
            # Se falhou, tenta próxima (não trava a fila)
            self._loop.call_soon_threadsafe(asyncio.create_task, self.play_next(bot))
            return

        self.playing_now = {"url": entry["url"], "title": getattr(player, "title", entry.get("title", "Desconhecida"))}
        self.playing = True
        self._stopped_manually = False

        def after_playback(error):
            if error:
                print(f"[Erro de reprodução] {error}")
            self._loop.call_soon_threadsafe(asyncio.create_task, self._after_and_next(bot))

        try:
            self.connection.play(player, after=after_playback)
        except Exception as e:
            print(f"[Erro ao iniciar reprodução] {e}")
            self.playing = False
            self.playing_now = None
            self._loop.call_soon_threadsafe(asyncio.create_task, discord_actions.send_message(
                channel=self.text_channel,
                message_text=f"❌ Erro ao tentar tocar: {getattr(player, 'title', entry.get('title', entry['url']))}"
            ))
            self._loop.call_soon_threadsafe(asyncio.create_task, self.play_next(bot))

    async def _after_and_next(self, bot):
        """Chamado após terminar a faixa atual; decide se avança."""
        if self._stopped_manually:
            self._stopped_manually = False
            self.playing = False
            self.playing_now = None
            return
        await self.play_next(bot)
