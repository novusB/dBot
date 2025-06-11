from .weathercog import WeatherCog

async def setup(bot):
    """
    Setup function for the Enhanced WeatherCog.
    This function is called by Red to load the cog with proper registration.
    """
    try:
        # Create the cog instance
        cog = WeatherCog(bot)
        
        # Force add the cog to ensure proper registration
        await bot.add_cog(cog)
        
        # Attempt to sync slash commands
        try:
            synced = await bot.tree.sync()
            print(f"✅ Enhanced WeatherCog loaded successfully!")
            print(f"📡 Synced {len(synced)} slash commands.")
            print(f"🔧 Config registered with unique identifier: 260288776360820736")
        except Exception as sync_error:
            print(f"✅ Enhanced WeatherCog loaded successfully!")
            print(f"⚠️  Failed to sync slash commands: {sync_error}")
            print(f"🔧 Config registered with unique identifier: 260288776360820736")
            
    except Exception as e:
        print(f"❌ Failed to load Enhanced WeatherCog: {e}")
        raise