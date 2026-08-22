"""
module_panel.py — Panel interactivo de configuración por módulo.

Cada módulo de AntiNuke puede tener su propio castigo, canal de logs y
whitelist (usuarios + roles), independientes de la configuración global.
Si un módulo no tiene nada propio configurado, todo cae de vuelta a la
configuración global (compatibilidad con servidores existentes).
"""

import discord
from config import db
from settings import MODULES

MODULE_LABELS = {
    "ban": "Anti-Ban Masivo",
    "kick": "Anti-Kick Masivo",
    "channeldelete": "Anti-Eliminación de Canales",
    "channelcreate": "Anti-Creación de Canales",
    "roledelete": "Anti-Eliminación de Roles",
    "rolecreate": "Anti-Creación de Roles",
    "roleadd": "Anti-Asignación de Roles",
    "webhook": "Anti-Webhook",
    "mention": "Anti-Spam de Menciones",
    "emojidelete": "Anti-Eliminación de Emojis",
    "botadd": "Anti-Bot Add",
    "everyone": "Anti-Mención Everyone",
    "serverupdate": "Anti-Actualización del Servidor",
    "prune": "Anti-Prune",
    "roleperm": "Anti-Permisos de Rol",
}

PUNISHMENT_CHOICES = ("ban", "kick", "strip", "mute")


def _invalidate_cache(guild_id: int):
    try:
        from antinuke import invalidate_config_cache
        invalidate_config_cache(guild_id)
    except ImportError:
        pass


def _get_module_config(config: dict, module_key: str) -> dict:
    return config.get("module_settings", {}).get(module_key, {})


def _save_module_config(guild_id: int, module_key: str, **updates):
    config = db.get_guild(guild_id)
    config.setdefault("module_settings", {})
    config["module_settings"].setdefault(module_key, {})
    config["module_settings"][module_key].update(updates)
    db.update_guild(guild_id, config)
    _invalidate_cache(guild_id)


# ── Embeds ──────────────────────────────────────────────────────────────────

def build_module_embed(bot: discord.Client, guild: discord.Guild, module_key: str) -> discord.Embed:
    config = db.get_guild(guild.id)
    an = config.get("antinuke", {})
    toggle_key, threshold_key, window_key = MODULES[module_key]
    mod_cfg = _get_module_config(config, module_key)

    enabled = an.get("enabled", False) and an.get(toggle_key, True)
    punishment = mod_cfg.get("punishment") or an.get("punishment", "ban")
    is_override = "punishment" in mod_cfg
    log_channel_id = mod_cfg.get("log_channel")
    log_text = f"<#{log_channel_id}>" if log_channel_id else "Sin configurar (usa el canal global)"
    wl = mod_cfg.get("whitelist", {})
    wl_count = len(wl.get("users", [])) + len(wl.get("roles", []))

    lines = [
        f"**Status:** {'Enabled' if enabled else 'Disabled'}",
        f"**Punishment:** `{punishment}`" + (" *(propio)*" if is_override else " *(global)*"),
        f"**Logs:** {log_text}",
        f"**Whitelisted:** {wl_count} entradas",
    ]
    if threshold_key:
        lines.append(f"**Threshold:** {an.get(threshold_key, 3)} en {an.get(window_key, 10)}s")

    e = discord.Embed(title=MODULE_LABELS.get(module_key, module_key), description="\n".join(lines), color=0x2b2d31)
    e.set_author(name=f"{bot.user.name}", icon_url=bot.user.display_avatar.url)
    e.set_footer(text="Usa el menú desplegable para configurar")
    return e


def build_whitelist_embed(module_key: str, guild: discord.Guild) -> discord.Embed:
    config = db.get_guild(guild.id)
    wl = _get_module_config(config, module_key).get("whitelist", {})
    users = wl.get("users", [])
    roles = wl.get("roles", [])

    user_text = "\n".join(f"<@{u}>" for u in users) or "None"
    role_text = "\n".join(f"<@&{r}>" for r in roles) or "None"

    e = discord.Embed(
        title="Whitelist Management",
        description=f"Manage whitelisted users and roles for **{MODULE_LABELS.get(module_key, module_key)}**",
        color=0x2b2d31,
    )
    e.add_field(name=f"Users ({len(users)})", value=user_text[:1024], inline=False)
    e.add_field(name=f"Roles ({len(roles)})", value=role_text[:1024], inline=False)
    e.set_footer(text="Use the buttons below to manage whitelist entries")
    return e


# ── Modales ─────────────────────────────────────────────────────────────────

class PunishmentModal(discord.ui.Modal, title="Configure Punishment"):
    def __init__(self, bot: discord.Client, module_key: str, parent_view: discord.ui.View):
        super().__init__()
        self.bot = bot
        self.module_key = module_key
        self.parent_view = parent_view
        self.value_input = discord.ui.TextInput(
            label="Punishment Type",
            placeholder="ban, kick, strip o mute",
            required=True,
            max_length=10,
        )
        self.add_item(self.value_input)

    async def on_submit(self, interaction: discord.Interaction):
        value = self.value_input.value.strip().lower()
        if value not in PUNISHMENT_CHOICES:
            return await interaction.response.send_message(
                f"Castigo inválido. Usa uno de: {', '.join(PUNISHMENT_CHOICES)}", ephemeral=True
            )
        _save_module_config(interaction.guild.id, self.module_key, punishment=value)
        embed = build_module_embed(self.bot, interaction.guild, self.module_key)
        await interaction.response.edit_message(embed=embed, view=self.parent_view)


