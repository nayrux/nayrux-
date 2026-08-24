"""
autorole.py — Asigna roles automáticamente cuando alguien entra al servidor.

Comandos:
  ,autorole setup <rol>     — activa el sistema y agrega el primer rol (humanos)
  ,autorole toggle          — activa/desactiva sin borrar la configuración
  ,autorole add <rol>       — agrega un rol para humanos
  ,autorole remove <rol>    — quita un rol de humanos
  ,autorole addbot <rol>    — agrega un rol para bots
  ,autorole removebot <rol> — quita un rol de bots
  ,autorole list            — lista los roles configurados
  ,autorole clear           — vacía los roles (mantiene el estado on/off)
  ,autorole info            — muestra el estado actual
  ,autorole reset           — restablece todo (desactiva y vacía)
"""

import discord
from discord.ext import commands
from config import db
import logging

log = logging.getLogger("antinuke.autorole")


def _get_autorole(guild_id: int) -> dict:
    config = db.get_guild(guild_id)
    return config.setdefault("autorole", {"enabled": False, "human_roles": [], "bot_roles": []})


def _save_autorole(guild_id: int, data: dict):
    config = db.get_guild(guild_id)
    config["autorole"] = data
    db.update_guild(guild_id, config)


class AutoRole(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        data = _get_autorole(member.guild.id)
        if not data.get("enabled"):
            return

        role_ids = data.get("bot_roles", []) if member.bot else data.get("human_roles", [])
        if not role_ids:
            return

        roles = [member.guild.get_role(int(rid)) for rid in role_ids]
        roles = [r for r in roles if r is not None and r < member.guild.me.top_role]
        if not roles:
            return

        try:
            await member.add_roles(*roles, reason="AutoRole")
        except discord.Forbidden:
            log.warning(f"[{member.guild.name}] Sin permisos para asignar autorole a {member}")
        except Exception as e:
            log.error(f"[{member.guild.name}] Error en autorole: {e}")

    @commands.group(name="autorole", aliases=["ar"], invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def autorole(self, ctx: commands.Context):
        await ctx.send(embed=discord.Embed(
            description="Usa `,autorole setup <rol>`, `,autorole add/remove <rol>`, "
                        "`,autorole addbot/removebot <rol>`, `,autorole list`, `,autorole info`, "
                        "`,autorole toggle`, `,autorole clear`, `,autorole reset`.",
            color=0x2b2d31,
        ))

    @autorole.command(name="setup")
    @commands.has_permissions(manage_guild=True)
    async def autorole_setup(self, ctx: commands.Context, role: discord.Role):
        if role >= ctx.guild.me.top_role:
            return await ctx.send(embed=discord.Embed(
                description="Ese rol está por encima (o igual) del rol del bot. Muévelo más abajo.",
                color=0xed4245,
            ))
        data = _get_autorole(ctx.guild.id)
        data["enabled"] = True
        if role.id not in data["human_roles"]:
            data["human_roles"].append(role.id)
        _save_autorole(ctx.guild.id, data)
        await ctx.send(embed=discord.Embed(
            description=f"AutoRole activado. {role.mention} se asignará a los nuevos miembros.",
            color=0x57f287,
        ))

    @autorole.command(name="toggle")
    @commands.has_permissions(manage_guild=True)
    async def autorole_toggle(self, ctx: commands.Context):
        data = _get_autorole(ctx.guild.id)
        data["enabled"] = not data.get("enabled", False)
        _save_autorole(ctx.guild.id, data)
        word = "activado" if data["enabled"] else "desactivado"
        await ctx.send(embed=discord.Embed(description=f"AutoRole **{word}**.", color=0x2b2d31))

    @autorole.command(name="add")
    @commands.has_permissions(manage_guild=True)
    async def autorole_add(self, ctx: commands.Context, role: discord.Role):
        if role >= ctx.guild.me.top_role:
            return await ctx.send(embed=discord.Embed(
                description="Ese rol está por encima (o igual) del rol del bot. Muévelo más abajo.",
                color=0xed4245,
            ))
        data = _get_autorole(ctx.guild.id)
        if role.id in data["human_roles"]:
            return await ctx.send(embed=discord.Embed(description="Ese rol ya está en la lista.", color=0xed4245))
        data["human_roles"].append(role.id)
        _save_autorole(ctx.guild.id, data)
        await ctx.send(embed=discord.Embed(description=f"{role.mention} agregado a AutoRole.", color=0x57f287))

    @autorole.command(name="remove")
    @commands.has_permissions(manage_guild=True)
    async def autorole_remove(self, ctx: commands.Context, role: discord.Role):
        data = _get_autorole(ctx.guild.id)
        if role.id not in data["human_roles"]:
            return await ctx.send(embed=discord.Embed(description="Ese rol no estaba en la lista.", color=0xed4245))
        data["human_roles"].remove(role.id)
        _save_autorole(ctx.guild.id, data)
        await ctx.send(embed=discord.Embed(description=f"{role.mention} quitado de AutoRole.", color=0xed4245))

    @autorole.command(name="addbot")
    @commands.has_permissions(manage_guild=True)
    async def autorole_addbot(self, ctx: commands.Context, role: discord.Role):
        if role >= ctx.guild.me.top_role:
            return await ctx.send(embed=discord.Embed(
                description="Ese rol está por encima (o igual) del rol del bot. Muévelo más abajo.",
                color=0xed4245,
            ))
        data = _get_autorole(ctx.guild.id)
        if role.id in data["bot_roles"]:
            return await ctx.send(embed=discord.Embed(description="Ese rol ya está en la lista de bots.", color=0xed4245))
        data["bot_roles"].append(role.id)
        _save_autorole(ctx.guild.id, data)
        await ctx.send(embed=discord.Embed(description=f"{role.mention} agregado a AutoRole (bots).", color=0x57f287))

    @autorole.command(name="removebot")
    @commands.has_permissions(manage_guild=True)
    async def autorole_removebot(self, ctx: commands.Context, role: discord.Role):
        data = _get_autorole(ctx.guild.id)
        if role.id not in data["bot_roles"]:
            return await ctx.send(embed=discord.Embed(description="Ese rol no estaba en la lista de bots.", color=0xed4245))
        data["bot_roles"].remove(role.id)
        _save_autorole(ctx.guild.id, data)
        await ctx.send(embed=discord.Embed(description=f"{role.mention} quitado de AutoRole (bots).", color=0xed4245))

    @autorole.command(name="list")
    @commands.has_permissions(manage_guild=True)
    async def autorole_list(self, ctx: commands.Context):
        data = _get_autorole(ctx.guild.id)
        human = [ctx.guild.get_role(r) for r in data["human_roles"]]
        bots = [ctx.guild.get_role(r) for r in data["bot_roles"]]
        human_text = ", ".join(r.mention for r in human if r) or "Ninguno"
        bots_text = ", ".join(r.mention for r in bots if r) or "Ninguno"
        e = discord.Embed(title="AutoRole", color=0x2b2d31)
        e.add_field(name="Humanos", value=human_text, inline=False)
        e.add_field(name="Bots", value=bots_text, inline=False)
        await ctx.send(embed=e)

    @autorole.command(name="info")
    @commands.has_permissions(manage_guild=True)
    async def autorole_info(self, ctx: commands.Context):
        data = _get_autorole(ctx.guild.id)
        status = "Activado" if data.get("enabled") else "Desactivado"
        e = discord.Embed(
            description=f"**Status:** {status}\n"
                        f"**Roles para humanos:** {len(data['human_roles'])}\n"
                        f"**Roles para bots:** {len(data['bot_roles'])}",
            color=0x2b2d31,
        )
        await ctx.send(embed=e)

    @autorole.command(name="clear")
    @commands.has_permissions(manage_guild=True)
    async def autorole_clear(self, ctx: commands.Context):
        data = _get_autorole(ctx.guild.id)
        data["human_roles"] = []
        data["bot_roles"] = []
        _save_autorole(ctx.guild.id, data)
        await ctx.send(embed=discord.Embed(description="Roles de AutoRole vaciados.", color=0xed4245))

    @autorole.command(name="reset")
    @commands.has_permissions(manage_guild=True)
    async def autorole_reset(self, ctx: commands.Context):
        _save_autorole(ctx.guild.id, {"enabled": False, "human_roles": [], "bot_roles": []})
        await ctx.send(embed=discord.Embed(description="AutoRole restablecido por completo.", color=0xed4245))


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoRole(bot))
