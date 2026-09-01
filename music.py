"""
music.py — Bot de música con búsqueda por nombre/artista, cola, y buena calidad
de audio (estilo Jockie Music).

El audio se extrae de YouTube usando yt-dlp (no existe forma legítima de
transmitir audio directo desde Spotify vía API pública — Spotify solo permite
controlar SU PROPIA app oficial). Si el usuario pega un link de Spotify, se
lee el nombre de la canción/artista y se busca en YouTube automáticamente.

Requiere: yt-dlp, PyNaCl (voz) y el binario ffmpeg instalado en el sistema
(ver nixpacks.toml).

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

import asyncio
import functools
import logging
import os
import random
import re
from dataclasses import dataclass, field

import discord
from discord.ext import commands
import yt_dlp
import aiohttp

from voice import EMOJI_SUCCESS, EMOJI_ERROR

log = logging.getLogger("antinuke.music")

YTDL_OPTS = {
    "format": "bestaudio[ext=m4a]/bestaudio/best[acodec!=none]/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch1",
    "source_address": "0.0.0.0",
    "extract_flat": False,
    "skip_download": True,
    # YouTube bloquea muchas IPs de servidores/nube con un check anti-bot.
    # Pedirle a yt-dlp que finja ser el cliente de Android/iOS (en vez del
    # cliente web normal) suele evitar ese bloqueo, porque esos clientes no
    # piden la misma verificación.
    "extractor_args": {
        "youtube": {
            # YouTube está forzando el protocolo "SABR" en el cliente web, que
            # bloquea los links de descarga directa (yt-dlp issue #12482).
            # El cliente "tv" todavía entrega URLs usables sin pedir un token
            # extra (PO Token) — se prioriza. Los demás quedan de respaldo.
            "player_client": ["tv", "ios", "web_safari", "android"],
        }
    },
}

# Si YouTube sigue bloqueando incluso con el truco de arriba, hace falta pasar
# cookies de una sesión real de YouTube. En vez de subir un archivo a Railway,
# pega el CONTENIDO completo de tu cookies.txt en la variable de entorno
# YOUTUBE_COOKIES (Railway sí permite variables de varias líneas) — el bot lo
# escribe a un archivo local él solo al arrancar. Si no configuras la
# variable, esto simplemente no se usa.
_cookies_content = os.getenv("YOUTUBE_COOKIES")
if _cookies_content:
    _cookies_path = "/tmp/youtube_cookies.txt"
    with open(_cookies_path, "w", encoding="utf-8") as _f:
        _f.write(_cookies_content)
    YTDL_OPTS["cookiefile"] = _cookies_path

FFMPEG_BEFORE_OPTS = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
FFMPEG_OPTS = "-vn"

IDLE_DISCONNECT_SECONDS = 180  # 3 minutos sin nada en cola -> el bot se va solo

SPOTIFY_URL_RE = re.compile(r"open\.spotify\.com/track/[A-Za-z0-9]+")
YTDL = yt_dlp.YoutubeDL(YTDL_OPTS)


def _format_duration(seconds: int | None) -> str:
    if not seconds:
        return "En vivo / desconocida"
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _success_embed(text: str) -> discord.Embed:
    return discord.Embed(description=f"{EMOJI_SUCCESS} {text}", color=0x57f287)


def _error_embed(text: str) -> discord.Embed:
    return discord.Embed(description=f"{EMOJI_ERROR} {text}", color=0xed4245)


@dataclass
class Track:
    title: str
    artist: str
    webpage_url: str
    stream_url: str
    thumbnail: str | None
    duration: int | None
    requester: discord.Member


class GuildPlayer:
    def __init__(self, guild: discord.Guild, text_channel: discord.abc.Messageable):
        self.guild = guild
        self.text_channel = text_channel
        self.voice_client: discord.VoiceClient | None = None
        self.queue: list[Track] = []
        self.current: Track | None = None
        self.loop_mode: str = "off"  # "off" | "track" | "queue"
        self.volume: float = 1.0
        self.idle_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    def _cancel_idle_timer(self):
        if self.idle_task and not self.idle_task.done():
            self.idle_task.cancel()
        self.idle_task = None

    def _start_idle_timer(self, on_timeout):
        self._cancel_idle_timer()
        self.idle_task = asyncio.create_task(self._idle_watch(on_timeout))

    async def _idle_watch(self, on_timeout):
        try:
            await asyncio.sleep(IDLE_DISCONNECT_SECONDS)
            await on_timeout()
        except asyncio.CancelledError:
            pass

    def make_source(self, track: Track) -> discord.PCMVolumeTransformer:
        ffmpeg_audio = discord.FFmpegPCMAudio(
            track.stream_url,
            before_options=FFMPEG_BEFORE_OPTS,
            options=FFMPEG_OPTS,
        )
        return discord.PCMVolumeTransformer(ffmpeg_audio, volume=self.volume)


players: dict[int, GuildPlayer] = {}


def _get_player(guild: discord.Guild, text_channel) -> GuildPlayer:
    if guild.id not in players:
        players[guild.id] = GuildPlayer(guild, text_channel)
    else:
        players[guild.id].text_channel = text_channel
    return players[guild.id]


async def _resolve_spotify_title(url: str) -> str | None:
    """Usa el endpoint público oEmbed de Spotify (sin autenticación) para sacar
    el título real de la canción a partir de un link, y así buscarla en YouTube
    con un texto mucho más preciso que el link crudo."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://open.spotify.com/oembed",
                params={"url": url},
                timeout=aiohttp.ClientTimeout(total=8),
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                return data.get("title")
    except Exception:
        return None


