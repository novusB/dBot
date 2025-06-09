# weathercog/__init__.py
# This file initializes the cog and registers it with the Red bot.

from .weathercog import WeatherCog # Import the main cog class from weathercog.py

async def setup(bot):
    """
    Sets up the WeatherCog when Red starts.
    This function is called by Red to load the cog.
    """
    await bot.add_cog(WeatherCog(bot))
    print("WeatherCog loaded successfully!") # Optional: for confirmation in console