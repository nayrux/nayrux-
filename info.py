import discord
from discord.ext import commands


class Info(commands.Cog):
    """Comandos de información del servidor y usuarios."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="userinfo", description="Muestra información de un usuario")
    async def userinfo(self, ctx: commands.Context, member: discord.Member = None):
        member = member or ctx.author
        embed = discord.Embed(
            title=f"Información de {member.display_name}",
            color=member.color,
            timestamp=ctx.message.created_at,
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="ID", value=member.id, inline=True)
        embed.add_field(name="Apodo", value=member.nick or "Ninguno", inline=True)
        embed.add_field(name="Se unió", value=discord.utils.format_dt(member.joined_at, style="R"), inline=True)
        embed.add_field(name="Cuenta creada", value=discord.utils.format_dt(member.created_at, style="R"), inline=True)
        roles = [role.mention for role in member.roles[1:]] or ["@everyone"]
        embed.add_field(name=f"Roles [{len(roles)}]", value=" ".join(roles), inline=False)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="serverinfo", description="Muestra información del servidor")
    async def serverinfo(self, ctx: commands.Context):
        guild = ctx.guild
        embed = discord.Embed(
            title=guild.name,
            color=0x2B2D31,
            timestamp=ctx.message.created_at,
        )
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        embed.add_field(name="ID", value=guild.id, inline=True)
        embed.add_field(name="Dueño", value=str(guild.owner), inline=True)
        embed.add_field(name="Miembros", value=guild.member_count, inline=True)
        embed.add_field(name="Canales", value=len(guild.channels), inline=True)
        embed.add_field(name="Roles", value=len(guild.roles), inline=True)
        embed.add_field(name="Boosts", value=guild.premium_subscription_count, inline=True)
        embed.add_field(name="Creado el", value=discord.utils.format_dt(guild.created_at, style="R"), inline=False)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="avatar", description="Muestra el avatar de un usuario")
    async def avatar(self, ctx: commands.Context, member: discord.Member = None):
        member = member or ctx.author
        embed = discord.Embed(
            title=f"Avatar de {member.display_name}",
            color=0x2B2D31,
        )
        embed.set_image(url=member.display_avatar.url)
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Info(bot))
