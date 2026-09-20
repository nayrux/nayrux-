"""
moderation.py — Comandos de moderación estándar (no relacionados al AntiNuke).

Comandos:
  ,kick <@usuario> [razón]
  ,ban <@usuario> [razón] [días_borrado]
  ,softban <@usuario> [razón]
  ,unban <id_usuario> [razón]
  ,timeout <@usuario> <duración> [razón]     — timeout nativo de Discord (alias: mute)
  ,untimeout <@usuario> [razón]              — (alias: unmute)
  ,warn <@usuario> [razón]
  ,warnings <@usuario>
  ,clearwarnings <@usuario>                  — (alias: clearwarns)
  ,unwarn <@usuario> <índice>                — (alias: delwarn)
  ,purge <cantidad 1-1000> [@usuario]
  ,lock [#canal]                             — (alias: lockchannel)
  ,unlock [#canal]                           — (alias: unlockchannel)
  ,hide [#canal]
  ,unhide [#canal]
  ,nuke [#canal]                             — clona y borra el canal (lo reinicia)
  ,slowmode <segundos> [#canal]
  ,nickname <@usuario> <apodo|reset>         — (alias: nick)
  ,role <@usuario> <@rol>                    — añade un rol
  ,role remove <@usuario> <@rol>
  ,role info <@rol>
  ,roleall <@rol>                            — añade el rol a todos los miembros
  ,unroleall <@rol>                          — quita el rol a todos los miembros
  ,modlogs <@usuario>
"""

import discord
from discord.ext import commands
from config import db
from logger import _resolve_log_channel
from webhook_utils import send_via_webhook
import re
import logging
from datetime import datetime, timezone, timedelta

log = logging.getLogger("antinuke.moderation")

DURATION_RE = re.compile(r"^(\d+)\s*([smhd])$", re.IGNORECASE)
DURATION_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}
MAX_TIMEOUT_DAYS = 28


async def _send_mod_log(guild: discord.Guild, *, title: str, target, moderator: discord.Member, reason: str, extra_fields=None, color: int = 0x2b2d31):
    """Embed de log dedicado a acciones de moderación manual — no depende del castigo configurado en el antinuke."""
    config = db.get_guild(guild.id)
    channel = _resolve_log_channel(guild, config, "mod")
    if not channel:
        return

    embed_cfg = config.get("log_embed", {})
    footer_text = embed_cfg.get("footer_text", "Protección AntiNuke")
    show_thumbnail = embed_cfg.get("thumbnail", True)

    embed = discord.Embed(title=title, color=color, timestamp=datetime.now(timezone.utc))
    embed.set_author(name=guild.name, icon_url=guild.icon.url if guild.icon else None)
    if target is not None:
        embed.add_field(name="Usuario", value=f"{getattr(target, 'mention', str(target))} `{target}` (`{target.id}`)", inline=False)
    if moderator is not None:
        embed.add_field(name="Moderador", value=f"{moderator.mention} `{moderator}` (`{moderator.id}`)", inline=False)
    embed.add_field(name="Razón", value=f"```{reason}```", inline=False)
    if extra_fields:
        for name, value, inline in extra_fields:
            embed.add_field(name=name, value=value, inline=inline)
    if show_thumbnail and guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    embed.set_footer(text=footer_text)

    try:
        await send_via_webhook(channel, embed=embed)
    except Exception as e:
        log.warning(f"No se pudo enviar el log de moderación en {guild.name}: {e}")


def _parse_duration(text: str) -> timedelta | None:
    """Acepta formatos como '10m', '2h', '1d', '30s'."""
    match = DURATION_RE.match(text.strip())
    if not match:
        return None
    amount, unit = match.groups()
    seconds = int(amount) * DURATION_UNITS[unit.lower()]
    return timedelta(seconds=seconds)


def _hierarchy_error(ctx: commands.Context, target: discord.Member) -> str | None:
    """Retorna un mensaje de error si no se puede moderar a `target`, o None si está permitido."""
    if target.id == ctx.author.id:
        return "No puedes aplicarte esto a ti mismo."
    if target.id == ctx.bot.user.id:
        return "No puedo aplicarme esto a mí mismo."
    if target.id == ctx.guild.owner_id:
        return "No puedo moderar al dueño del servidor."
    if ctx.author.id != ctx.guild.owner_id and target.top_role >= ctx.author.top_role:
        return "No puedes moderar a alguien con un rol igual o superior al tuyo."
    if target.top_role >= ctx.guild.me.top_role:
        return "Mi rol está por debajo (o igual) del rol de ese usuario, no puedo hacer nada."
    return None


