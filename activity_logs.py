"""
activity_logs.py — Registra en tiempo real eventos de mensajes, miembros,
voz e invitaciones hacia sus canales de logs correspondientes (creados con
,setuplogs). No requiere configuración extra: en cuanto los canales de logs
existan, estos eventos empiezan a mandarse solos.

Estos son logs INFORMATIVOS (nadie fue castigado) — por eso ninguna llamada
a send_log() de aquí pasa el parámetro punishment. Los logs de castigos
reales por detección de nuke/raid viven en antinuke.py.

Nota sobre mensajes: Discord solo entrega el contenido de un mensaje
eliminado/editado si el bot ya lo tenía en caché (lo vio pasar mientras
estaba online). Mensajes de antes de que el bot arrancara no se pueden
recuperar — es una limitación de la API de Discord, no del bot.
"""

import discord
from discord.ext import commands
from logger import send_log
import logging

log = logging.getLogger("antinuke.activity_logs")


class ActivityLogs(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── Mensajes ─────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        content = message.content or "*(sin texto — puede ser una imagen, embed o adjunto)*"
        if len(content) > 950:
            content = content[:950] + "..."
        await send_log(
            message.guild,
            action="delete",
            target=message.author,
            moderator=None,
            reason=f"Mensaje eliminado en {message.channel.mention}",
            module="Mensaje Eliminado",
            category="messages",
            extra_fields=[("Contenido", f"```{content}```", False)],
        )

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if not before.guild or before.author.bot or before.content == after.content:
            return
        antes = (before.content or "*vacío*")[:450]
        despues = (after.content or "*vacío*")[:450]
        await send_log(
            before.guild,
            action="edit",
            target=before.author,
            moderator=None,
            reason=f"Mensaje editado en {before.channel.mention}",
            module="Mensaje Editado",
            category="messages",
            extra_fields=[("Antes", f"```{antes}```", False), ("Después", f"```{despues}```", False)],
        )

    # ── Miembros ─────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        await send_log(
            member.guild,
            action="join",
            target=member,
            moderator=None,
            reason="Un nuevo miembro se unió al servidor",
            module="Miembro Ingresó",
            category="members",
            extra_fields=[("Cuenta creada", discord.utils.format_dt(member.created_at, "R"), True)],
        )

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        await send_log(
            member.guild,
            action="leave",
            target=member,
            moderator=None,
            reason="Un miembro salió del servidor",
            module="Miembro Salió",
            category="members",
        )

    # ── Voz ──────────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if before.channel == after.channel:
            return
        if before.channel is None and after.channel is not None:
            reason = f"Se unió a {after.channel.mention}"
        elif before.channel is not None and after.channel is None:
            reason = f"Salió de {before.channel.mention}"
        else:
            reason = f"Se movió de {before.channel.mention} a {after.channel.mention}"
        await send_log(
            member.guild,
            action="voice",
            target=member,
            moderator=None,
            reason=reason,
            module="Actividad de Voz",
            category="voice",
        )

    # ── Invitaciones ─────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite):
        await send_log(
            invite.guild,
            action="invite_create",
            target=invite.inviter,
            moderator=None,
            reason=f"Invitación creada: `{invite.code}` en {invite.channel.mention}",
            module="Invitación Creada",
            category="invites",
        )

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite):
        await send_log(
            invite.guild,
            action="invite_delete",
            target=None,
            moderator=None,
            reason=f"Invitación eliminada: `{invite.code}`",
            module="Invitación Eliminada",
            category="invites",
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(ActivityLogs(bot))
