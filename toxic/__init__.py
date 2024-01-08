from .main import Toxic


async def setup(bot):
    await bot.add_cog(Toxic(bot))