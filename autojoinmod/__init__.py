from .joinrole import JoinRole

async def setup(bot):
    """
    Sets up the JoinRole cog.
    """
    await bot.add_cog(JoinRole(bot))