import asyncio
from engine.music_player.ytdl_source import YTDLSource
from engine import discord_actions


class GuildQueue:
    def __init__(self, guild_id, text_channel, voice_channel, connection):
        self.guild_id = guild_id
        self.text_channel = text_channel
        self.voice_channel = voice_channel
        self.connection = connection
        self.songs = []
        self.playing_now = None
        self.playing = False

    def add_song(self, song: dict):
        self.songs.append(song)

    def add_playlist(self, playlist: list[dict]):
        self.songs.extend(playlist)

    def clear(self):
        self.songs.clear()
        self.playing = False
        self.playing_now = None

    def jump_to(self, position: int):
        if 0 <= position < len(self.songs):
            self.songs = self.songs[position:]
            self.connection.stop()
            return True
        return False

    def is_playing(self):
        return self.connection and (
            self.connection.is_playing() or self.connection.is_paused()
        )

    def skip(self):
        if self.connection:
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
        if self.connection:
            await self.connection.disconnect()

    def get_queue_summary(self, limit=10) -> str:
        if not self.songs:
            return "📭 Nenhuma música na fila por enquanto. Quer que eu toque algo pra animar?"
        lines = []
        for i, song in enumerate(self.songs[:limit], 1):
            lines.append(f"#{i} - {song['title']}")
        if len(self.songs) > limit:
            lines.append(f"➕ E tem mais {len(self.songs) - limit} músicas na fila esperando a vez!")
        return '\n'.join(lines)

    async def play(self, bot, song_url: str):
        player = await YTDLSource.from_url(song_url, stream=True, message=None)

        if not player:
            await discord_actions.send_message(
                channel=self.text_channel,
                message_text=f"❌ Não consegui reproduzir esta faixa: {song_url}"
            )
            return

        self.playing_now = {'url': song_url, 'title': player.title}
        self.playing = True

        loop = asyncio.get_running_loop()

        def after_playback(error):
            if error:
                print(f"[Erro de reprodução] {error}")
            loop.call_soon_threadsafe(asyncio.create_task, self.play_next(bot))

        try:
            self.connection.play(player, after=after_playback)
        except Exception as e:
            print(f"[Erro ao iniciar reprodução] {e}")
            self.playing = False
            await discord_actions.send_message(
                channel=self.text_channel,
                message_text=f"❌ Erro ao tentar tocar: {player.title}"
            )

    async def play_next(self, bot):
        if self.songs:
            next_song = self.songs.pop(0)
            await self.play(bot, next_song['url'])
        else:
            self.playing = False
            if self.connection:
                self.connection.stop()
