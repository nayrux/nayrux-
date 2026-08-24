"""
autoreact.py — El bot reacciona automáticamente a mensajes que contengan
una palabra o frase disparadora (trigger).

Comandos:
  ,autoreact add <trigger> <emoji> — agrega una reacción automática
  ,autoreact remove <trigger>      — quita una
  ,autoreact list                  — lista los triggers configurados
  ,autoreact clear                 — vacía todos los triggers
  ,autoreact test <trigger>        — prueba la reacción en tu propio mensaje
"""

import discord
from discord.ext import commands
from config import db
import logging

log = logging.getLogger("antinuke.autoreact")


def _get_autoreacts(guild_id: int) -> dict:
    config = db.get_guild(guild_id)
    return config.setdefault("autoreact", {})


def _save_autoreacts(guild_id: int, data: dict):
    config = db.get_guild(guild_id)
    config["autoreact"] = data
    db.update_guild(guild_id, config)


class AutoReact(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return

        config = db.get_guild(message.guild.id)
        prefix = config.get("prefix", ",")
        if message.content.startswith(prefix):
            return

        data = _get_autoreacts(message.guild.id)
        if not data:
            return

        content_lower = message.content.lower()
        for trigger, emoji in data.items():
            if trigger in content_lower:
                try:
                    await message.add_reaction(emoji)
                except discord.HTTPException:
                    pass
                except Exception as e:
                    log.error(f"[{message.guild.name}] Error en autoreact: {e}")

    @commands.group(name="autoreact", aliases=["ar2"], invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def autoreact(self, ctx: commands.Context):
        await ctx.send(embed=discord.Embed(
            description="Usa `,autoreact add <trigger> <emoji>`, `,autoreact remove <trigger>`, "
                        "`,autoreact list`, `,autoreact clear`, `,autoreact test <trigger>`.",
            color=0x2b2d31,
        ))

    @autoreact.command(name="add")
    @commands.has_permissions(manage_guild=True)
    async def autoreact_add(self, ctx: commands.Context, trigger: str, emoji: str):
        trigger = trigger.lower().strip()
        test_msg = await ctx.send("Probando el emoji...")
        try:
            await test_msg.add_reaction(emoji)
        except discord.HTTPException:
            await test_msg.edit(content="Ese emoji no es válido o el bot no puede usarlo.")
            return

        data = _get_autoreacts(ctx.guild.id)
        data[trigger] = emoji
        _save_autoreacts(ctx.guild.id, data)
        await test_msg.edit(content=None, embed=discord.Embed(
            description=f"Cuando alguien mencione `{trigger}`, reaccionaré con {emoji}.",
            color=0x57f287,
        ))

    @autoreact.command(name="remove")
    @commands.has_permissions(manage_guild=True)
    async def autoreact_remove(self, ctx: commands.Context, *, trigger: str):
        trigger = trigger.lower().strip()
        data = _get_autoreacts(ctx.guild.id)
        if trigger not in data:
            return await ctx.send(embed=discord.Embed(description="Ese trigger no existe.", color=0xed4245))
        del data[trigger]
        _save_autoreacts(ctx.guild.id, data)
        await ctx.send(embed=discord.Embed(description=f"Trigger `{trigger}` eliminado.", color=0xed4245))

    @autoreact.command(name="list")
    @commands.has_permissions(manage_guild=True)
    async def autoreact_list(self, ctx: commands.Context):
        data = _get_autoreacts(ctx.guild.id)
        if not data:
            return await ctx.send(embed=discord.Embed(description="No hay autoreacts configurados.", color=0x2b2d31))
        lines = [f"`{trigger}` → {emoji}" for trigger, emoji in data.items()]
        await ctx.send(embed=discord.Embed(title="AutoReact", description="\n".join(lines), color=0x2b2d31))

    @autoreact.command(name="clear")
    @commands.has_permissions(manage_guild=True)
    async def autoreact_clear(self, ctx: commands.Context):
        _save_autoreacts(ctx.guild.id, {})
        await ctx.send(embed=discord.Embed(description="Todos los autoreacts fueron eliminados.", color=0xed4245))

    @autoreact.command(name="test")
    @commands.has_permissions(manage_guild=True)
    async def autoreact_test(self, ctx: commands.Context, *, trigger: str):
        trigger = trigger.lower().strip()
        data = _get_autoreacts(ctx.guild.id)
        emoji = data.get(trigger)
        if not emoji:
            return await ctx.send(embed=discord.Embed(description="Ese trigger no existe.", color=0xed4245))
        try:
            await ctx.message.add_reaction(emoji)
        except discord.HTTPException:
            await ctx.send(embed=discord.Embed(description="No pude reaccionar con ese emoji.", color=0xed4245))


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoReact(bot))
