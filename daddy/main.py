from redbot.core import commands

class daddy(commands.Cog):
    """My custom cog"""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="daddy")
    async def mycom(self, ctx):
        """This does stuff!"""
        # Your code will go here
        await ctx.send("novusB is my daddy!")