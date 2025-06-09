from .main import Toxicity # Import the main cog class from main.py

async def setup(bot):
    """
    Sets up the Toxicity cog when Red starts.
    This function is called by Red to load the cog.
    """
    await bot.add_cog(Toxicity(bot))
    print("Toxicity cog loaded successfully!") # Optional: for confirmation in console