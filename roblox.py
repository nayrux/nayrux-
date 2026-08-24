"""
roblox.py — Búsqueda e información de jugadores de Roblox.

Usa la API pública OFICIAL de Roblox (users.roblox.com, friends.roblox.com,
thumbnails.roblox.com, presence.roblox.com, avatar.roblox.com,
groups.roblox.com, games.roblox.com, inventory.roblox.com) — no requiere
API key.

Excepción: ,roblox value usa la API NO OFICIAL de Rolimons (rolimons.com)
para estimar el valor de la cuenta; puede fallar o dejar de funcionar sin
aviso porque no es un servicio de Roblox.

Nota: desde agosto 2026, Roblox dejó de devolver la descripción del perfil
en su API pública por cumplimiento regional — puede aparecer vacía.

Comandos:
  ,roblox <usuario>  /  ,roblox user <usuario> — perfil completo
  ,roblox value <usuario>            — valor estimado de la cuenta (no oficial)
  ,roblox presence <usuario>         — estado en línea / en qué juego está
  ,roblox avatar <usuario>           — imagen del avatar completo
  ,roblox wearing <usuario>          — lo que trae puesto ahora mismo
  ,roblox friends <usuario>          — cantidad y lista de amigos
  ,roblox inventory <usuario>        — coleccionables públicos
  ,roblox group <usuario> <id_grupo> — rol del usuario en ese grupo
  ,roblox groups <usuario>           — todos los grupos del usuario
  ,roblox game <place_id>            — información de un juego/experiencia
"""

import discord
from discord.ext import commands
import aiohttp
import logging
from datetime import datetime, timezone

log = logging.getLogger("antinuke.roblox")

HEADERS = {"User-Agent": "Mozilla/5.0"}
PRESENCE_LABELS = {0: "Offline", 1: "En línea", 2: "En un juego", 3: "En Roblox Studio"}


async def _post(url: str, json_body: dict) -> dict | None:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=json_body, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return {"__error__": f"http_{resp.status}"}
                return await resp.json()
    except Exception as e:
        log.error(f"Roblox API error (POST {url}): {e}")
        return {"__error__": "network"}


async def _get(url: str, params: dict = None) -> dict | list | None:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 404:
                    return {"__error__": "not_found"}
                if resp.status != 200:
                    return {"__error__": f"http_{resp.status}"}
                return await resp.json()
    except Exception as e:
        log.error(f"Roblox API error (GET {url}): {e}")
        return {"__error__": "network"}


def _has_error(data) -> bool:
    return data is None or (isinstance(data, dict) and "__error__" in data)


def _err(data) -> str:
    return data.get("__error__", "unknown") if isinstance(data, dict) else "unknown"


def _error_embed(error: str) -> discord.Embed:
    messages = {
        "not_found": "No encontré ningún jugador con ese nombre de usuario.",
        "network": "No se pudo conectar con la API de Roblox ahora mismo. Intenta de nuevo en un rato.",
    }
    text = messages.get(error, f"Error de la API: `{error}`")
    return discord.Embed(description=text, color=0xed4245)


async def _resolve_user(username: str) -> dict | None:
    """username -> {'id', 'name', 'displayName'} o {'__error__': ...}"""
    data = await _post(
        "https://users.roblox.com/v1/usernames/users",
        {"usernames": [username], "excludeBannedUsers": False},
    )
    if _has_error(data):
        return data
    results = data.get("data", [])
    if not results:
        return {"__error__": "not_found"}
    return results[0]


def _format_created(created_iso: str) -> str:
    try:
        dt = datetime.fromisoformat(created_iso.replace("Z", "+00:00"))
        years = (datetime.now(timezone.utc) - dt).days // 365
        base = dt.strftime("%d/%m/%Y")
        return f"{base} (hace {years} años)" if years > 0 else base
    except Exception:
        return created_iso


async def _fetch_thumbnail(user_id: int, endpoint: str) -> str | None:
    data = await _get(
        f"https://thumbnails.roblox.com/v1/users/{endpoint}",
        {"userIds": user_id, "size": "420x420", "format": "Png", "isCircular": "false"},
    )
    if _has_error(data):
        return None
    items = data.get("data", [])
    if items and items[0].get("state") == "Completed":
        return items[0]["imageUrl"]
    return None


