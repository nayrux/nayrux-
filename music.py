"""
music.py — Bot de música (estilo Jockie Music) usando Lavalink + wavelink.

A diferencia del intento anterior (yt-dlp + ffmpeg corriendo dentro del
propio bot), este usa Lavalink: un servidor de audio aparte, mantenido
activamente por su propia comunidad específicamente para pelear contra los
bloqueos de YouTube (SABR, verificación anti-bot, etc.) — es el enfoque que
usan los bots de música serios y actualizados en 2026, en vez de pelear esa
guerra nosotros mismos dentro del bot.

Requiere:
  - El servicio de Lavalink corriendo (ver /lavalink/application.yml y
    /lavalink/Dockerfile — se despliega como un servicio APARTE en Railway).
  - Variables de entorno: LAVALINK_HOST, LAVALINK_PORT, LAVALINK_PASSWORD.
  - PyNaCl (para la conexión de voz del bot).

Comandos:
  ,play <nombre o link>   — busca/agrega una canción a la cola y la reproduce
  ,skip                   — salta a la siguiente canción
  ,stop                   — detiene todo, vacía la cola y desconecta al bot
  ,pause / ,resume        — pausa o reanuda la canción actual
  ,queue                  — muestra la cola de reproducción
  ,nowplaying             — muestra qué se está reproduciendo ahora
  ,volume <0-200>         — ajusta el volumen
  ,leave                  — desconecta al bot del canal de voz
  ,loop [track|queue|off] — repite la canción actual, la cola entera, o apaga
  ,shuffle                — mezcla el orden de la cola
"""

import logging

import discord
from discord.ext import commands
import wavelink

from voice import EMOJI_SUCCESS, EMOJI_ERROR

log = logging.getLogger("antinuke.music")

IDLE_DISCONNECT_MS = 180_000  # 3 minutos sin nada en cola -> el bot se va solo


def _format_duration(ms: int | None) -> str:
    if not ms:
        return "En vivo / desconocida"
    seconds = int(ms / 1000)
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _success_embed(text: str) -> discord.Embed:
    return discord.Embed(description=f"{EMOJI_SUCCESS} {text}", color=0x57f287)


def _error_embed(text: str) -> discord.Embed:
    return discord.Embed(description=f"{EMOJI_ERROR} {text}", color=0xed4245)


def _track_embed(title: str, track: wavelink.Playable, requester: discord.Member | None = None) -> discord.Embed:
    e = discord.Embed(description=f"[{track.title}]({track.uri})", color=0x2b2d31)
    e.set_author(name=title)
    artwork = getattr(track, "artwork", None)
    if artwork:
        e.set_thumbnail(url=artwork)
    e.add_field(name="Artista", value=track.author or "Desconocido", inline=True)
    e.add_field(name="Duración", value=_format_duration(track.length), inline=True)
    if requester:
        e.add_field(name="Pedido por", value=requester.mention, inline=True)
    return e


