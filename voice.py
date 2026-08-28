"""
voice.py — Sistema de voice channels temporales (Join to Create) con panel de control,
estilo VoiceMaster.

Setup:
  ,voicemaster setup (alias ,vm setup) — crea TODO automático: categoría "VoiceMaster",
                                          canal de texto "interface" (con el panel fijo)
                                          y el canal de voz "Join to Create"
  ,voicemaster reset                   — borra esos canales/categoría y limpia la configuración
  ,voicemaster panel                   — reenvía el panel al canal interface (si se borró)

Automático:
  Al unirse al canal hub, se crea un VC nuevo para el usuario (owner) y se le mueve ahí.
  El panel de control vive en el canal de texto "interface" (uno solo, fijo) y sus
  botones actúan sobre el canal de voz en el que esté conectado quien los use — no
  hace falta estar dentro del VC para usarlo. El VC se borra solo cuando queda vacío.

Panel (botones) + comandos de texto equivalentes:
  ,voice lock / ,voice unlock
  ,voice hide / ,voice unhide
  ,voice rename <nombre>
  ,voice limit <numero>
  ,voice kick <@usuario>
  ,voice claim
"""

import discord
from discord.ext import commands
from discord.http import Route
from config import db
import logging
from webhook_utils import send_via_webhook

log = logging.getLogger("antinuke.voice")

# ── Emojis del panel ────────────────────────────────────────────────────────
# Por ahora son emojis normales de Discord. Cuando subas tus emojis custom al
# bot (Developer Portal → tu App → Emojis), solo reemplaza cada valor de aquí
# por el formato "<:nombre:id_del_emoji>" y el panel los usa automáticamente.
EMOJI = {
    "lock": "<:lock:1542311910613983262>",
    "unlock": "<:unlock:1542312045364610760>",
    "hide": "<:nover:1542312009272659968>",
    "reveal": "<:ver:1542312060976718501>",
    "activity": "<:pantalla:1542312027983315034>",
    "increase": "<:mas:1542311945682022756>",
    "decrease": "<:menos:1542311955493298307>",
    "disconnect": "<:martillo:1542311934953662294>",
    "claim": "<:microfono:1542311970675884498>",
    "info": "<:notas:1542311984920630954>",
}

# Logo de marca (montaña+banderín), servido desde la CDN de emojis de Discord
BRAND_ICON_URL = "https://cdn.discordapp.com/emojis/1542311923461263391.png"

# check.png / x.png subidos como emojis de la app:
EMOJI_SUCCESS = "<:check:1542315458882179142>"
EMOJI_ERROR = "<:x_:1542315470643003442>"


def _success_embed(text: str) -> discord.Embed:
    prefix = f"{EMOJI_SUCCESS} " if EMOJI_SUCCESS else ""
    return discord.Embed(description=f"{prefix}{text}", color=0x57f287)


def _error_embed(text: str) -> discord.Embed:
    prefix = f"{EMOJI_ERROR} " if EMOJI_ERROR else ""
    return discord.Embed(description=f"{prefix}{text}", color=0xed4245)



def _build_panel_embed(guild: discord.Guild) -> discord.Embed:
    embed = discord.Embed(
        title="Panel de Voz",
        description="Usa los botones de abajo para controlar tu canal de voz.",
        color=0x2b2d31,
    )
    embed.add_field(
        name="Uso de Botones",
        value=(
            f"{EMOJI['lock']} — **Bloquear** el canal de voz\n"
            f"{EMOJI['unlock']} — **Desbloquear** el canal de voz\n"
            f"{EMOJI['hide']} — **Ocultar** el canal de voz\n"
            f"{EMOJI['activity']} — **Establecer** el estado del canal\n"
            f"{EMOJI['increase']} — **Cambiar** el límite de usuarios (subir)\n"
            f"{EMOJI['disconnect']} — **Desconectar** a un miembro\n"
            f"{EMOJI['claim']} — **Reclamar** el canal de voz\n"
            f"{EMOJI['reveal']} — **Revelar** el canal de voz\n"
            f"{EMOJI['info']} — **Ver** información del canal\n"
            f"{EMOJI['decrease']} — **Cambiar** el límite de usuarios (bajar)"
        ),
        inline=False,
    )
    embed.set_thumbnail(url=BRAND_ICON_URL)
    return embed


