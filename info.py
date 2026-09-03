"""
info.py — Comandos de información e utilidades de solo lectura (servidor, usuarios,
roles, canales, mensajes, invitaciones, etc.). No modifican nada en el servidor.
"""

import discord
from discord.ext import commands
import time
import platform

log_start_time = time.time()


def _info_embed(title: str = None, description: str = None) -> discord.Embed:
    e = discord.Embed(color=0x2b2d31)
    if title:
        e.title = title
    if description:
        e.description = description
    return e


class Info(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.start_time = time.time()

    # ── Bot ──────────────────────────────────────────────────────────────

    @commands.command(name="ping")
    async def ping(self, ctx: commands.Context):
        latency_ms = round(self.bot.latency * 1000)
        await ctx.send(embed=_info_embed(description=f"Pong. Latencia: `{latency_ms}ms`"))

    @commands.command(name="uptime")
    async def uptime(self, ctx: commands.Context):
        seconds = int(time.time() - self.start_time)
        days, rem = divmod(seconds, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, seconds = divmod(rem, 60)
        parts = []
        if days: parts.append(f"{days}d")
        if hours: parts.append(f"{hours}h")
        if minutes: parts.append(f"{minutes}m")
        parts.append(f"{seconds}s")
        await ctx.send(embed=_info_embed(description=f"En línea desde hace: **{' '.join(parts)}**"))

    @commands.command(name="botinfo")
    async def botinfo(self, ctx: commands.Context):
        e = _info_embed(title=self.bot.user.name)
        e.set_thumbnail(url=self.bot.user.display_avatar.url)
        total_members = sum(g.member_count or 0 for g in self.bot.guilds)
        e.add_field(name="Servidores", value=str(len(self.bot.guilds)), inline=True)
        e.add_field(name="Usuarios", value=str(total_members), inline=True)
        e.add_field(name="Latencia", value=f"{round(self.bot.latency * 1000)}ms", inline=True)
        e.add_field(name="discord.py", value=discord.__version__, inline=True)
        e.add_field(name="Python", value=platform.python_version(), inline=True)
        await ctx.send(embed=e)

    # ── Servidor ─────────────────────────────────────────────────────────

    @commands.command(name="serverinfo")
    async def serverinfo(self, ctx: commands.Context):
        g = ctx.guild
        e = _info_embed(title=g.name)
        if g.icon:
            e.set_thumbnail(url=g.icon.url)
        e.add_field(name="Dueño", value=str(g.owner) if g.owner else str(g.owner_id), inline=True)
        e.add_field(name="Miembros", value=str(g.member_count), inline=True)
        e.add_field(name="Roles", value=str(len(g.roles)), inline=True)
        e.add_field(name="Canales", value=str(len(g.channels)), inline=True)
        e.add_field(name="Boosts", value=f"Nivel {g.premium_tier} ({g.premium_subscription_count})", inline=True)
        e.add_field(name="Creado", value=discord.utils.format_dt(g.created_at, "R"), inline=True)
        await ctx.send(embed=e)

    @commands.command(name="servericon")
    async def servericon(self, ctx: commands.Context):
        if not ctx.guild.icon:
            return await ctx.send(embed=_info_embed(description="Este servidor no tiene ícono."))
        e = _info_embed(title=f"Ícono — {ctx.guild.name}")
        e.set_image(url=ctx.guild.icon.url)
        await ctx.send(embed=e)

    @commands.command(name="serverbanner")
    async def serverbanner(self, ctx: commands.Context):
        if not ctx.guild.banner:
            return await ctx.send(embed=_info_embed(description="Este servidor no tiene banner."))
        e = _info_embed(title=f"Banner — {ctx.guild.name}")
        e.set_image(url=ctx.guild.banner.url)
        await ctx.send(embed=e)

    @commands.command(name="membercount")
    async def membercount(self, ctx: commands.Context):
        await ctx.send(embed=_info_embed(description=f"**{ctx.guild.member_count}** miembros."))

    @commands.command(name="owner")
    async def owner(self, ctx: commands.Context):
        owner = ctx.guild.owner or await ctx.guild.fetch_owner()
        await ctx.send(embed=_info_embed(description=f"Dueño del servidor: {owner.mention} (`{owner}`)"))

    @commands.command(name="boosts")
    async def boosts(self, ctx: commands.Context):
        g = ctx.guild
        await ctx.send(embed=_info_embed(
            description=f"**Nivel:** {g.premium_tier}\n**Boosts:** {g.premium_subscription_count}"
        ))

    @commands.command(name="boosters")
    async def boosters(self, ctx: commands.Context):
        boosters = [m for m in ctx.guild.members if m.premium_since]
        if not boosters:
            return await ctx.send(embed=_info_embed(description="Nadie ha boosteado el servidor todavía."))
        boosters.sort(key=lambda m: m.premium_since)
        lines = [f"{m.mention} — desde {discord.utils.format_dt(m.premium_since, 'R')}" for m in boosters[:20]]
        await ctx.send(embed=_info_embed(title=f"Boosters ({len(boosters)})", description="\n".join(lines)))

    @commands.command(name="vanityinfo")
    async def vanityinfo(self, ctx: commands.Context):
        if not ctx.guild.vanity_url_code:
            return await ctx.send(embed=_info_embed(description="Este servidor no tiene enlace de vanidad."))
        try:
            uses = await ctx.guild.vanity_invite()
            await ctx.send(embed=_info_embed(
                description=f"**Código:** `{ctx.guild.vanity_url_code}`\n**Usos:** {uses.uses}"
            ))
        except discord.HTTPException:
            await ctx.send(embed=_info_embed(description=f"**Código:** `{ctx.guild.vanity_url_code}`"))

    # ── Usuarios ─────────────────────────────────────────────────────────

    @commands.command(name="userinfo")
    async def userinfo(self, ctx: commands.Context, member: discord.Member = None):
        member = member or ctx.author
        e = _info_embed(title=str(member))
        e.set_thumbnail(url=member.display_avatar.url)
        e.add_field(name="ID", value=str(member.id), inline=True)
        e.add_field(name="Cuenta creada", value=discord.utils.format_dt(member.created_at, "R"), inline=True)
        if member.joined_at:
            e.add_field(name="Se unió", value=discord.utils.format_dt(member.joined_at, "R"), inline=True)
        roles = [r.mention for r in reversed(member.roles) if r.name != "@everyone"]
        e.add_field(name=f"Roles ({len(roles)})", value=", ".join(roles[:15]) or "Ninguno", inline=False)
        await ctx.send(embed=e)

    @commands.command(name="avatar")
    async def avatar(self, ctx: commands.Context, member: discord.Member = None):
        member = member or ctx.author
        e = _info_embed(title=f"Avatar — {member}")
        e.set_image(url=member.display_avatar.url)
        await ctx.send(embed=e)

    @commands.command(name="banner")
    async def banner(self, ctx: commands.Context, member: discord.Member = None):
        member = member or ctx.author
        user = await self.bot.fetch_user(member.id)
        if not user.banner:
            return await ctx.send(embed=_info_embed(description=f"{member.mention} no tiene banner."))
        e = _info_embed(title=f"Banner — {member}")
        e.set_image(url=user.banner.url)
        await ctx.send(embed=e)

    @commands.command(name="displayname")
    async def displayname(self, ctx: commands.Context, member: discord.Member = None):
        member = member or ctx.author
        await ctx.send(embed=_info_embed(description=f"Nombre mostrado de {member.mention}: **{member.display_name}**"))

    @commands.command(name="created")
    async def created(self, ctx: commands.Context, member: discord.Member = None):
        member = member or ctx.author
        await ctx.send(embed=_info_embed(
            description=f"Cuenta de {member.mention} creada {discord.utils.format_dt(member.created_at, 'R')}"
        ))

    @commands.command(name="joined")
    async def joined(self, ctx: commands.Context, member: discord.Member = None):
        member = member or ctx.author
        if not member.joined_at:
            return await ctx.send(embed=_info_embed(description="No tengo esa información."))
        await ctx.send(embed=_info_embed(
            description=f"{member.mention} se unió {discord.utils.format_dt(member.joined_at, 'R')}"
        ))

    @commands.command(name="spotify")
    async def spotify(self, ctx: commands.Context, member: discord.Member = None):
        member = member or ctx.author
        activity = next((a for a in member.activities if isinstance(a, discord.Spotify)), None)
        if not activity:
            return await ctx.send(embed=_info_embed(description=f"{member.mention} no está escuchando Spotify ahora mismo."))
        e = _info_embed(
            title=activity.title,
            description=f"por {activity.artist}\nÁlbum: {activity.album}",
        )
        e.set_thumbnail(url=activity.album_cover_url)
        await ctx.send(embed=e)

    @commands.command(name="voiceinfo")
    async def voiceinfo(self, ctx: commands.Context, member: discord.Member = None):
        member = member or ctx.author
        if not member.voice:
            return await ctx.send(embed=_info_embed(description=f"{member.mention} no está en un canal de voz."))
        vs = member.voice
        flags = []
        if vs.mute: flags.append("muteado (servidor)")
        if vs.self_mute: flags.append("muteado")
        if vs.deaf: flags.append("ensordecido (servidor)")
        if vs.self_deaf: flags.append("ensordecido")
        if vs.self_stream: flags.append("transmitiendo")
        if vs.self_video: flags.append("cámara activa")
        await ctx.send(embed=_info_embed(
            description=f"**Canal:** {vs.channel.mention}\n**Estado:** {', '.join(flags) or 'Normal'}"
        ))

    @commands.command(name="id")
    async def id_cmd(self, ctx: commands.Context, member: discord.Member = None):
        member = member or ctx.author
        await ctx.send(embed=_info_embed(description=f"ID de {member.mention}: `{member.id}`"))

    @commands.command(name="permissions")
    async def permissions(self, ctx: commands.Context, member: discord.Member = None, channel: discord.abc.GuildChannel = None):
        member = member or ctx.author
        channel = channel or ctx.channel
        perms = channel.permissions_for(member)
        granted = [name.replace("_", " ").title() for name, value in perms if value]
        await ctx.send(embed=_info_embed(
            title=f"Permisos de {member} en #{channel.name}",
            description=", ".join(granted) or "Ninguno",
        ))

    # ── Roles ────────────────────────────────────────────────────────────

    @commands.command(name="roleinfo")
    async def roleinfo(self, ctx: commands.Context, *, role: discord.Role):
        e = _info_embed(title=role.name)
        e.add_field(name="ID", value=str(role.id), inline=True)
        e.add_field(name="Color", value=str(role.color), inline=True)
        e.add_field(name="Posición", value=str(role.position), inline=True)
        e.add_field(name="Miembros", value=str(len(role.members)), inline=True)
        e.add_field(name="Mencionable", value="Sí" if role.mentionable else "No", inline=True)
        e.add_field(name="Creado", value=discord.utils.format_dt(role.created_at, "R"), inline=True)
        await ctx.send(embed=e)

    @commands.command(name="roles")
    async def roles(self, ctx: commands.Context):
        roles = [r.mention for r in reversed(ctx.guild.roles) if r.name != "@everyone"]
        await ctx.send(embed=_info_embed(
            title=f"Roles ({len(roles)})",
            description=", ".join(roles[:40]) or "Sin roles",
        ))

    @commands.command(name="colorinfo")
    async def colorinfo(self, ctx: commands.Context, *, role: discord.Role):
        await ctx.send(embed=_info_embed(description=f"Color de **{role.name}**: `{role.color}`"))

    @commands.command(name="position")
    async def position(self, ctx: commands.Context, *, role: discord.Role):
        await ctx.send(embed=_info_embed(description=f"Posición de **{role.name}**: `{role.position}`"))

    @commands.command(name="list")
    async def list_role_members(self, ctx: commands.Context, *, role: discord.Role):
        if not role.members:
            return await ctx.send(embed=_info_embed(description=f"Nadie tiene el rol **{role.name}**."))
        lines = [m.mention for m in role.members[:40]]
        await ctx.send(embed=_info_embed(
            title=f"{role.name} ({len(role.members)})",
            description=", ".join(lines),
        ))

    # ── Canales ──────────────────────────────────────────────────────────

    @commands.command(name="channelinfo")
    async def channelinfo(self, ctx: commands.Context, channel: discord.abc.GuildChannel = None):
        channel = channel or ctx.channel
        e = _info_embed(title=f"#{channel.name}")
        e.add_field(name="ID", value=str(channel.id), inline=True)
        e.add_field(name="Tipo", value=str(channel.type).replace("_", " ").title(), inline=True)
        if channel.category:
            e.add_field(name="Categoría", value=channel.category.name, inline=True)
        e.add_field(name="Creado", value=discord.utils.format_dt(channel.created_at, "R"), inline=True)
        await ctx.send(embed=e)

    @commands.command(name="firstmessage")
    async def firstmessage(self, ctx: commands.Context, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        async for msg in channel.history(limit=1, oldest_first=True):
            return await ctx.send(embed=_info_embed(description=f"[Primer mensaje]({msg.jump_url}) de {msg.author.mention}"))
        await ctx.send(embed=_info_embed(description="No encontré mensajes en ese canal."))

    @commands.command(name="lastmessage")
    async def lastmessage(self, ctx: commands.Context, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        async for msg in channel.history(limit=2, oldest_first=False):
            if msg.id == ctx.message.id:
                continue
            return await ctx.send(embed=_info_embed(description=f"[Último mensaje]({msg.jump_url}) de {msg.author.mention}"))
        await ctx.send(embed=_info_embed(description="No encontré mensajes anteriores en ese canal."))

    @commands.command(name="messageinfo")
    async def messageinfo(self, ctx: commands.Context, message: discord.Message):
        e = _info_embed(title="Información del mensaje")
        e.add_field(name="Autor", value=str(message.author), inline=True)
        e.add_field(name="Canal", value=message.channel.mention, inline=True)
        e.add_field(name="Enviado", value=discord.utils.format_dt(message.created_at, "R"), inline=True)
        e.add_field(name="Enlace", value=f"[Ir al mensaje]({message.jump_url})", inline=False)
        if message.content:
            e.add_field(name="Contenido", value=message.content[:1000], inline=False)
        await ctx.send(embed=e)

    # ── Invitaciones ─────────────────────────────────────────────────────

    @commands.command(name="inviteinfo")
    async def inviteinfo(self, ctx: commands.Context, invite: discord.Invite):
        e = _info_embed(title=f"Invitación: {invite.code}")
        if invite.inviter:
            e.add_field(name="Creada por", value=str(invite.inviter), inline=True)
        if invite.channel:
            e.add_field(name="Canal", value=str(invite.channel), inline=True)
        if invite.uses is not None:
            e.add_field(name="Usos", value=str(invite.uses), inline=True)
        await ctx.send(embed=e)

    # ── Auditoría / snowflake ────────────────────────────────────────────

    @commands.command(name="auditlogs")
    @commands.has_permissions(view_audit_log=True)
    async def auditlogs(self, ctx: commands.Context, limit: int = 10):
        limit = max(1, min(limit, 20))
        lines = []
        async for entry in ctx.guild.audit_logs(limit=limit):
            lines.append(f"`{entry.action.name}` — {entry.user} — {discord.utils.format_dt(entry.created_at, 'R')}")
        if not lines:
            return await ctx.send(embed=_info_embed(description="No hay entradas en el registro de auditoría."))
        await ctx.send(embed=_info_embed(title="Registro de auditoría", description="\n".join(lines)))

    @commands.command(name="snowflake")
    async def snowflake(self, ctx: commands.Context, snowflake_id: int):
        created = discord.utils.snowflake_time(snowflake_id)
        await ctx.send(embed=_info_embed(
            description=f"ID `{snowflake_id}` fue creado {discord.utils.format_dt(created, 'R')} "
                        f"({discord.utils.format_dt(created, 'F')})"
        ))


async def setup(bot: commands.Bot):
    await bot.add_cog(Info(bot))