async def _extract_track(query: str, requester: discord.Member) -> Track:
    loop = asyncio.get_event_loop()

    if SPOTIFY_URL_RE.search(query):
        resolved_title = await _resolve_spotify_title(query)
        if resolved_title:
            query = resolved_title

    partial = functools.partial(YTDL.extract_info, query, download=False)
    info = await loop.run_in_executor(None, partial)

    if info is None:
        raise ValueError("No encontré resultados para esa búsqueda.")

    if "entries" in info:
        entries = [e for e in info["entries"] if e]
        if not entries:
            raise ValueError("No encontré resultados para esa búsqueda.")
        info = entries[0]

    stream_url = info.get("url")
    if not stream_url:
        # Algunos formatos anidan la URL de audio en 'formats'
        formats = info.get("formats") or []
        audio_formats = [f for f in formats if f.get("acodec") != "none"]
        if audio_formats:
            stream_url = audio_formats[-1]["url"]
    if not stream_url:
        raise ValueError("No pude obtener el audio de ese resultado.")

    return Track(
        title=info.get("title", "Desconocido"),
        artist=info.get("uploader") or info.get("artist") or "Desconocido",
        webpage_url=info.get("webpage_url", query),
        stream_url=stream_url,
        thumbnail=info.get("thumbnail"),
        duration=info.get("duration"),
        requester=requester,
    )


def _track_embed(title: str, track: Track) -> discord.Embed:
    e = discord.Embed(
        description=f"[{track.title}]({track.webpage_url})",
        color=0x2b2d31,
    )
    e.set_author(name=title)
    if track.thumbnail:
        e.set_thumbnail(url=track.thumbnail)
    e.add_field(name="Artista", value=track.artist, inline=True)
    e.add_field(name="Duración", value=_format_duration(track.duration), inline=True)
    e.add_field(name="Pedido por", value=track.requester.mention, inline=True)
    return e


