from .viewroles import ViewRoles

async def setup(bot):
    await bot.add_cog(MyCog(bot))