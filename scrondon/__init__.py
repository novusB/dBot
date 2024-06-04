from .main import scrondon


async def setup(bot):
    await bot.add_cog(scrondon(bot))