class Roblox(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.group(name="roblox", aliases=["rblx"], invoke_without_command=True)
    async def roblox(self, ctx: commands.Context, *, username: str = None):
        if username is None:
            return await ctx.send(embed=discord.Embed(
                description="Usa `,roblox <usuario>` o cualquiera de sus subcomandos: "
                            "`user`, `value`, `presence`, `avatar`, `wearing`, `friends`, "
                            "`inventory`, `group`, `groups`, `game`.",
                color=0x2b2d31,
            ))
        await self._send_profile(ctx, username)

    @roblox.command(name="user")
    async def roblox_user(self, ctx: commands.Context, *, username: str):
        await self._send_profile(ctx, username)

    async def _send_profile(self, ctx: commands.Context, username: str):
        user = await _resolve_user(username)
        if _has_error(user):
            return await ctx.send(embed=_error_embed(_err(user)))
        user_id = user["id"]

        details = await _get(f"https://users.roblox.com/v1/users/{user_id}")
        friends_c = await _get(f"https://friends.roblox.com/v1/users/{user_id}/friends/count")
        followers_c = await _get(f"https://friends.roblox.com/v1/users/{user_id}/followers/count")
        following_c = await _get(f"https://friends.roblox.com/v1/users/{user_id}/followings/count")
        presence = await _post("https://presence.roblox.com/v1/presence/users", {"userIds": [user_id]})
        headshot_url = await _fetch_thumbnail(user_id, "avatar-headshot")
        avatar_url = await _fetch_thumbnail(user_id, "avatar")

        if _has_error(details):
            details = {}

        display_name = user.get("displayName") or details.get("displayName") or user.get("name")
        username_real = user.get("name")
        description = (details.get("description") or "").strip()
        created = details.get("created")

        presence_type = 0
        location = None
        if not _has_error(presence):
            presences = presence.get("userPresences", [])
            if presences:
                presence_type = presences[0].get("userPresenceType", 0)
                location = presences[0].get("lastLocation")

        embed = discord.Embed(title=display_name, color=0x2b2d31)
        lines = [f"@{username_real} - ID: `{user_id}`"]

        if not _has_error(friends_c) and not _has_error(followers_c) and not _has_error(following_c):
            lines.append(
                f"{friends_c.get('count', '—')} amigos - "
                f"{followers_c.get('count', '—')} seguidores - "
                f"{following_c.get('count', '—')} siguiendo"
            )

        status_line = f"**{PRESENCE_LABELS.get(presence_type, 'Offline')}**"
        if location and presence_type == 2:
            status_line += f" — {location}"
        lines.append(status_line)

        lines.append(description if description else "Sin descripción.")
        if created:
            lines.append(f"Creado {_format_created(created)}")

        embed.description = "\n".join(lines)
        if headshot_url:
            embed.set_thumbnail(url=headshot_url)

        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="Profile", url=f"https://www.roblox.com/users/{user_id}/profile", style=discord.ButtonStyle.link))
        view.add_item(discord.ui.Button(label="Headshot", url=headshot_url or f"https://www.roblox.com/users/{user_id}/profile", style=discord.ButtonStyle.link))
        view.add_item(discord.ui.Button(label="Avatar", url=avatar_url or f"https://www.roblox.com/users/{user_id}/profile", style=discord.ButtonStyle.link))
        view.add_item(discord.ui.Button(label="Friends", url=f"https://www.roblox.com/users/{user_id}/friends", style=discord.ButtonStyle.link))

        await ctx.send(embed=embed, view=view)

    @roblox.command(name="value")
    async def roblox_value(self, ctx: commands.Context, *, username: str):
        user = await _resolve_user(username)
        if _has_error(user):
            return await ctx.send(embed=_error_embed(_err(user)))
        user_id = user["id"]

        data = await _get(f"https://api.rolimons.com/players/v1/playerassets/{user_id}")
        if _has_error(data) or not data.get("success", True):
            return await ctx.send(embed=discord.Embed(
                description="No pude obtener el valor de la cuenta (servicio no oficial de Rolimons no disponible ahora mismo).",
                color=0xed4245,
            ))

        assets = data.get("playerAssets", {})
        total_rap = sum(item[1] for item in assets.values() if isinstance(item, list) and len(item) > 1)

        embed = discord.Embed(
            title=f"Valor estimado — {user.get('name')}",
            description=f"**RAP total:** {total_rap:,} Robux\n**Objetos limitados:** {len(assets)}",
            color=0x2b2d31,
        )
        embed.set_footer(text="Estimación vía Rolimons (no oficial de Roblox) · puede no ser exacta")
        await ctx.send(embed=embed)

    @roblox.command(name="presence")
    async def roblox_presence(self, ctx: commands.Context, *, username: str):
        user = await _resolve_user(username)
        if _has_error(user):
            return await ctx.send(embed=_error_embed(_err(user)))
        user_id = user["id"]

        presence = await _post("https://presence.roblox.com/v1/presence/users", {"userIds": [user_id]})
        if _has_error(presence):
            return await ctx.send(embed=_error_embed(_err(presence)))

        p = (presence.get("userPresences") or [{}])[0]
        presence_type = p.get("userPresenceType", 0)

        embed = discord.Embed(
            title=f"Presencia — {user.get('name')}",
            description=f"**Estado:** {PRESENCE_LABELS.get(presence_type, 'Offline')}",
            color=0x2b2d31,
        )
        if presence_type == 2:
            if p.get("lastLocation"):
                embed.add_field(name="Jugando", value=p["lastLocation"], inline=False)
            if p.get("placeId"):
                embed.add_field(name="Place ID", value=str(p["placeId"]), inline=True)
        await ctx.send(embed=embed)

    @roblox.command(name="avatar")
    async def roblox_avatar(self, ctx: commands.Context, *, username: str):
        user = await _resolve_user(username)
        if _has_error(user):
            return await ctx.send(embed=_error_embed(_err(user)))
        user_id = user["id"]

        avatar_url = await _fetch_thumbnail(user_id, "avatar")
        if not avatar_url:
            return await ctx.send(embed=discord.Embed(description="No pude obtener el avatar.", color=0xed4245))

        embed = discord.Embed(title=f"Avatar — {user.get('name')}", color=0x2b2d31)
        embed.set_image(url=avatar_url)
        await ctx.send(embed=embed)

    @roblox.command(name="wearing")
    async def roblox_wearing(self, ctx: commands.Context, *, username: str):
        user = await _resolve_user(username)
        if _has_error(user):
            return await ctx.send(embed=_error_embed(_err(user)))
        user_id = user["id"]

        wearing = await _get(f"https://avatar.roblox.com/v1/users/{user_id}/currently-wearing")
        if _has_error(wearing):
            return await ctx.send(embed=_error_embed(_err(wearing)))

        asset_ids = wearing.get("assetIds", [])
        embed = discord.Embed(
            title=f"Trae puesto — {user.get('name')}",
            description=f"{len(asset_ids)} objetos equipados." if asset_ids else "No trae nada equipado (o es privado).",
            color=0x2b2d31,
        )
        avatar_url = await _fetch_thumbnail(user_id, "avatar")
        if avatar_url:
            embed.set_image(url=avatar_url)
        await ctx.send(embed=embed)

    @roblox.command(name="friends")
    async def roblox_friends(self, ctx: commands.Context, *, username: str):
        user = await _resolve_user(username)
        if _has_error(user):
            return await ctx.send(embed=_error_embed(_err(user)))
        user_id = user["id"]

        friends = await _get(f"https://friends.roblox.com/v1/users/{user_id}/friends")
        if _has_error(friends):
            return await ctx.send(embed=_error_embed(_err(friends)))

        data = friends.get("data", [])
        preview = ", ".join(f["name"] for f in data[:15])
        embed = discord.Embed(
            title=f"Amigos — {user.get('name')}",
            description=f"**Total:** {len(data)}\n\n{preview or 'Sin amigos.'}" + (" ..." if len(data) > 15 else ""),
            color=0x2b2d31,
        )
        await ctx.send(embed=embed)

    @roblox.command(name="inventory")
    async def roblox_inventory(self, ctx: commands.Context, *, username: str):
        user = await _resolve_user(username)
        if _has_error(user):
            return await ctx.send(embed=_error_embed(_err(user)))
        user_id = user["id"]

        inv = await _get(
            f"https://inventory.roblox.com/v1/users/{user_id}/assets/collectibles",
            {"limit": 100, "sortOrder": "Desc"},
        )
        if _has_error(inv):
            return await ctx.send(embed=discord.Embed(
                description="No pude leer el inventario. Es probable que sea privado (la mayoría de los usuarios lo tienen así).",
                color=0xed4245,
            ))

        items = inv.get("data", [])
        if not items:
            return await ctx.send(embed=discord.Embed(description="Inventario vacío o privado.", color=0x2b2d31))

        preview = "\n".join(f"• {i.get('name', 'Item')}" for i in items[:15])
        embed = discord.Embed(
            title=f"Coleccionables — {user.get('name')}",
            description=f"**Total:** {len(items)}\n\n{preview}" + ("\n..." if len(items) > 15 else ""),
            color=0x2b2d31,
        )
        embed.set_footer(text="Solo objetos limitados/coleccionables públicos")
        await ctx.send(embed=embed)

    @roblox.command(name="group")
    async def roblox_group(self, ctx: commands.Context, username: str, group_id: int):
        user = await _resolve_user(username)
        if _has_error(user):
            return await ctx.send(embed=_error_embed(_err(user)))
        user_id = user["id"]

        roles = await _get(f"https://groups.roblox.com/v2/users/{user_id}/groups/roles")
        if _has_error(roles):
            return await ctx.send(embed=_error_embed(_err(roles)))

        match = next((g for g in roles.get("data", []) if g["group"]["id"] == group_id), None)
        if not match:
            return await ctx.send(embed=discord.Embed(
                description=f"{user.get('name')} no pertenece a ese grupo.",
                color=0xed4245,
            ))

        embed = discord.Embed(
            title=match["group"]["name"],
            description=f"**Usuario:** {user.get('name')}\n**Rol:** {match['role']['name']}",
            color=0x2b2d31,
        )
        await ctx.send(embed=embed)

    @roblox.command(name="groups")
    async def roblox_groups(self, ctx: commands.Context, *, username: str):
        user = await _resolve_user(username)
        if _has_error(user):
            return await ctx.send(embed=_error_embed(_err(user)))
        user_id = user["id"]

        roles = await _get(f"https://groups.roblox.com/v2/users/{user_id}/groups/roles")
        if _has_error(roles):
            return await ctx.send(embed=_error_embed(_err(roles)))

        data = roles.get("data", [])
        if not data:
            return await ctx.send(embed=discord.Embed(description="Ese usuario no está en ningún grupo.", color=0x2b2d31))

        lines = [f"**{g['group']['name']}** — {g['role']['name']}" for g in data[:20]]
        embed = discord.Embed(
            title=f"Grupos — {user.get('name')}",
            description="\n".join(lines) + ("\n..." if len(data) > 20 else ""),
            color=0x2b2d31,
        )
        await ctx.send(embed=embed)

    @roblox.command(name="game")
    async def roblox_game(self, ctx: commands.Context, place_id: int):
        details = await _get(
            "https://games.roblox.com/v1/games/multiget-place-details",
            {"placeIds": place_id},
        )
        if _has_error(details) or not isinstance(details, list) or not details:
            return await ctx.send(embed=discord.Embed(description="No encontré ningún juego con ese Place ID.", color=0xed4245))

        universe_id = details[0].get("universeId")
        if not universe_id:
            return await ctx.send(embed=discord.Embed(description="No pude resolver ese juego.", color=0xed4245))

        game_data = await _get("https://games.roblox.com/v1/games", {"universeIds": universe_id})
        if _has_error(game_data) or not game_data.get("data"):
            return await ctx.send(embed=discord.Embed(description="No pude obtener información del juego.", color=0xed4245))

        g = game_data["data"][0]
        embed = discord.Embed(
            title=g.get("name", "Juego"),
            description=(g.get("description") or "Sin descripción.")[:500],
            color=0x2b2d31,
        )
        embed.add_field(name="Jugando ahora", value=f"{g.get('playing', 0):,}", inline=True)
        embed.add_field(name="Visitas totales", value=f"{g.get('visits', 0):,}", inline=True)
        embed.add_field(name="Favoritos", value=f"{g.get('favoritedCount', 0):,}", inline=True)
        if g.get("creator"):
            embed.add_field(name="Creador", value=g["creator"].get("name", "—"), inline=True)

        thumb = await _get("https://thumbnails.roblox.com/v1/games/icons", {"universeIds": universe_id, "size": "512x512", "format": "Png"})
        if not _has_error(thumb) and thumb.get("data"):
            embed.set_thumbnail(url=thumb["data"][0]["imageUrl"])

        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Roblox(bot))
