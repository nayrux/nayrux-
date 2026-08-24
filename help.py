import discord
from discord.ext import commands
from config import db
import logging

log = logging.getLogger("antinuke.help")

SUPPORT_SERVER_URL = "https://discord.gg/hMJ3wWzkFF"
BRAND_ICON_URL = "https://i.pinimg.com/736x/78/ab/07/78ab072e66ef17fe638524e9a072cc74.jpg"

# ── Tabla de comandos ──────────────────────────────────────────────────────
# Cada categoría tiene "sections": lista de (subtítulo, [comandos], nota_opcional)

CATEGORIES = {
    "automation": {
        "label": "Automation",
        "description": "AutoRole, AutoReact y AutoGreet — automatiza roles, reacciones y bienvenidas.",
        "sections": [
            ("AutoRole", [
                ",autorole setup <rol>",
                ",autorole toggle",
                ",autorole add <rol>",
                ",autorole remove <rol>",
                ",autorole addbot <rol>",
                ",autorole removebot <rol>",
                ",autorole list",
                ",autorole clear",
                ",autorole info",
                ",autorole reset",
            ], None),
            ("AutoReact", [
                ",autoreact add <trigger> <emoji>",
                ",autoreact remove <trigger>",
                ",autoreact list",
                ",autoreact clear",
                ",autoreact test <trigger>",
            ], None),
            ("AutoGreet", [
                ",autogreet <#canal>",
                ",autogreet off",
                ",automsg <mensaje>",
            ], "Variables: `{user}` `{username}` `{server}` `{membercount}`"),
        ],
    },
    "integrations": {
        "label": "Integrations",
        "description": "Integración y búsquedas de Roblox.",
        "sections": [
            ("Roblox", [
                ",roblox",
                ",rblx",
                ",roblox user",
                ",roblox value",
                ",roblox presence",
                ",roblox avatar",
                ",roblox wearing",
                ",roblox friends",
                ",roblox inventory",
                ",roblox group",
                ",roblox groups",
                ",roblox game",
            ], "`,roblox value` usa un servicio no oficial (Rolimons) y puede fallar sin aviso."),
        ],
    },
    "antinuke": {
        "label": "AntiNuke",
        "description": "Motor de protección principal — activa, desactiva y ajusta cada módulo.",
        "sections": [
            ("AntiNuke", [
                ",antinuke enable",
                ",antinuke disable",
                ",antinuke status",
                ",antinuke punishment <ban|kick|strip|mute>",
                ",antinuke module <nombre>",
                ",antinuke module <nombre> <on|off>",
                ",antinuke threshold <módulo> <n>",
                ",antinuke window <módulo> <segundos>",
                ",antinuke accountage <días>",
                ",antinuke guildage <días>",
                ",antinuke reset",
            ], None),
            ("Módulos", [
                "ban", "kick", "channeldelete", "channelcreate", "roledelete", "rolecreate",
                "webhook", "mention", "emojidelete", "botadd", "everyone", "serverupdate", "prune", "roleperm",
            ], "Usa `,antinuke module <nombre>` (sin más nada) para abrir el panel de configuración de ese módulo: castigo, canal de logs y whitelist propios. O usa `,antinuke module <nombre> <on|off>` para activarlo/desactivarlo directo."),
        ],
    },
    "moderacion": {
        "label": "Moderación",
        "description": "Kicks, baneos, silencios, advertencias, purgas, cuarentena y bloqueo del servidor.",
        "sections": [
            ("Moderación", [
                ",kick <usuario> [razón]",
                ",ban <usuario> [días_borrado] [razón]",
                ",softban <usuario> [razón]",
                ",mute <usuario> <duración> [razón]",
                ",unmute <usuario> [razón]",
                ",warn <usuario> [razón]",
                ",warnings <usuario>",
                ",clearwarns <usuario>",
                ",delwarn <usuario> <índice>",
                ",purge <cantidad> [usuario]",
                ",lockchannel [#canal]",
                ",unlockchannel [#canal]",
                ",slowmode <segundos> [#canal]",
                ",nick <usuario> <apodo|reset>",
                ",role add <usuario> <rol>",
                ",role remove <usuario> <rol>",
                ",modlogs <usuario>",
            ], None),
            ("Jail", [
                ",setupjail",
                ",jail <usuario> [razón]",
                ",unjail <usuario> [razón]",
            ], None),
            ("Lockdown", [
                ",lockdown",
                ",unlock",
                ",lockdown exempt add <canal>",
                ",lockdown exempt remove <canal>",
                ",lockdown exempt list",
            ], None),
            ("Desbaneos", [
                ",unban <id_usuario> [razón]",
                ",unbanall",
            ], None),
        ],
    },
    "configuracion": {
        "label": "Configuración",
        "description": "Prefijo, canal de logs, apariencia de embeds y configuración rápida del bot.",
        "sections": [
            ("Ajustes", [
                ",setlogs [#canal]",
                ",setprefix <prefijo>",
                ",logembed color <hex>",
                ",logembed footer <texto>",
                ",logembed thumbnail <on|off>",
            ], None),
            ("Auto-Configuración", [
                ",setuplogs",
                ",autosetup normal",
                ",autosetup rapido",
            ], None),
        ],
    },
    "whitelist": {
        "label": "Whitelist",
        "description": "Usuarios completamente exentos de la detección AntiNuke.",
        "sections": [
            ("Whitelist", [
                ",whitelist",
                ",whitelist add <usuario>",
                ",whitelist remove <usuario>",
                ",whitelist clear",
                ",whitelist check <usuario>",
            ], None),
        ],
    },
    "voz": {
        "label": "Voz",
        "description": "Rastreo de actividad en canales de voz y canales temporales tipo Join-to-Create.",
        "sections": [
            ("VC Tracker", [
                ",setvc channel <#canal>",
                ",setvc threshold <n>",
                ",vcstats",
            ], None),
            ("Voz Temporal", [
                ",voiceset setup <categoría>",
                ",voiceset hub <#canal_voz>",
                ",voiceset off",
                ",voice rename <nombre>",
                ",voice limit <n>",
            ], "Al crear tu canal, el bot manda un panel con botones para bloquear, ocultar, reclamar y más."),
        ],
    },
    "bienvenidas": {
        "label": "Bienvenidas",
        "description": "Mensajes de bienvenida personalizados, con embeds, botones y variables.",
        "sections": [
            ("Bienvenidas", [
                ",welcome add <#canal> <config>",
                ",welcome list",
                ",welcome remove <n>",
                ",welcome test",
                ",welcome off",
            ], None),
        ],
    },
    "invitaciones": {
        "label": "Invitaciones",
        "description": "Rastrea cuántas invitaciones trae cada miembro y recompensa a los que más invitan.",
        "sections": [
            ("Invitaciones", [
                ",setinvite channel <#canal>",
                ",setinvite threshold <n> [recompensa]",
                ",setinvite altdays <días>",
                ",invites [usuario]",
                ",invitetop",
                ",resetinvites",
            ], None),
        ],
    },
    "giveaways": {
        "label": "Giveaways",
        "description": "Sorteos con botón de participación, bonus de probabilidad y reroll.",
        "sections": [
            ("Giveaways", [
                ",gcreate <#canal> <duración> <premio>",
                ",gend <id_mensaje>",
                ",greroll <id_mensaje>",
                ",gbonus <usuario> <porcentaje>",
                ",gbonus remove <usuario>",
                ",gbonus list",
            ], None),
        ],
    },
    "imagenes": {
        "label": "Reenvío de Imágenes",
        "description": "Manda links de fotos/gifs por DM al bot y elige con botones a cuál canal reenviarlos.",
        "sections": [
            ("Canales y Acceso", [
                ",addpostchannel <nombre> <#canal>",
                ",removepostchannel <nombre>",
                ",postchannels",
                ",posters add <usuario>",
                ",posters remove <usuario>",
                ",posters",
            ], None),
            ("Uso", [
                ",post <link1> <link2> ...",
                ",preview",
            ], None),
        ],
    },
    "autoresponder": {
        "label": "Autoresponders",
        "description": "Respuestas automáticas a palabras o frases exactas, en texto o embed.",
        "sections": [
            ("Autoresponders", [
                ",autoresponder add <trigger> | <respuesta>",
                ",autoresponder remove <trigger>",
                ",autoresponder list",
                ",autoresponder clear",
            ], None),
        ],
    },
    "embeds": {
        "label": "Embeds Personalizados",
        "description": "Crea y edita embeds con un motor de sintaxis simple, compatible con las bienvenidas.",
        "sections": [
            ("Embeds", [
                ",createembed <código>",
                ",editembed <link_mensaje> <código>",
            ], "Sintaxis: `{embed}$v{title: ...}$v{description: ...}$v{color: #hex}$v{field: nombre && valor && inline}`\nVariables: `{user.mention}` `{user.tag}` `{guild.name}` `{guild.count}` `{channel.mention}`"),
        ],
    },
    "freefire": {
        "label": "Free Fire",
        "description": "Búsqueda de jugadores de Free Fire por UID (API no oficial de comunidad).",
        "sections": [
            ("Free Fire", [
                ",ffinfo <uid> [region]",
                ",ffstats <uid> [region]",
                ",ffban <uid>",
            ], None),
        ],
    },
    "backup": {
        "label": "Respaldo",
        "description": "Copias de seguridad del servidor para restaurar canales y roles tras un ataque.",
        "sections": [
            ("Respaldo", [
                ",backup snapshot",
                ",backup restore",
                ",backup status",
            ], None),
        ],
    },
}

