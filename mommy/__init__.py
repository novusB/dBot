from .main import mommy


async def setup(bot):
    await bot.add_cog(mommy(bot))