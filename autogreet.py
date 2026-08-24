"""
autogreet.py — Bienvenida simple en texto plano, con variables.
Es un modo alternativo y más simple al sistema de embeds de welcome.py
(no lo reemplaza, ambos pueden usarse a la vez).

Comandos:
  ,autogreet <#canal>  — activa AutoGreet en ese canal
  ,autogreet off       — desactiva AutoGreet
  ,automsg <mensaje>   — configura el mensaje (con variables)

Variables disponibles: {user} {username} {server} {membercount}
"""

import discord
from discord.ext import commands
from config import db
import logging
from webhook_utils import send_via_webhook

log = logging.getLogger("antinuke.autogreet")

DEFAULT_MESSAGE = "¡Bienvenido {user} a **{server}**! Ahora somos **{membercount}** miembros."


def _get_autogreet(guild_id: int) -> dict:
    config = db.get_guild(guild_id)
    return config.setdefault("autogreet", {"enabled": False, "channel_id": None, "message": DEFAULT_MESSAGE})


def _save_autogreet(guild_id: int, data: dict):
    config = db.get_guild(guild_id)
    config["autogreet"] = data
    db.update_guild(guild_id, config)


def _format_message(template: str, member: discord.Member) -> str:
    return (
        template
        .replace("{user}", member.mention)
        .replace("{username}", member.name)
        .replace("{server}", member.guild.name)
        .replace("{membercount}", str(member.guild.member_count))
    )


class AutoGreet(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return

        data = _get_autogreet(member.guild.id)
        if not data.get("enabled") or not data.get("channel_id"):
            return

        channel = member.guild.get_channel(int(data["channel_id"]))
        if not channel:
            return

        text = _format_message(data.get("message", DEFAULT_MESSAGE), member)
        try:
            await send_via_webhook(channel, content=text)
        except discord.Forbidden:
            log.warning(f"[{member.guild.name}] Sin permisos para mandar autogreet en {channel.name}")
        except Exception as e:
            log.error(f"[{member.guild.name}] Error en autogreet: {e}")

    @commands.command(name="autogreet")
    @commands.has_permissions(manage_guild=True)
    async def autogreet(self, ctx: commands.Context, *, target: str = None):
        data = _get_autogreet(ctx.guild.id)

        if target is None:
            status = "Activado" if data.get("enabled") else "Desactivado"
            ch = ctx.guild.get_channel(int(data["channel_id"])) if data.get("channel_id") else None
            e = discord.Embed(
                description=f"**Status:** {status}\n"
                            f"**Canal:** {ch.mention if ch else 'Sin configurar'}\n"
                            f"**Mensaje:** {data.get('message', DEFAULT_MESSAGE)}\n\n"
                            f"Usa `,autogreet #canal` para activar, `,autogreet off` para desactivar, "
                            f"`,automsg <mensaje>` para cambiar el texto.",
                color=0x2b2d31,
            )
            return await ctx.send(embed=e)

        if target.strip().lower() == "off":
            data["enabled"] = False
            _save_autogreet(ctx.guild.id, data)
            return await ctx.send(embed=discord.Embed(description="AutoGreet desactivado.", color=0xed4245))

        try:
            channel = await commands.TextChannelConverter().convert(ctx, target.strip())
        except commands.BadArgument:
            return await ctx.send(embed=discord.Embed(
                description="No encontré ese canal. Usa `,autogreet #canal` o `,autogreet off`.",
                color=0xed4245,
            ))

        data["enabled"] = True
        data["channel_id"] = channel.id
        _save_autogreet(ctx.guild.id, data)
        await ctx.send(embed=discord.Embed(
            description=f"AutoGreet activado en {channel.mention}.",
            color=0x57f287,
        ))

    @commands.command(name="automsg")
    @commands.has_permissions(manage_guild=True)
    async def automsg(self, ctx: commands.Context, *, message: str):
        data = _get_autogreet(ctx.guild.id)
        data["message"] = message
        _save_autogreet(ctx.guild.id, data)
        preview = _format_message(message, ctx.author)
        await ctx.send(embed=discord.Embed(
            description=f"Mensaje actualizado. Así se ve:\n\n{preview}",
            color=0x57f287,
        ))


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoGreet(bot))