ALIASES = {
    "roblox": "integrations", "rblx": "integrations", "integrations": "integrations", "integraciones": "integrations",
    "autorole": "automation", "autoreact": "automation", "autogreet": "automation",
    "automation": "automation", "automatizacion": "automation", "automatización": "automation",
    "mod": "moderacion", "moderation": "moderacion", "moderación": "moderacion",
    "jail": "moderacion", "lockdown": "moderacion", "unban": "moderacion",
    "modules": "antinuke", "módulos": "antinuke", "modulos": "antinuke",
    "images": "imagenes", "imagedrop": "imagenes", "fotos": "imagenes",
    "log": "configuracion", "logs": "configuracion", "settings": "configuracion",
    "setup": "configuracion", "auto": "configuracion", "autoconfig": "configuracion", "autosetup": "configuracion",
    "vctracker": "voz", "voicechannel": "voz", "voice": "voz", "voicemaster": "voz",
    "welcome": "bienvenidas",
    "invites": "invitaciones", "invite": "invitaciones",
    "giveaway": "giveaways", "sorteos": "giveaways", "sorteo": "giveaways",
    "respaldo": "backup",
}


def _build_overview_embed(bot: discord.Client, prefix: str) -> discord.Embed:
    e = discord.Embed(
        description=(
            f"Usa `{prefix}help <comando>` para ayuda sobre un comando específico.\n"
            "Los parámetros en `<>` son obligatorios, `[]` son opcionales.\n"
            f"Únete al [servidor de soporte]({SUPPORT_SERVER_URL}) para más ayuda."
        ),
        color=0x2b2d31,
    )
    e.set_author(name=f"{bot.user.name} Help", icon_url=bot.user.display_avatar.url)
    e.set_thumbnail(url=BRAND_ICON_URL)
    e.set_footer(text=f"Selecciona una categoría desde el menú de abajo · {bot.user.name}")
    e.timestamp = discord.utils.utcnow()
    return e


