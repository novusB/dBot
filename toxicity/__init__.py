from .toxicity import Toxicity

async def setup(bot):
    """Set up the Toxicity cog."""
    cog = Toxicity(bot)
    await bot.add_cog(cog)

async def teardown(bot):
    """Clean up when the cog is unloaded."""
    cog = bot.get_cog("Toxicity")
    if cog:
        # Clean up any running tasks
        if hasattr(cog, 'cleanup_task') and cog.cleanup_task:
            cog.cleanup_task.cancel()