class Music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _ensure_voice(self, ctx: commands.Context) -> discord.VoiceClient | None:
        if ctx.author.voice is None or ctx.author.voice.channel is None:
            await ctx.send(embed=_error_embed("Debes estar en un canal de voz para usar esto."))
            return None

        player = _get_player(ctx.guild, ctx.channel)
        channel = ctx.author.voice.channel

        if player.voice_client is None or not player.voice_client.is_connected():
            try:
                player.voice_client = await channel.connect()
            except discord.ClientException as e:
                await ctx.send(embed=_error_embed(f"No pude conectarme al canal de voz: {e}"))
                return None
        elif player.voice_client.channel.id != channel.id:
            await player.voice_client.move_to(channel)

        return player.voice_client

    def _play_next(self, guild: discord.Guild):
        player = players.get(guild.id)
        if not player:
            return

        if player.loop_mode == "track" and player.current:
            next_track = player.current
        elif player.queue:
            if player.loop_mode == "queue" and player.current:
                player.queue.append(player.current)
            next_track = player.queue.pop(0)
        else:
            player.current = None
            coro = self._on_queue_empty(guild)
            asyncio.run_coroutine_threadsafe(coro, self.bot.loop)
            return

        player.current = next_track
        source = player.make_source(next_track)

        def _after(error):
            if error:
                log.error(f"Error de reproducción en {guild.name}: {error}")
            self._play_next(guild)

        if player.voice_client and player.voice_client.is_connected():
            player.voice_client.play(source, after=_after)
            coro = self._announce_now_playing(player, next_track)
            asyncio.run_coroutine_threadsafe(coro, self.bot.loop)

    async def _announce_now_playing(self, player: GuildPlayer, track: Track):
        try:
            await player.text_channel.send(embed=_track_embed("Reproduciendo ahora", track))
        except discord.HTTPException:
            pass

    async def _on_queue_empty(self, guild: discord.Guild):
        player = players.get(guild.id)
        if not player:
            return
        player._start_idle_timer(lambda: self._idle_disconnect(guild))

    async def _idle_disconnect(self, guild: discord.Guild):
        player = players.get(guild.id)
        if not player or player.current or player.queue:
            return
        if player.voice_client and player.voice_client.is_connected():
            await player.voice_client.disconnect()
        players.pop(guild.id, None)

    @commands.command(name="play", aliases=["p"])
    async def play(self, ctx: commands.Context, *, query: str):
        voice_client = await self._ensure_voice(ctx)
        if voice_client is None:
            return

        player = _get_player(ctx.guild, ctx.channel)
        player._cancel_idle_timer()

        msg = await ctx.send(embed=discord.Embed(description="Buscando...", color=0x2b2d31))
        try:
            track = await _extract_track(query, ctx.author)
        except Exception as e:
            return await msg.edit(embed=_error_embed(f"No pude encontrar esa canción: {e}"))

        async with player._lock:
            if player.current is None and not player.voice_client.is_playing():
                player.current = track
                source = player.make_source(track)

                def _after(error):
                    if error:
                        log.error(f"Error de reproducción en {ctx.guild.name}: {error}")
                    self._play_next(ctx.guild)

                player.voice_client.play(source, after=_after)
                await msg.edit(embed=_track_embed("Reproduciendo ahora", track))
            else:
                player.queue.append(track)
                await msg.edit(embed=_track_embed(f"Agregado a la cola (posición {len(player.queue)})", track))

    @commands.command(name="skip")
    async def skip(self, ctx: commands.Context):
        player = players.get(ctx.guild.id)
        if not player or not player.voice_client or not player.voice_client.is_playing():
            return await ctx.send(embed=_error_embed("No hay nada sonando ahora mismo."))
        player.loop_mode = "off" if player.loop_mode == "track" else player.loop_mode
        player.voice_client.stop()  # dispara el callback 'after' -> _play_next
        await ctx.send(embed=_success_embed("Canción saltada."))

    @commands.command(name="stop")
    async def stop(self, ctx: commands.Context):
        player = players.get(ctx.guild.id)
        if not player:
            return await ctx.send(embed=_error_embed("No estoy reproduciendo nada."))
        player.queue.clear()
        player.current = None
        player.loop_mode = "off"
        player._cancel_idle_timer()
        if player.voice_client and player.voice_client.is_connected():
            player.voice_client.stop()
            await player.voice_client.disconnect()
        players.pop(ctx.guild.id, None)
        await ctx.send(embed=_success_embed("Reproducción detenida y cola vaciada."))

    @commands.command(name="pause")
    async def pause(self, ctx: commands.Context):
        player = players.get(ctx.guild.id)
        if not player or not player.voice_client or not player.voice_client.is_playing():
            return await ctx.send(embed=_error_embed("No hay nada sonando ahora mismo."))
        player.voice_client.pause()
        await ctx.send(embed=_success_embed("Pausado."))

    @commands.command(name="resume")
    async def resume(self, ctx: commands.Context):
        player = players.get(ctx.guild.id)
        if not player or not player.voice_client or not player.voice_client.is_paused():
            return await ctx.send(embed=_error_embed("No hay nada pausado ahora mismo."))
        player.voice_client.resume()
        await ctx.send(embed=_success_embed("Reanudado."))

    @commands.command(name="leave", aliases=["disconnect"])
    async def leave(self, ctx: commands.Context):
        player = players.get(ctx.guild.id)
        if not player or not player.voice_client or not player.voice_client.is_connected():
            return await ctx.send(embed=_error_embed("No estoy en un canal de voz."))
        player.queue.clear()
        player._cancel_idle_timer()
        await player.voice_client.disconnect()
        players.pop(ctx.guild.id, None)
        await ctx.send(embed=_success_embed("Desconectado del canal de voz."))

    @commands.command(name="queue", aliases=["q"])
    async def queue_cmd(self, ctx: commands.Context):
        player = players.get(ctx.guild.id)
        if not player or (not player.current and not player.queue):
            return await ctx.send(embed=discord.Embed(description="La cola está vacía.", color=0x2b2d31))

        lines = []
        if player.current:
            lines.append(f"**Ahora:** [{player.current.title}]({player.current.webpage_url})")
        for i, t in enumerate(player.queue[:15], start=1):
            lines.append(f"`{i}.` [{t.title}]({t.webpage_url}) — {t.requester.mention}")
        extra = len(player.queue) - 15
        if extra > 0:
            lines.append(f"...y {extra} más.")

        await ctx.send(embed=discord.Embed(title="Cola de reproducción", description="\n".join(lines), color=0x2b2d31))

    @commands.command(name="nowplaying", aliases=["np"])
    async def nowplaying(self, ctx: commands.Context):
        player = players.get(ctx.guild.id)
        if not player or not player.current:
            return await ctx.send(embed=discord.Embed(description="No hay nada reproduciéndose.", color=0x2b2d31))
        await ctx.send(embed=_track_embed("Reproduciendo ahora", player.current))

    @commands.command(name="volume", aliases=["vol"])
    async def volume(self, ctx: commands.Context, level: int):
        player = players.get(ctx.guild.id)
        if not player or not player.voice_client:
            return await ctx.send(embed=_error_embed("No estoy en un canal de voz."))
        level = max(0, min(level, 200))
        player.volume = level / 100
        if player.voice_client.source and isinstance(player.voice_client.source, discord.PCMVolumeTransformer):
            player.voice_client.source.volume = player.volume
        await ctx.send(embed=_success_embed(f"Volumen ajustado a `{level}%`."))

    @commands.command(name="loop")
    async def loop_cmd(self, ctx: commands.Context, mode: str = None):
        player = players.get(ctx.guild.id)
        if not player:
            return await ctx.send(embed=_error_embed("No estoy reproduciendo nada."))
        mode = (mode or "").lower()
        if mode not in ("track", "queue", "off"):
            return await ctx.send(embed=_error_embed("Usa `,loop track`, `,loop queue`, o `,loop off`."))
        player.loop_mode = mode
        labels = {"track": "canción actual", "queue": "cola completa", "off": "desactivado"}
        await ctx.send(embed=_success_embed(f"Repetición: **{labels[mode]}**."))

    @commands.command(name="shuffle")
    async def shuffle(self, ctx: commands.Context):
        player = players.get(ctx.guild.id)
        if not player or not player.queue:
            return await ctx.send(embed=_error_embed("No hay suficientes canciones en la cola para mezclar."))
        random.shuffle(player.queue)
        await ctx.send(embed=_success_embed("Cola mezclada."))

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.id != self.bot.user.id:
            return
        if before.channel is not None and after.channel is None:
            # El bot fue desconectado del canal de voz (manual o kick) -> limpiar estado
            player = players.pop(member.guild.id, None)
            if player:
                player._cancel_idle_timer()


async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot))