# ── DB helpers ────────────────────────────────────────────────────────────────

def _get_config(guild_id: int) -> dict:
    return db.get_guild(guild_id)


def _save_config(guild_id: int, config: dict):
    db.update_guild(guild_id, config)


def _get_temp_channels(guild_id: int) -> dict:
    config = _get_config(guild_id)
    return config.get("voice_temp_channels", {})


def _save_temp_channels(guild_id: int, temp: dict):
    config = _get_config(guild_id)
    config["voice_temp_channels"] = temp
    _save_config(guild_id, config)


def _get_owner(guild_id: int, channel_id: int):
    temp = _get_temp_channels(guild_id)
    owner = temp.get(str(channel_id))
    return int(owner) if owner else None


def _is_owner_or_admin(member: discord.Member, guild_id: int, channel_id: int) -> bool:
    owner = _get_owner(guild_id, channel_id)
    return member.guild_permissions.manage_channels or (owner is not None and member.id == owner)


# ── Panel de botones ──────────────────────────────────────────────────────────

class VoicePanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def on_error(self, interaction: discord.Interaction, error: Exception, item):
        log.error(f"Error en el panel de voz ({item.custom_id if hasattr(item, 'custom_id') else item}): {error}")
        message = "Ocurrió un error al ejecutar esa acción. Puede que al bot le falten permisos en este canal."
        try:
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
        except discord.HTTPException:
            pass

    async def _check(self, interaction: discord.Interaction):
        member = interaction.user
        if not member.voice or not member.voice.channel:
            await interaction.response.send_message(
                "Debes estar conectado a tu canal de voz temporal para usar esto.", ephemeral=True
            )
            return None
        channel = member.voice.channel
        if str(channel.id) not in _get_temp_channels(interaction.guild.id):
            await interaction.response.send_message("No estás en un canal de voz temporal.", ephemeral=True)
            return None
        if not _is_owner_or_admin(member, interaction.guild.id, channel.id):
            await interaction.response.send_message("Solo el dueño del canal puede usar esto.", ephemeral=True)
            return None
        return channel

    async def _resolve_member_channel(self, interaction: discord.Interaction):
        """Como _check(), pero sin exigir que seas el dueño (usado por claim/info)."""
        member = interaction.user
        if not member.voice or not member.voice.channel:
            await interaction.response.send_message(
                "Debes estar conectado a tu canal de voz temporal para usar esto.", ephemeral=True
            )
            return None
        channel = member.voice.channel
        if str(channel.id) not in _get_temp_channels(interaction.guild.id):
            await interaction.response.send_message("No estás en un canal de voz temporal.", ephemeral=True)
            return None
        return channel

    # ── Fila 1 ──────────────────────────────────────────────────────────────

    @discord.ui.button(emoji=EMOJI["lock"], style=discord.ButtonStyle.secondary, custom_id="vc_lock", row=0)
    async def lock(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = await self._check(interaction)
        if not channel:
            return
        await channel.set_permissions(interaction.guild.default_role, connect=False)
        await interaction.response.send_message(embed=_success_embed(f"Canal bloqueado {EMOJI['lock']}"), ephemeral=True)

    @discord.ui.button(emoji=EMOJI["unlock"], style=discord.ButtonStyle.secondary, custom_id="vc_unlock", row=0)
    async def unlock(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = await self._check(interaction)
        if not channel:
            return
        await channel.set_permissions(interaction.guild.default_role, connect=True)
        await interaction.response.send_message(embed=_success_embed(f"Canal desbloqueado {EMOJI['unlock']}"), ephemeral=True)

    @discord.ui.button(emoji=EMOJI["hide"], style=discord.ButtonStyle.secondary, custom_id="vc_hide", row=0)
    async def hide(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = await self._check(interaction)
        if not channel:
            return
        await channel.set_permissions(interaction.guild.default_role, view_channel=False)
        await interaction.response.send_message(embed=_success_embed(f"Canal oculto {EMOJI['hide']}"), ephemeral=True)

    @discord.ui.button(emoji=EMOJI["activity"], style=discord.ButtonStyle.secondary, custom_id="vc_activity", row=0)
    async def activity(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = await self._check(interaction)
        if not channel:
            return
        await interaction.response.send_modal(StatusModal(channel))

    @discord.ui.button(emoji=EMOJI["increase"], style=discord.ButtonStyle.secondary, custom_id="vc_increase", row=0)
    async def increase(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = await self._check(interaction)
        if not channel:
            return
        await interaction.response.send_modal(LimitModal(channel))

    # ── Fila 2 ──────────────────────────────────────────────────────────────

    @discord.ui.button(emoji=EMOJI["disconnect"], style=discord.ButtonStyle.secondary, custom_id="vc_disconnect", row=1)
    async def disconnect(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = await self._check(interaction)
        if not channel:
            return
        view = KickSelectView(channel)
        await interaction.response.send_message(embed=discord.Embed(description=f"{EMOJI['disconnect']} Elige a quién desconectar de tu canal:", color=0x2b2d31), view=view, ephemeral=True)

    @discord.ui.button(emoji=EMOJI["claim"], style=discord.ButtonStyle.secondary, custom_id="vc_claim", row=1)
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = await self._resolve_member_channel(interaction)
        if not channel:
            return

        owner_id = _get_owner(interaction.guild.id, channel.id)
        owner_still_here = owner_id and interaction.guild.get_member(owner_id) in channel.members

        if owner_still_here:
            return await interaction.response.send_message(embed=_error_embed("El dueño sigue en el canal, no se puede reclamar."), ephemeral=True)

        temp = _get_temp_channels(interaction.guild.id)
        temp[str(channel.id)] = interaction.user.id
        _save_temp_channels(interaction.guild.id, temp)

        await channel.set_permissions(interaction.user, manage_channels=True, move_members=True, mute_members=True)
        await interaction.response.send_message(embed=_success_embed(f"{interaction.user.mention} ahora es el dueño de {channel.mention} {EMOJI['claim']}"), ephemeral=True)

    @discord.ui.button(emoji=EMOJI["reveal"], style=discord.ButtonStyle.secondary, custom_id="vc_reveal", row=1)
    async def reveal(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = await self._check(interaction)
        if not channel:
            return
        await channel.set_permissions(interaction.guild.default_role, view_channel=True)
        await interaction.response.send_message(embed=_success_embed(f"Canal visible {EMOJI['reveal']}"), ephemeral=True)

    @discord.ui.button(emoji=EMOJI["info"], style=discord.ButtonStyle.secondary, custom_id="vc_info", row=1)
    async def info(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = await self._resolve_member_channel(interaction)
        if not channel:
            return

        owner_id = _get_owner(interaction.guild.id, channel.id)
        owner = interaction.guild.get_member(owner_id) if owner_id else None
        perms_everyone = channel.overwrites_for(interaction.guild.default_role)

        embed = discord.Embed(title=f"{EMOJI['info']} Información — {channel.name}", color=0x2b2d31)
        embed.add_field(name="Dueño", value=owner.mention if owner else "Desconocido", inline=True)
        embed.add_field(name="Miembros conectados", value=str(len(channel.members)), inline=True)
        embed.add_field(name="Límite de usuarios", value=str(channel.user_limit or "Sin límite"), inline=True)
        embed.add_field(name="Bloqueado", value="Sí" if perms_everyone.connect is False else "No", inline=True)
        embed.add_field(name="Oculto", value="Sí" if perms_everyone.view_channel is False else "No", inline=True)
        embed.add_field(name="ID del canal", value=f"`{channel.id}`", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(emoji=EMOJI["decrease"], style=discord.ButtonStyle.secondary, custom_id="vc_decrease", row=1)
    async def decrease(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = await self._check(interaction)
        if not channel:
            return
        await interaction.response.send_modal(LimitModal(channel))


class StatusModal(discord.ui.Modal, title="Estado del canal"):
    def __init__(self, channel: discord.VoiceChannel):
        super().__init__()
        self.channel = channel
        self.text_input = discord.ui.TextInput(
            label="Texto del estado",
            placeholder="Ej. Jugando Valorant, En pausa, Chill...",
            required=False,
            max_length=500,
        )
        self.add_item(self.text_input)

    async def on_submit(self, interaction: discord.Interaction):
        text = self.text_input.value.strip()
        try:
            await interaction.client.http.request(
                Route("PATCH", "/channels/{channel_id}", channel_id=self.channel.id),
                json={"status": text},
            )
        except discord.HTTPException as e:
            return await interaction.response.send_message(embed=_error_embed(f"No se pudo actualizar el estado: {e}"), ephemeral=True)

        if text:
            await interaction.response.send_message(embed=_success_embed(f"Estado del canal actualizado a: **{text}**"), ephemeral=True)
        else:
            await interaction.response.send_message(embed=_success_embed("Estado del canal borrado."), ephemeral=True)


class LimitModal(discord.ui.Modal, title="Límite de usuarios"):
    def __init__(self, channel: discord.VoiceChannel):
        super().__init__()
        self.channel = channel
        self.number_input = discord.ui.TextInput(
            label="Límite (0-99, 0 = sin límite)",
            placeholder="Ej. 5",
            required=True,
            max_length=2,
        )
        self.add_item(self.number_input)

    async def on_submit(self, interaction: discord.Interaction):
        raw = self.number_input.value.strip()
        if not raw.isdigit():
            return await interaction.response.send_message(embed=_error_embed("Escribe solo un número."), ephemeral=True)
        limit = max(0, min(int(raw), 99))
        await self.channel.edit(user_limit=limit)
        label = str(limit) if limit else "sin límite"
        await interaction.response.send_message(embed=_success_embed(f"Límite ajustado a `{label}`."), ephemeral=True)


class KickSelectView(discord.ui.View):
    def __init__(self, channel: discord.VoiceChannel):
        super().__init__(timeout=60)
        self.add_item(KickSelect(channel))


class KickSelect(discord.ui.UserSelect):
    def __init__(self, channel: discord.VoiceChannel):
        super().__init__(placeholder="Selecciona un usuario para sacar del VC")
        self.channel = channel

    async def callback(self, interaction: discord.Interaction):
        member = self.values[0]
        if member.voice and member.voice.channel and member.voice.channel.id == self.channel.id:
            await member.move_to(None, reason=f"Kick del VC por {interaction.user}")
            await interaction.response.send_message(
                embed=_success_embed(f"{EMOJI['disconnect']} {member.mention} fue sacado del canal."), ephemeral=True
            )
        else:
            await interaction.response.send_message(embed=_error_embed("Ese usuario ya no está en el canal."), ephemeral=True)


# ── Cog ──────────────────────────────────────────────────────────────────────

class Voice(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        bot.add_view(VoicePanel())  # persistente tras reinicios

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        guild = member.guild
        config = _get_config(guild.id)
        hub_id = config.get("voice_hub_channel_id")
        temp = _get_temp_channels(guild.id)

        # Se unió al hub → crear canal nuevo
        if hub_id and after.channel and after.channel.id == int(hub_id):
            category = after.channel.category
            new_channel = await guild.create_voice_channel(
                name=f"{member.display_name}'s VC",
                category=category,
                reason=f"Voice temporal para {member}",
            )
            await new_channel.set_permissions(member, manage_channels=True, move_members=True, mute_members=True)
            await member.move_to(new_channel)

            temp[str(new_channel.id)] = member.id
            _save_temp_channels(guild.id, temp)

        # Salió de un canal temporal → borrar si quedó vacío
        if before.channel and str(before.channel.id) in temp:
            if len(before.channel.members) == 0:
                try:
                    await before.channel.delete(reason="Voice temporal vacío")
                except discord.NotFound:
                    pass
                temp.pop(str(before.channel.id), None)
                _save_temp_channels(guild.id, temp)

    @commands.group(name="voicemaster", aliases=["vm"], invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def voicemaster(self, ctx: commands.Context):
        e = discord.Embed(title="VoiceMaster Commands", color=0x2b2d31)
        e.description = (
            "`,voicemaster setup` - Configura el sistema VoiceMaster\n"
            "`,voicemaster reset` - Restablece la configuración"
        )
        await ctx.send(embed=e)

    @voicemaster.command(name="setup")
    @commands.has_permissions(manage_guild=True)
    async def voicemaster_setup(self, ctx: commands.Context):
        config = _get_config(ctx.guild.id)
        if config.get("voice_hub_channel_id"):
            return await ctx.send(embed=_error_embed("VoiceMaster ya está configurado. Usa `,voicemaster reset` para reconfigurarlo."))

        category = await ctx.guild.create_category("VoiceMaster", reason=f"VoiceMaster setup por {ctx.author}")

        interface = await ctx.guild.create_text_channel(
            "interface",
            category=category,
            reason=f"Canal de panel de voz creado por {ctx.author}",
        )

        hub = await ctx.guild.create_voice_channel(
            "Join to Create",
            category=category,
            reason=f"Voice hub creado por {ctx.author}",
        )

        config["voice_category_id"] = category.id
        config["voice_hub_channel_id"] = hub.id
        config["voice_interface_channel_id"] = interface.id
        _save_config(ctx.guild.id, config)

        try:
            await send_via_webhook(interface, embed=_build_panel_embed(ctx.guild), view=VoicePanel())
        except discord.Forbidden:
            pass

        await ctx.send(embed=_success_embed("Sistema VoiceMaster configurado correctamente."))

    @voicemaster.command(name="reset")
    @commands.has_permissions(manage_guild=True)
    async def voicemaster_reset(self, ctx: commands.Context):
        config = _get_config(ctx.guild.id)

        category_id = config.get("voice_category_id")
        hub_id = config.get("voice_hub_channel_id")
        interface_id = config.get("voice_interface_channel_id")

        for channel_id in (hub_id, interface_id):
            if not channel_id:
                continue
            channel = ctx.guild.get_channel(int(channel_id))
            if channel:
                try:
                    await channel.delete(reason=f"VoiceMaster reset por {ctx.author}")
                except discord.HTTPException:
                    pass

        if category_id:
            category = ctx.guild.get_channel(int(category_id))
            if category and isinstance(category, discord.CategoryChannel) and not category.channels:
                try:
                    await category.delete(reason=f"VoiceMaster reset por {ctx.author}")
                except discord.HTTPException:
                    pass

        for temp_channel_id in list(_get_temp_channels(ctx.guild.id).keys()):
            channel = ctx.guild.get_channel(int(temp_channel_id))
            if channel:
                try:
                    await channel.delete(reason=f"VoiceMaster reset por {ctx.author}")
                except discord.HTTPException:
                    pass

        config["voice_category_id"] = None
        config["voice_hub_channel_id"] = None
        config["voice_interface_channel_id"] = None
        config["voice_temp_channels"] = {}
        _save_config(ctx.guild.id, config)

        await ctx.send(embed=_success_embed("Configuración restablecida."))

    @voicemaster.command(name="panel")
    @commands.has_permissions(manage_guild=True)
    async def voicemaster_panel(self, ctx: commands.Context):
        config = _get_config(ctx.guild.id)
        interface_id = config.get("voice_interface_channel_id")
        interface = ctx.guild.get_channel(int(interface_id)) if interface_id else None
        if not interface:
            return await ctx.send(embed=_error_embed("No hay un canal de panel configurado. Usa `,voicemaster setup` primero."))
        try:
            await send_via_webhook(interface, embed=_build_panel_embed(ctx.guild), view=VoicePanel())
        except discord.Forbidden:
            return await ctx.send(embed=_error_embed("No tengo permisos para mandar mensajes ahí."))
        await ctx.send(embed=_success_embed(f"Panel reenviado a {interface.mention}."))

    @commands.group(name="voice", invoke_without_command=True)
    async def voice(self, ctx: commands.Context):
        await ctx.send(embed=discord.Embed(
            description="Usa `,voice lock`, `,voice unlock`, `,voice hide`, `,voice unhide`, `,voice rename <nombre>`, `,voice limit <n>`, `,voice kick <@user>` o `,voice claim` (dentro de tu VC temporal).",
            color=0x2b2d31,
        ))

    async def _current_temp_channel(self, ctx: commands.Context):
        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.send(embed=_error_embed("Debes estar en un canal de voz temporal."))
            return None
        channel = ctx.author.voice.channel
        if str(channel.id) not in _get_temp_channels(ctx.guild.id):
            await ctx.send(embed=_error_embed("Ese no es un canal de voz temporal."))
            return None
        if not _is_owner_or_admin(ctx.author, ctx.guild.id, channel.id):
            await ctx.send(embed=_error_embed("No eres el dueño de este canal."))
            return None
        return channel

    @voice.command(name="lock")
    async def voice_lock(self, ctx: commands.Context):
        channel = await self._current_temp_channel(ctx)
        if not channel:
            return
        await channel.set_permissions(ctx.guild.default_role, connect=False)
        await ctx.send(embed=_success_embed(f"Canal bloqueado {EMOJI['lock']}"))

    @voice.command(name="unlock")
    async def voice_unlock(self, ctx: commands.Context):
        channel = await self._current_temp_channel(ctx)
        if not channel:
            return
        await channel.set_permissions(ctx.guild.default_role, connect=True)
        await ctx.send(embed=_success_embed(f"Canal desbloqueado {EMOJI['unlock']}"))

    @voice.command(name="hide")
    async def voice_hide(self, ctx: commands.Context):
        channel = await self._current_temp_channel(ctx)
        if not channel:
            return
        await channel.set_permissions(ctx.guild.default_role, view_channel=False)
        await ctx.send(embed=_success_embed(f"Canal oculto {EMOJI['hide']}"))

    @voice.command(name="unhide")
    async def voice_unhide(self, ctx: commands.Context):
        channel = await self._current_temp_channel(ctx)
        if not channel:
            return
        await channel.set_permissions(ctx.guild.default_role, view_channel=True)
        await ctx.send(embed=_success_embed(f"Canal visible {EMOJI['reveal']}"))

    @voice.command(name="rename")
    async def voice_rename(self, ctx: commands.Context, *, name: str):
        channel = await self._current_temp_channel(ctx)
        if not channel:
            return
        await channel.edit(name=name[:100])
        await ctx.send(embed=_success_embed(f"Canal renombrado a **{name[:100]}**."))

    @voice.command(name="limit")
    async def voice_limit(self, ctx: commands.Context, number: int):
        channel = await self._current_temp_channel(ctx)
        if not channel:
            return
        await channel.edit(user_limit=max(0, min(number, 99)))
        await ctx.send(embed=_success_embed(f"Límite ajustado a `{number}`."))

    @voice.command(name="kick")
    async def voice_kick(self, ctx: commands.Context, member: discord.Member):
        channel = await self._current_temp_channel(ctx)
        if not channel:
            return
        if member.voice and member.voice.channel and member.voice.channel.id == channel.id:
            await member.move_to(None, reason=f"Kick del VC por {ctx.author}")
            await ctx.send(embed=_success_embed(f"{EMOJI['disconnect']} {member.mention} fue sacado del canal."))
        else:
            await ctx.send(embed=_error_embed("Ese usuario no está en tu canal."))

    @voice.command(name="claim")
    async def voice_claim(self, ctx: commands.Context):
        if not ctx.author.voice or not ctx.author.voice.channel:
            return await ctx.send(embed=_error_embed("Debes estar en un canal de voz."))
        channel = ctx.author.voice.channel
        temp = _get_temp_channels(ctx.guild.id)
        if str(channel.id) not in temp:
            return await ctx.send(embed=_error_embed("Ese no es un canal temporal."))

        owner_id = temp.get(str(channel.id))
        owner_still_here = owner_id and ctx.guild.get_member(int(owner_id)) in channel.members

        if owner_still_here:
            return await ctx.send(embed=_error_embed("El dueño sigue en el canal."))

        temp[str(channel.id)] = ctx.author.id
        _save_temp_channels(ctx.guild.id, temp)
        await channel.set_permissions(ctx.author, manage_channels=True, move_members=True, mute_members=True)
        await ctx.send(embed=_success_embed(f"{ctx.author.mention} ahora es el dueño de este canal {EMOJI['claim']}"))


async def setup(bot: commands.Bot):
    await bot.add_cog(Voice(bot))
