from .main import Toxic # Import the main cog class from main.py

async def setup(bot):
    """
    Sets up the Toxic cog when Red starts.
    This function is called by Red to load the cog.
    """
    await bot.add_cog(Toxic(bot))
    print("Toxic cog loaded successfully!") # Optional: for confirmation in console