class LogsModal(discord.ui.Modal, title="Configure Logs Channel"):
    def __init__(self, bot: discord.Client, module_key: str, parent_view: discord.ui.View):
        super().__init__()
        self.bot = bot
        self.module_key = module_key
        self.parent_view = parent_view
        self.value_input = discord.ui.TextInput(
            label="Channel ID or #mention",
            placeholder="#logs o el ID del canal (vacío = usar el canal global)",
            required=False,
            max_length=100,
        )
        self.add_item(self.value_input)

    async def on_submit(self, interaction: discord.Interaction):
        raw = self.value_input.value.strip()
        if not raw:
            _save_module_config(interaction.guild.id, self.module_key, log_channel=None)
            embed = build_module_embed(self.bot, interaction.guild, self.module_key)
            return await interaction.response.edit_message(embed=embed, view=self.parent_view)

        channel_id = "".join(ch for ch in raw if ch.isdigit())
        if not channel_id:
            return await interaction.response.send_message(
                "Canal inválido. Usa un #mention o el ID del canal.", ephemeral=True
            )
        channel = interaction.guild.get_channel(int(channel_id))
        if channel is None:
            return await interaction.response.send_message("No encontré ese canal en este servidor.", ephemeral=True)

        _save_module_config(interaction.guild.id, self.module_key, log_channel=channel.id)
        embed = build_module_embed(self.bot, interaction.guild, self.module_key)
        await interaction.response.edit_message(embed=embed, view=self.parent_view)


class ThresholdModal(discord.ui.Modal, title="Configure Threshold"):
    def __init__(self, bot: discord.Client, module_key: str, parent_view: discord.ui.View):
        super().__init__()
        self.bot = bot
        self.module_key = module_key
        self.parent_view = parent_view
        self.threshold_input = discord.ui.TextInput(label="Threshold (cantidad)", placeholder="ej. 3", required=True, max_length=4)
        self.window_input = discord.ui.TextInput(label="Window (segundos)", placeholder="ej. 10", required=True, max_length=4)
        self.add_item(self.threshold_input)
        self.add_item(self.window_input)

    async def on_submit(self, interaction: discord.Interaction):
        t_raw = self.threshold_input.value.strip()
        w_raw = self.window_input.value.strip()
        if not (t_raw.isdigit() and w_raw.isdigit()):
            return await interaction.response.send_message("Threshold y Window deben ser números.", ephemeral=True)

        threshold, window = int(t_raw), int(w_raw)
        if threshold < 1 or window < 1:
            return await interaction.response.send_message("Deben ser mayores a 0.", ephemeral=True)

        toggle_key, threshold_key, window_key = MODULES[self.module_key]
        config = db.get_guild(interaction.guild.id)
        config.setdefault("antinuke", {})
        config["antinuke"][threshold_key] = threshold
        config["antinuke"][window_key] = window
        db.update_guild(interaction.guild.id, config)
        _invalidate_cache(interaction.guild.id)

        embed = build_module_embed(self.bot, interaction.guild, self.module_key)
        await interaction.response.edit_message(embed=embed, view=self.parent_view)


class WhitelistAddModal(discord.ui.Modal, title="Add Whitelist Entry"):
    def __init__(self, bot: discord.Client, module_key: str):
        super().__init__()
        self.bot = bot
        self.module_key = module_key
        self.value_input = discord.ui.TextInput(
            label="Usuario o Rol (mención o ID)",
            placeholder="@usuario, @rol, o su ID",
            required=True,
            max_length=100,
        )
        self.add_item(self.value_input)

    async def on_submit(self, interaction: discord.Interaction):
        raw_id = "".join(ch for ch in self.value_input.value.strip() if ch.isdigit())
        if not raw_id:
            return await interaction.response.send_message("No pude leer un ID válido ahí.", ephemeral=True)
        entry_id = int(raw_id)

        guild = interaction.guild
        role = guild.get_role(entry_id)
        member = guild.get_member(entry_id)

        config = db.get_guild(guild.id)
        config.setdefault("module_settings", {}).setdefault(self.module_key, {})
        wl = config["module_settings"][self.module_key].setdefault("whitelist", {"users": [], "roles": []})

        if member is not None:
            if entry_id not in wl.setdefault("users", []):
                wl["users"].append(entry_id)
        elif role is not None:
            if entry_id not in wl.setdefault("roles", []):
                wl["roles"].append(entry_id)
        else:
            return await interaction.response.send_message(
                "No encontré ese usuario ni ese rol en este servidor.", ephemeral=True
            )

        db.update_guild(guild.id, config)
        _invalidate_cache(guild.id)

        embed = build_whitelist_embed(self.module_key, guild)
        await interaction.response.edit_message(embed=embed, view=WhitelistView(self.bot, self.module_key))


