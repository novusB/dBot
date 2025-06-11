from .weathercog import WeatherCog

async def setup(bot):
    """Setup function for the enhanced WeatherCog"""
    cog = WeatherCog(bot)
    await bot.add_cog(cog)
    
    # Register slash commands
    try:
        synced = await bot.tree.sync()
        print(f"Enhanced WeatherCog loaded successfully! Synced {len(synced)} slash commands.")
    except Exception as e:
        print(f"Enhanced WeatherCog loaded, but failed to sync slash commands: {e}")