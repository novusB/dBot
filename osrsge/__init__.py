from .osrs_ge import OSRSGE

async def setup(bot):
    cog = OSRSGE(bot)
    await bot.add_cog(cog)
    print("OSRS GE cog loaded successfully - Version 1.0.0")

async def teardown(bot):
    print("OSRS GE cog unloaded")