class WhitelistRemoveModal(discord.ui.Modal, title="Remove Whitelist Entry"):
    def __init__(self, bot: discord.Client, module_key: str):
        super().__init__()
        self.bot = bot
        self.module_key = module_key
        self.value_input = discord.ui.TextInput(
            label="Usuario o Rol (mención o ID)",
            placeholder="@usuario, @rol, o su ID",
            required=True,
            max_length=100,
        )
        self.add_item(self.value_input)

    async def on_submit(self, interaction: discord.Interaction):
        raw_id = "".join(ch for ch in self.value_input.value.strip() if ch.isdigit())
        if not raw_id:
            return await interaction.response.send_message("No pude leer un ID válido ahí.", ephemeral=True)
        entry_id = int(raw_id)

        guild = interaction.guild
        config = db.get_guild(guild.id)
        config.setdefault("module_settings", {}).setdefault(self.module_key, {})
        wl = config["module_settings"][self.module_key].setdefault("whitelist", {"users": [], "roles": []})

        removed = False
        if entry_id in wl.get("users", []):
            wl["users"].remove(entry_id)
            removed = True
        if entry_id in wl.get("roles", []):
            wl["roles"].remove(entry_id)
            removed = True

        if not removed:
            return await interaction.response.send_message("Esa entrada no estaba en la whitelist.", ephemeral=True)

        db.update_guild(guild.id, config)
        _invalidate_cache(guild.id)

        embed = build_whitelist_embed(self.module_key, guild)
        await interaction.response.edit_message(embed=embed, view=WhitelistView(self.bot, self.module_key))


# ── Vistas ──────────────────────────────────────────────────────────────────

class WhitelistView(discord.ui.View):
    def __init__(self, bot: discord.Client, module_key: str):
        super().__init__(timeout=120)
        self.bot = bot
        self.module_key = module_key

    @discord.ui.button(label="Add Entry", style=discord.ButtonStyle.success)
    async def add_entry(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(WhitelistAddModal(self.bot, self.module_key))

    @discord.ui.button(label="Remove Entry", style=discord.ButtonStyle.danger)
    async def remove_entry(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(WhitelistRemoveModal(self.bot, self.module_key))

    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.secondary)
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = build_whitelist_embed(self.module_key, interaction.guild)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.secondary)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Panel cerrado.", embed=None, view=None)


class ModuleActionSelect(discord.ui.Select):
    def __init__(self, bot: discord.Client, module_key: str):
        self.bot = bot
        self.module_key = module_key
        toggle_key, threshold_key, window_key = MODULES[module_key]

        options = [
            discord.SelectOption(label="Enable", value="enable", description=f"Enable {MODULE_LABELS.get(module_key, module_key)}"),
            discord.SelectOption(label="Disable", value="disable", description=f"Disable {MODULE_LABELS.get(module_key, module_key)}"),
            discord.SelectOption(label="Punishment", value="punishment", description="Set punishment type"),
            discord.SelectOption(label="Logs", value="logs", description="Configure logs channel"),
        ]
        if threshold_key:
            options.append(discord.SelectOption(label="Threshold", value="threshold", description="Set threshold and window"))
        options.append(discord.SelectOption(label="Whitelist", value="whitelist", description="Manage whitelisted users and roles"))
        options.append(discord.SelectOption(label="Reset", value="reset", description="Reset to global configuration"))

        super().__init__(placeholder="Select an option...", options=options)

    async def callback(self, interaction: discord.Interaction):
        action = self.values[0]
        guild = interaction.guild
        toggle_key, threshold_key, window_key = MODULES[self.module_key]

        if action in ("enable", "disable"):
            config = db.get_guild(guild.id)
            config.setdefault("antinuke", {})
            config["antinuke"][toggle_key] = (action == "enable")
            db.update_guild(guild.id, config)
            _invalidate_cache(guild.id)
            embed = build_module_embed(self.bot, guild, self.module_key)
            return await interaction.response.edit_message(embed=embed, view=self.view)

        if action == "reset":
            config = db.get_guild(guild.id)
            config.get("module_settings", {}).pop(self.module_key, None)
            db.update_guild(guild.id, config)
            _invalidate_cache(guild.id)
            embed = build_module_embed(self.bot, guild, self.module_key)
            return await interaction.response.edit_message(embed=embed, view=self.view)

        if action == "punishment":
            return await interaction.response.send_modal(PunishmentModal(self.bot, self.module_key, self.view))

        if action == "logs":
            return await interaction.response.send_modal(LogsModal(self.bot, self.module_key, self.view))

        if action == "threshold":
            return await interaction.response.send_modal(ThresholdModal(self.bot, self.module_key, self.view))

        if action == "whitelist":
            embed = build_whitelist_embed(self.module_key, guild)
            view = WhitelistView(self.bot, self.module_key)
            return await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class ModuleConfigView(discord.ui.View):
    def __init__(self, bot: discord.Client, module_key: str):
        super().__init__(timeout=180)
        self.add_item(ModuleActionSelect(bot, module_key))

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
