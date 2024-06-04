from redbot.core import commands

class daddy(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="mommy")
    async def mycom(self, ctx):
        await ctx.send("novusB loves mommies! Do you love mommies too?")