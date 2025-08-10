# engine/cogs/music.py
import discord
from discord.ext import commands

# Reutiliza seu módulo atual
from engine.music_player import music_player

class Music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ========= Novo formato (prefix "!" sem "#") =========
    @commands.command(name="play", aliases=["p"])
    async def play_cmd(self, ctx: commands.Context, *, query: str):
        """Toca uma música: !play <url|termo>"""
        # se seu music_player.parse usa message.content, ele já deve funcionar
        await music_player.execute(ctx.message)

    @commands.command(name="resume")
    async def resume_cmd(self, ctx: commands.Context):
        await music_player.execute_resume(ctx.message)

    @commands.command(name="pause")
    async def pause_cmd(self, ctx: commands.Context):
        await music_player.execute_pause(ctx.message)

    @commands.command(name="next", aliases=["skip"])
    async def next_cmd(self, ctx: commands.Context):
        await music_player.execute_skip(ctx.message)

    @commands.command(name="stop")
    async def stop_cmd(self, ctx: commands.Context):
        await music_player.execute_stop(ctx.message)

    @commands.command(name="queue", aliases=["q"])
    async def queue_cmd(self, ctx: commands.Context):
        await music_player.execute_list_queue(ctx.message)

    @commands.command(name="jump_to", aliases=["jump"])
    async def jump_to_cmd(self, ctx: commands.Context, index: int):
        """Pula para posição na fila: !jump_to 3"""
        # mantém compat: seu método lê do message.content, então funciona
        await music_player.execute_jump_to(ctx.message)

async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot))
