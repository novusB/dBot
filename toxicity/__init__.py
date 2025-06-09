from .toxic import Toxic

__red_end_user_data_statement__ = (
    "This cog stores data about active votes including the initiator, "
    "target, and reason. No personal data is stored after votes are completed."
)

async def setup(bot):
    await bot.add_cog(Toxic(bot))