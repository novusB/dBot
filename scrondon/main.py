from redbot.core import commands

class scrondon(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="scrondon")
    async def mycom(self, ctx):
        await ctx.send("Airman Scrondon reporting for duty!")