def _add_mod_action(guild_id: int, user_id: int, action_type: str, moderator_id: int, reason: str):
    config = db.get_guild(guild_id)
    actions = config.get("mod_actions", {})
    key = str(user_id)
    actions.setdefault(key, []).append({
        "type": action_type,
        "reason": reason,
        "moderator_id": moderator_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    config["mod_actions"] = actions
    db.update_guild(guild_id, config)


class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── Kick / Ban / Softban / Unban ────────────────────────────────────────

    @commands.command(name="kick")
    @commands.has_permissions(kick_members=True)
    @commands.bot_has_permissions(kick_members=True)
    async def kick(self, ctx: commands.Context, member: discord.Member, *, reason: str = "Sin razón especificada"):
        error = _hierarchy_error(ctx, member)
        if error:
            return await ctx.send(embed=discord.Embed(description=error, color=0xed4245))

        try:
            await member.send(embed=discord.Embed(
                description=f"Fuiste expulsado de **{ctx.guild.name}**.\n**Razón:** {reason}",
                color=0xed4245,
            ))
        except (discord.Forbidden, discord.HTTPException):
            pass

        await member.kick(reason=f"{ctx.author} ({ctx.author.id}): {reason}")
        _add_mod_action(ctx.guild.id, member.id, "kick", ctx.author.id, reason)

        await ctx.send(embed=discord.Embed(
            description=f"{member.mention} fue expulsado.\n**Razón:** {reason}",
            color=0x57f287,
        ))
        await _send_mod_log(
            ctx.guild, title="Expulsión Manual", target=member, moderator=ctx.author,
            reason=reason, color=0xed4245,
        )

    @commands.command(name="ban")
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def ban(self, ctx: commands.Context, member: discord.Member, delete_days: int = 0, *, reason: str = "Sin razón especificada"):
        error = _hierarchy_error(ctx, member)
        if error:
            return await ctx.send(embed=discord.Embed(description=error, color=0xed4245))
        delete_days = max(0, min(delete_days, 7))

        try:
            await member.send(embed=discord.Embed(
                description=f"Fuiste baneado de **{ctx.guild.name}**.\n**Razón:** {reason}",
                color=0xed4245,
            ))
        except (discord.Forbidden, discord.HTTPException):
            pass

        await member.ban(reason=f"{ctx.author} ({ctx.author.id}): {reason}", delete_message_days=delete_days)
        _add_mod_action(ctx.guild.id, member.id, "ban", ctx.author.id, reason)

        await ctx.send(embed=discord.Embed(
            description=f"{member.mention} fue baneado.\n**Razón:** {reason}",
            color=0x57f287,
        ))
        await _send_mod_log(
            ctx.guild, title="Baneo Manual", target=member, moderator=ctx.author,
            reason=reason, color=0xed4245,
        )

    @commands.command(name="softban")
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def softban(self, ctx: commands.Context, member: discord.Member, *, reason: str = "Sin razón especificada"):
        """Banea y desbanea al instante — borra sus mensajes recientes sin expulsarlo permanentemente."""
        error = _hierarchy_error(ctx, member)
        if error:
            return await ctx.send(embed=discord.Embed(description=error, color=0xed4245))

        await member.ban(reason=f"Softban por {ctx.author} ({ctx.author.id}): {reason}", delete_message_days=1)
        await ctx.guild.unban(member, reason="Softban: reingreso permitido")
        _add_mod_action(ctx.guild.id, member.id, "softban", ctx.author.id, reason)

        await ctx.send(embed=discord.Embed(
            description=f"{member.mention} recibió un softban (mensajes borrados, puede volver a entrar).\n**Razón:** {reason}",
            color=0x57f287,
        ))
        await _send_mod_log(
            ctx.guild, title="Softban", target=member, moderator=ctx.author,
            reason=reason, color=0xed4245,
        )

    @commands.command(name="unban")
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def unban(self, ctx: commands.Context, user_id: int, *, reason: str = "Sin razón especificada"):
        try:
            ban_entry = await ctx.guild.fetch_ban(discord.Object(id=user_id))
        except discord.NotFound:
            return await ctx.send(embed=discord.Embed(description="Ese usuario no está baneado.", color=0xed4245))

        await ctx.guild.unban(ban_entry.user, reason=f"{ctx.author} ({ctx.author.id}): {reason}")
        _add_mod_action(ctx.guild.id, user_id, "unban", ctx.author.id, reason)

        await ctx.send(embed=discord.Embed(
            description=f"`{ban_entry.user}` fue desbaneado.\n**Razón:** {reason}",
            color=0x57f287,
        ))
        await _send_mod_log(
            ctx.guild, title="Desbaneo Manual", target=ban_entry.user, moderator=ctx.author,
            reason=reason, color=0x57f287,
        )

    # ── Mute / Unmute (timeout nativo) ───────────────────────────────────────

    @commands.command(name="timeout", aliases=["mute"])
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    async def timeout(self, ctx: commands.Context, member: discord.Member, duration: str, *, reason: str = "Sin razón especificada"):
        error = _hierarchy_error(ctx, member)
        if error:
            return await ctx.send(embed=discord.Embed(description=error, color=0xed4245))

        delta = _parse_duration(duration)
        if delta is None:
            return await ctx.send(embed=discord.Embed(
                description="Formato de duración inválido. Usa `10m`, `2h`, `1d`, etc.",
                color=0xed4245,
            ))
        if delta > timedelta(days=MAX_TIMEOUT_DAYS):
            delta = timedelta(days=MAX_TIMEOUT_DAYS)

        until = discord.utils.utcnow() + delta
        await member.timeout(until, reason=f"{ctx.author} ({ctx.author.id}): {reason}")
        _add_mod_action(ctx.guild.id, member.id, "mute", ctx.author.id, f"{reason} ({duration})")

        await ctx.send(embed=discord.Embed(
            description=f"{member.mention} fue silenciado por `{duration}`.\n**Razón:** {reason}",
            color=0x57f287,
        ))
        await _send_mod_log(
            ctx.guild, title="Silencio Manual", target=member, moderator=ctx.author,
            reason=reason, extra_fields=[("Duración", f"`{duration}`", True)], color=0xed4245,
        )

    @commands.command(name="untimeout", aliases=["unmute"])
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    async def untimeout(self, ctx: commands.Context, member: discord.Member, *, reason: str = "Sin razón especificada"):
        if member.timed_out_until is None:
            return await ctx.send(embed=discord.Embed(description="Ese usuario no está silenciado.", color=0xed4245))

        await member.timeout(None, reason=f"{ctx.author} ({ctx.author.id}): {reason}")
        _add_mod_action(ctx.guild.id, member.id, "unmute", ctx.author.id, reason)

        await ctx.send(embed=discord.Embed(
            description=f"{member.mention} ya no está silenciado.\n**Razón:** {reason}",
            color=0x57f287,
        ))
        await _send_mod_log(
            ctx.guild, title="Fin de Silencio", target=member, moderator=ctx.author,
            reason=reason, color=0x57f287,
        )

    # ── Warns ────────────────────────────────────────────────────────────────

    @commands.command(name="warn")
    @commands.has_permissions(kick_members=True)
    async def warn(self, ctx: commands.Context, member: discord.Member, *, reason: str = "Sin razón especificada"):
        error = _hierarchy_error(ctx, member)
        if error:
            return await ctx.send(embed=discord.Embed(description=error, color=0xed4245))

        config = db.get_guild(ctx.guild.id)
        warns = config.get("warns", {})
        key = str(member.id)
        warns.setdefault(key, []).append({
            "reason": reason,
            "moderator_id": ctx.author.id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        config["warns"] = warns
        db.update_guild(ctx.guild.id, config)
        _add_mod_action(ctx.guild.id, member.id, "warn", ctx.author.id, reason)

        total = len(warns[key])
        try:
            await member.send(embed=discord.Embed(
                description=f"Recibiste una advertencia en **{ctx.guild.name}**.\n**Razón:** {reason}",
                color=0xfee75c,
            ))
        except (discord.Forbidden, discord.HTTPException):
            pass

        await ctx.send(embed=discord.Embed(
            description=f"{member.mention} fue advertido (total: `{total}`).\n**Razón:** {reason}",
            color=0x57f287,
        ))
        await _send_mod_log(
            ctx.guild, title="Advertencia", target=member, moderator=ctx.author,
            reason=reason, extra_fields=[("Total de Advertencias", f"`{total}`", True)], color=0xfee75c,
        )

    @commands.command(name="warnings")
    @commands.has_permissions(kick_members=True)
    async def warnings(self, ctx: commands.Context, member: discord.Member):
        config = db.get_guild(ctx.guild.id)
        entries = config.get("warns", {}).get(str(member.id), [])
        if not entries:
            return await ctx.send(embed=discord.Embed(
                description=f"{member.mention} no tiene advertencias.",
                color=0x2b2d31,
            ))

        lines = []
        for i, w in enumerate(entries, start=1):
            ts = w.get("timestamp", "")
            mod = f"<@{w.get('moderator_id')}>"
            lines.append(f"**#{i}** — {w.get('reason', 'Sin razón')}\nPor {mod} · {ts[:10] if ts else '—'}")

        embed = discord.Embed(
            title=f"Advertencias de {member}",
            description="\n\n".join(lines),
            color=0x2b2d31,
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.command(name="clearwarnings", aliases=["clearwarns"])
    @commands.has_permissions(kick_members=True)
    async def clearwarnings(self, ctx: commands.Context, member: discord.Member):
        config = db.get_guild(ctx.guild.id)
        warns = config.get("warns", {})
        count = len(warns.pop(str(member.id), []))
        config["warns"] = warns
        db.update_guild(ctx.guild.id, config)

        await ctx.send(embed=discord.Embed(
            description=f"Se borraron `{count}` advertencia(s) de {member.mention}.",
            color=0x57f287,
        ))

    @commands.command(name="unwarn", aliases=["delwarn"])
    @commands.has_permissions(kick_members=True)
    async def unwarn(self, ctx: commands.Context, member: discord.Member, index: int):
        config = db.get_guild(ctx.guild.id)
        warns = config.get("warns", {})
        key = str(member.id)
        entries = warns.get(key, [])

        if index < 1 or index > len(entries):
            return await ctx.send(embed=discord.Embed(
                description=f"Índice inválido. {member.mention} tiene `{len(entries)}` advertencia(s).",
                color=0xed4245,
            ))

        removed = entries.pop(index - 1)
        warns[key] = entries
        config["warns"] = warns
        db.update_guild(ctx.guild.id, config)

        await ctx.send(embed=discord.Embed(
            description=f"Se eliminó la advertencia #{index} de {member.mention}: *{removed.get('reason', '')}*",
            color=0x57f287,
        ))

    # ── Purge ────────────────────────────────────────────────────────────────

    @commands.command(name="purge", aliases=["clear"])
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def purge(self, ctx: commands.Context, amount: int, member: discord.Member = None):
        amount = max(1, min(amount, 1000))

        def check(m: discord.Message):
            return member is None or m.author.id == member.id

        await ctx.message.delete()
        deleted = await ctx.channel.purge(limit=amount, check=check)

        msg = await ctx.send(embed=discord.Embed(
            description=f"Se borraron `{len(deleted)}` mensaje(s)"
                        + (f" de {member.mention}" if member else "") + ".",
            color=0x57f287,
        ))
        await msg.delete(delay=5)

    # ── Canales: lock / unlock / slowmode ───────────────────────────────────

    @commands.command(name="lock", aliases=["lockchannel"])
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def lock(self, ctx: commands.Context, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        overwrite = channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = False
        await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite, reason=f"Bloqueado por {ctx.author}")

        await ctx.send(embed=discord.Embed(
            description=f"{channel.mention} fue bloqueado. @everyone ya no puede escribir aquí.",
            color=0x57f287,
        ))

    @commands.command(name="unlock", aliases=["unlockchannel"])
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def unlock(self, ctx: commands.Context, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        overwrite = channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = None
        await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite, reason=f"Desbloqueado por {ctx.author}")

        await ctx.send(embed=discord.Embed(
            description=f"{channel.mention} fue desbloqueado.",
            color=0x57f287,
        ))

    @commands.command(name="slowmode")
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def slowmode(self, ctx: commands.Context, seconds: int, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        seconds = max(0, min(seconds, 21600))
        await channel.edit(slowmode_delay=seconds, reason=f"Slowmode ajustado por {ctx.author}")

        if seconds == 0:
            desc = f"Slowmode desactivado en {channel.mention}."
        else:
            desc = f"Slowmode de {channel.mention} ajustado a `{seconds}s`."
        await ctx.send(embed=discord.Embed(description=desc, color=0x57f287))

    @commands.command(name="hide")
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def hide(self, ctx: commands.Context, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        overwrite = channel.overwrites_for(ctx.guild.default_role)
        overwrite.view_channel = False
        await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite, reason=f"Ocultado por {ctx.author}")

        await ctx.send(embed=discord.Embed(
            description=f"{channel.mention} fue ocultado. @everyone ya no puede verlo.",
            color=0x57f287,
        ))

    @commands.command(name="unhide")
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def unhide(self, ctx: commands.Context, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        overwrite = channel.overwrites_for(ctx.guild.default_role)
        overwrite.view_channel = None
        await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite, reason=f"Revelado por {ctx.author}")

        await ctx.send(embed=discord.Embed(
            description=f"{channel.mention} vuelve a ser visible.",
            color=0x57f287,
        ))

    @commands.command(name="nuke")
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def nuke(self, ctx: commands.Context, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        position = channel.position

        new_channel = await channel.clone(reason=f"Nuke por {ctx.author}")
        await new_channel.edit(position=position)
        await channel.delete(reason=f"Nuke por {ctx.author}")

        await new_channel.send(embed=discord.Embed(
            description="Este canal fue reiniciado.",
            color=0x57f287,
        ))

    # ── Nick / Roles ─────────────────────────────────────────────────────────

    @commands.command(name="nickname", aliases=["nick"])
    @commands.has_permissions(manage_nicknames=True)
    @commands.bot_has_permissions(manage_nicknames=True)
    async def nickname(self, ctx: commands.Context, member: discord.Member, *, nickname: str = None):
        if nickname and nickname.lower() == "reset":
            nickname = None
        if member.id != ctx.author.id:
            error = _hierarchy_error(ctx, member)
            if error:
                return await ctx.send(embed=discord.Embed(description=error, color=0xed4245))

        await member.edit(nick=nickname, reason=f"Apodo cambiado por {ctx.author}")
        desc = f"Se restableció el apodo de {member.mention}." if nickname is None else f"El apodo de {member.mention} ahora es **{nickname}**."
        await ctx.send(embed=discord.Embed(description=desc, color=0x57f287))

    @commands.group(name="role", invoke_without_command=True)
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def role(self, ctx: commands.Context, member: discord.Member = None, role: discord.Role = None):
        if member is None or role is None:
            return await ctx.send(embed=discord.Embed(
                description="Usa `,role <@usuario> <@rol>` para añadir, `,role remove <@usuario> <@rol>` para quitar, "
                            "o `,role info <@rol>` para ver información del rol.",
                color=0x2b2d31,
            ))
        if role >= ctx.guild.me.top_role:
            return await ctx.send(embed=discord.Embed(description="Ese rol está por encima del mío, no puedo asignarlo.", color=0xed4245))
        if ctx.author.id != ctx.guild.owner_id and role >= ctx.author.top_role:
            return await ctx.send(embed=discord.Embed(description="No puedes asignar un rol igual o superior al tuyo.", color=0xed4245))

        await member.add_roles(role, reason=f"Añadido por {ctx.author}")
        await ctx.send(embed=discord.Embed(
            description=f"Se añadió el rol {role.mention} a {member.mention}.",
            color=0x57f287,
        ))

    @role.command(name="remove")
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def role_remove(self, ctx: commands.Context, member: discord.Member, role: discord.Role):
        if role >= ctx.guild.me.top_role:
            return await ctx.send(embed=discord.Embed(description="Ese rol está por encima del mío, no puedo quitarlo.", color=0xed4245))
        if ctx.author.id != ctx.guild.owner_id and role >= ctx.author.top_role:
            return await ctx.send(embed=discord.Embed(description="No puedes quitar un rol igual o superior al tuyo.", color=0xed4245))

        await member.remove_roles(role, reason=f"Removido por {ctx.author}")
        await ctx.send(embed=discord.Embed(
            description=f"Se quitó el rol {role.mention} a {member.mention}.",
            color=0x57f287,
        ))

    @role.command(name="info")
    async def role_info(self, ctx: commands.Context, *, role: discord.Role):
        e = discord.Embed(title=role.name, color=role.color if role.color.value else 0x2b2d31)
        e.add_field(name="ID", value=str(role.id), inline=True)
        e.add_field(name="Color", value=str(role.color), inline=True)
        e.add_field(name="Posición", value=str(role.position), inline=True)
        e.add_field(name="Miembros", value=str(len(role.members)), inline=True)
        e.add_field(name="Mencionable", value="Sí" if role.mentionable else "No", inline=True)
        e.add_field(name="Se muestra aparte", value="Sí" if role.hoist else "No", inline=True)
        e.add_field(name="Creado", value=discord.utils.format_dt(role.created_at, "R"), inline=True)
        await ctx.send(embed=e)

    @commands.command(name="roleall")
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def roleall(self, ctx: commands.Context, *, role: discord.Role):
        if role >= ctx.guild.me.top_role:
            return await ctx.send(embed=discord.Embed(description="Ese rol está por encima del mío, no puedo asignarlo.", color=0xed4245))
        if ctx.author.id != ctx.guild.owner_id and role >= ctx.author.top_role:
            return await ctx.send(embed=discord.Embed(description="No puedes asignar un rol igual o superior al tuyo.", color=0xed4245))

        msg = await ctx.send(embed=discord.Embed(description=f"Asignando {role.mention} a todos los miembros...", color=0x2b2d31))
        added = 0
        for member in ctx.guild.members:
            if member.bot or role in member.roles:
                continue
            try:
                await member.add_roles(role, reason=f"Roleall por {ctx.author}")
                added += 1
            except discord.HTTPException:
                continue

        await msg.edit(embed=discord.Embed(
            description=f"Se asignó {role.mention} a `{added}` miembro(s).",
            color=0x57f287,
        ))

    @commands.command(name="unroleall")
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def unroleall(self, ctx: commands.Context, *, role: discord.Role):
        if role >= ctx.guild.me.top_role:
            return await ctx.send(embed=discord.Embed(description="Ese rol está por encima del mío, no puedo quitarlo.", color=0xed4245))
        if ctx.author.id != ctx.guild.owner_id and role >= ctx.author.top_role:
            return await ctx.send(embed=discord.Embed(description="No puedes quitar un rol igual o superior al tuyo.", color=0xed4245))

        msg = await ctx.send(embed=discord.Embed(description=f"Quitando {role.mention} a todos los miembros...", color=0x2b2d31))
        removed = 0
        for member in ctx.guild.members:
            if role not in member.roles:
                continue
            try:
                await member.remove_roles(role, reason=f"Unroleall por {ctx.author}")
                removed += 1
            except discord.HTTPException:
                continue

        await msg.edit(embed=discord.Embed(
            description=f"Se quitó {role.mention} a `{removed}` miembro(s).",
            color=0x57f287,
        ))

    # ── Historial de moderación ──────────────────────────────────────────────

    @commands.command(name="modlogs")
    @commands.has_permissions(kick_members=True)
    async def modlogs(self, ctx: commands.Context, member: discord.Member):
        config = db.get_guild(ctx.guild.id)
        entries = config.get("mod_actions", {}).get(str(member.id), [])
        if not entries:
            return await ctx.send(embed=discord.Embed(
                description=f"{member.mention} no tiene historial de moderación.",
                color=0x2b2d31,
            ))

        labels = {
            "kick": "Expulsión", "ban": "Baneo", "softban": "Softban",
            "unban": "Desbaneo", "mute": "Silencio", "unmute": "Fin de silencio",
            "warn": "Advertencia",
        }
        lines = []
        for entry in entries[-15:]:
            label = labels.get(entry["type"], entry["type"])
            ts = entry.get("timestamp", "")[:10]
            lines.append(f"**{label}** — {entry['reason']}\nPor <@{entry['moderator_id']}> · {ts}")

        embed = discord.Embed(
            title=f"Historial de moderación — {member}",
            description="\n\n".join(lines),
            color=0x2b2d31,
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        if len(entries) > 15:
            embed.set_footer(text=f"Mostrando las últimas 15 de {len(entries)} acciones.")
        await ctx.send(embed=embed)

    # ── Manejo de errores de permisos, propio de este cog ────────────────────

    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.MissingPermissions):
            perms = ", ".join(error.missing_permissions)
            await ctx.send(embed=discord.Embed(
                description=f"Te falta el permiso `{perms}` para usar este comando.",
                color=0xed4245,
            ))
        elif isinstance(error, commands.BotMissingPermissions):
            perms = ", ".join(error.missing_permissions)
            await ctx.send(embed=discord.Embed(
                description=f"Me falta el permiso `{perms}` para hacer eso.",
                color=0xed4245,
            ))
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send(embed=discord.Embed(description="No encontré a ese usuario.", color=0xed4245))
        elif isinstance(error, commands.RoleNotFound):
            await ctx.send(embed=discord.Embed(description="No encontré ese rol.", color=0xed4245))
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(embed=discord.Embed(description=f"Falta el argumento `{error.param.name}`.", color=0xed4245))
        elif isinstance(error, commands.BadArgument):
            await ctx.send(embed=discord.Embed(description="Uno de los argumentos no es válido.", color=0xed4245))
        else:
            log.error(f"Error en comando de moderación: {error}")
            raise error


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
