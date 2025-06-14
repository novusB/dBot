from .osrs_stats import OSRSStats

async def setup(bot):
    await bot.add_cog(OSRSStats(bot))