def _build_category_embed(bot: discord.Client, cat_key: str) -> discord.Embed:
    data = CATEGORIES[cat_key]
    e = discord.Embed(title=data["label"], color=0x2b2d31)
    e.set_author(name=f"{bot.user.name} Help", icon_url=bot.user.display_avatar.url)
    e.set_thumbnail(url=BRAND_ICON_URL)

    parts = []
    for subheader, cmds, note in data["sections"]:
        block = "```\n" + "\n".join(cmds) + "\n```"
        parts.append(f"**{subheader}**\n{block}")
        if note:
            parts.append(note)
    e.description = "\n".join(parts)

    e.set_footer(text=f"Selecciona una categoría desde el menú de abajo · {bot.user.name}")
    e.timestamp = discord.utils.utcnow()
    return e


class CategorySelect(discord.ui.Select):
    def __init__(self, bot: discord.Client):
        self.bot = bot
        options = [
            discord.SelectOption(label=data["label"], value=key, description=data["description"][:100])
            for key, data in CATEGORIES.items()
        ]
        super().__init__(placeholder="Selecciona una categoría...", options=options)

    async def callback(self, interaction: discord.Interaction):
        embed = _build_category_embed(self.bot, self.values[0])
        await interaction.response.edit_message(embed=embed, view=self.view)


class HelpView(discord.ui.View):
    def __init__(self, bot: discord.Client):
        super().__init__(timeout=45)
        self.bot = bot
        self.message: discord.Message | None = None
        self.add_item(CategorySelect(bot))
        self.add_item(discord.ui.Button(label="Support Server", url=SUPPORT_SERVER_URL, style=discord.ButtonStyle.link))

    async def on_timeout(self):
        if self.message is None:
            return
        e = discord.Embed(description="Menú de ayuda expirado.", color=0x2b2d31)
        try:
            await self.message.edit(embed=e, view=None)
        except discord.HTTPException:
            pass


class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="help", aliases=["h", "commands"])
    async def help_command(self, ctx, *, category: str = None):
        """Muestra la ayuda general o de una categoría específica."""
        config = db.get_guild(ctx.guild.id)
        prefix = config.get("prefix", ",")

        if category is None:
            embed = _build_overview_embed(self.bot, prefix)
            view = HelpView(self.bot)
            view.message = await ctx.send(embed=embed, view=view)
            return

        cat_key = category.lower().strip()
        cat_key = ALIASES.get(cat_key, cat_key)

        if cat_key not in CATEGORIES:
            available = " · ".join(f"`{k}`" for k in CATEGORIES)
            e = discord.Embed(
                description=f"Categoría `{category}` no encontrada.\nDisponibles: {available}",
                color=0x2b2d31,
            )
            e.set_author(name=f"{self.bot.user.name} Help", icon_url=self.bot.user.display_avatar.url)
            return await ctx.send(embed=e)

        embed = _build_category_embed(self.bot, cat_key)
        view = HelpView(self.bot)
        view.message = await ctx.send(embed=embed, view=view)


async def setup(bot):
    await bot.add_cog(Help(bot))
