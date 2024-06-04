from .main import daddy


async def setup(bot):
    await bot.add_cog(daddy(bot))