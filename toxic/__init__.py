from .toxic import Toxic

__red_end_user_data_statement__ = (
    "This cog stores temporary data about active votes including the initiator, "
    "target, and reason. All data is automatically deleted when votes conclude."
)

async def setup(bot):
    await bot.add_cog(Toxic(bot))