class Music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _ensure_voice(self, ctx: commands.Context) -> wavelink.Player | None:
        if ctx.author.voice is None or ctx.author.voice.channel is None:
            await ctx.send(embed=_error_embed("Debes estar en un canal de voz para usar esto."))
            return None

        player: wavelink.Player = ctx.guild.voice_client
        channel = ctx.author.voice.channel

        if player is None:
            try:
                player = await channel.connect(cls=wavelink.Player)
            except Exception as e:
                await ctx.send(embed=_error_embed(f"No pude conectarme al canal de voz: {e}"))
                return None
            player.autoplay = wavelink.AutoPlayMode.partial
            player.inactive_timeout = IDLE_DISCONNECT_MS // 1000
        elif player.channel.id != channel.id:
            await player.move_to(channel)

        return player

    @commands.command(name="play", aliases=["p"])
    async def play(self, ctx: commands.Context, *, query: str):
        player = await self._ensure_voice(ctx)
        if player is None:
            return

        msg = await ctx.send(embed=discord.Embed(description="Buscando...", color=0x2b2d31))

        try:
            results = await wavelink.Playable.search(query)
        except Exception as e:
            return await msg.edit(embed=_error_embed(f"No pude encontrar esa canción: {e}"))

        if not results:
            return await msg.edit(embed=_error_embed("No encontré ninguna canción con eso."))

        track = results[0] if not isinstance(results, wavelink.Playlist) else results.tracks[0]
        track.extras = {"requester_id": ctx.author.id}

        if not player.playing and not player.paused and player.queue.is_empty:
            await player.play(track)
            await msg.edit(embed=_track_embed("Reproduciendo ahora", track, ctx.author))
        else:
            await player.queue.put_wait(track)
            position = player.queue.count
            await msg.edit(embed=_track_embed(f"Agregado a la cola (posición {position})", track, ctx.author))

    @commands.command(name="skip")
    async def skip(self, ctx: commands.Context):
        player: wavelink.Player = ctx.guild.voice_client
        if not player or not player.playing:
            return await ctx.send(embed=_error_embed("No hay nada sonando ahora mismo."))
        await player.skip(force=True)
        await ctx.send(embed=_success_embed("Canción saltada."))

    @commands.command(name="stop")
    async def stop(self, ctx: commands.Context):
        player: wavelink.Player = ctx.guild.voice_client
        if not player:
            return await ctx.send(embed=_error_embed("No estoy reproduciendo nada."))
        player.queue.clear()
        await player.stop()
        await player.disconnect()
        await ctx.send(embed=_success_embed("Reproducción detenida y cola vaciada."))

    @commands.command(name="pause")
    async def pause(self, ctx: commands.Context):
        player: wavelink.Player = ctx.guild.voice_client
        if not player or not player.playing:
            return await ctx.send(embed=_error_embed("No hay nada sonando ahora mismo."))
        await player.pause(True)
        await ctx.send(embed=_success_embed("Pausado."))

    @commands.command(name="resume")
    async def resume(self, ctx: commands.Context):
        player: wavelink.Player = ctx.guild.voice_client
        if not player or not player.paused:
            return await ctx.send(embed=_error_embed("No hay nada pausado ahora mismo."))
        await player.pause(False)
        await ctx.send(embed=_success_embed("Reanudado."))

    @commands.command(name="leave", aliases=["disconnect"])
    async def leave(self, ctx: commands.Context):
        player: wavelink.Player = ctx.guild.voice_client
        if not player:
            return await ctx.send(embed=_error_embed("No estoy en un canal de voz."))
        player.queue.clear()
        await player.disconnect()
        await ctx.send(embed=_success_embed("Desconectado del canal de voz."))

    @commands.command(name="queue", aliases=["q"])
    async def queue_cmd(self, ctx: commands.Context):
        player: wavelink.Player = ctx.guild.voice_client
        if not player or (not player.current and player.queue.is_empty):
            return await ctx.send(embed=discord.Embed(description="La cola está vacía.", color=0x2b2d31))

        lines = []
        if player.current:
            lines.append(f"**Ahora:** [{player.current.title}]({player.current.uri})")
        for i, t in enumerate(list(player.queue)[:15], start=1):
            lines.append(f"`{i}.` [{t.title}]({t.uri})")
        extra = player.queue.count - 15
        if extra > 0:
            lines.append(f"...y {extra} más.")

        await ctx.send(embed=discord.Embed(title="Cola de reproducción", description="\n".join(lines), color=0x2b2d31))

    @commands.command(name="nowplaying", aliases=["np"])
    async def nowplaying(self, ctx: commands.Context):
        player: wavelink.Player = ctx.guild.voice_client
        if not player or not player.current:
            return await ctx.send(embed=discord.Embed(description="No hay nada reproduciéndose.", color=0x2b2d31))
        await ctx.send(embed=_track_embed("Reproduciendo ahora", player.current))

    @commands.command(name="volume", aliases=["vol"])
    async def volume(self, ctx: commands.Context, level: int):
        player: wavelink.Player = ctx.guild.voice_client
        if not player:
            return await ctx.send(embed=_error_embed("No estoy en un canal de voz."))
        level = max(0, min(level, 200))
        await player.set_volume(level)
        await ctx.send(embed=_success_embed(f"Volumen ajustado a `{level}%`."))

    @commands.command(name="loop")
    async def loop_cmd(self, ctx: commands.Context, mode: str = None):
        player: wavelink.Player = ctx.guild.voice_client
        if not player:
            return await ctx.send(embed=_error_embed("No estoy reproduciendo nada."))
        mode = (mode or "").lower()
        mapping = {
            "track": wavelink.QueueMode.loop,
            "queue": wavelink.QueueMode.loop_all,
            "off": wavelink.QueueMode.normal,
        }
        if mode not in mapping:
            return await ctx.send(embed=_error_embed("Usa `,loop track`, `,loop queue`, o `,loop off`."))
        player.queue.mode = mapping[mode]
        labels = {"track": "canción actual", "queue": "cola completa", "off": "desactivado"}
        await ctx.send(embed=_success_embed(f"Repetición: **{labels[mode]}**."))

    @commands.command(name="shuffle")
    async def shuffle(self, ctx: commands.Context):
        player: wavelink.Player = ctx.guild.voice_client
        if not player or player.queue.is_empty:
            return await ctx.send(embed=_error_embed("No hay suficientes canciones en la cola para mezclar."))
        player.queue.shuffle()
        await ctx.send(embed=_success_embed("Cola mezclada."))

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload: wavelink.TrackEndEventPayload):
        player = payload.player
        if player is None or player.queue.is_empty:
            return
        next_track = await player.queue.get_wait()
        await player.play(next_track)

    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, payload: wavelink.NodeReadyEventPayload):
        log.info(f"Nodo de Lavalink conectado: {payload.node.identifier} (session {payload.session_id})")


async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot))
