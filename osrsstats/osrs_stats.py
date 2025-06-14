import aiohttp
import discord
from redbot.core import commands, Config
from redbot.core.bot import Red
from typing import Optional
import asyncio

class OSRSStats(commands.Cog):
    """A cog to fetch and display Old School RuneScape player statistics."""
    
    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=7829463051)
        self.session = aiohttp.ClientSession()
        
        # OSRS Skills mapping
        self.skills = [
            "Overall", "Attack", "Defence", "Strength", "Hitpoints", "Ranged", "Prayer",
            "Magic", "Cooking", "Woodcutting", "Fletching", "Fishing", "Firemaking",
            "Crafting", "Smithing", "Mining", "Herblore", "Agility", "Thieving",
            "Slayer", "Farming", "Runecraft", "Hunter", "Construction"
        ]
        
        # OSRS Activities mapping (minigames, bosses, etc.)
        self.activities = [
            "League Points", "Bounty Hunter - Hunter", "Bounty Hunter - Rogue",
            "Clue Scrolls (all)", "Clue Scrolls (beginner)", "Clue Scrolls (easy)",
            "Clue Scrolls (medium)", "Clue Scrolls (hard)", "Clue Scrolls (elite)",
            "Clue Scrolls (master)", "LMS - Rank", "Soul Wars Zeal", "Rifts closed",
            "Abyssal Sire", "Alchemical Hydra", "Barrows Chests", "Bryophyta",
            "Callisto", "Cerberus", "Chambers of Xeric", "Chambers of Xeric: Challenge Mode",
            "Chaos Elemental", "Chaos Fanatic", "Commander Zilyana", "Corporeal Beast",
            "Crazy Archaeologist", "Dagannoth Prime", "Dagannoth Rex", "Dagannoth Supreme",
            "Deranged Archaeologist", "General Graardor", "Giant Mole", "Grotesque Guardians",
            "Hespori", "Kalphite Queen", "King Black Dragon", "Kraken", "Kree'Arra",
            "K'ril Tsutsaroth", "Mimic", "Nex", "Nightmare", "Phosani's Nightmare",
            "Obor", "Sarachnis", "Scorpia", "Skotizo", "Tempoross", "The Gauntlet",
            "The Corrupted Gauntlet", "Theatre of Blood", "Theatre of Blood: Hard Mode",
            "Thermonuclear Smoke Devil", "TzKal-Zuk", "TzTok-Jad", "Venenatis",
            "Vet'ion", "Vorkath", "Wintertodt", "Zalcano", "Zulrah"
        ]

    def cog_unload(self):
        asyncio.create_task(self.session.close())

    async def fetch_player_stats(self, username: str) -> Optional[dict]:
        """Fetch player stats from OSRS Hiscores API."""
        url = f"https://secure.runescape.com/m=hiscore_oldschool/index_lite.ws?player={username}"
        
        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.text()
                    return self.parse_hiscores_data(data)
                elif response.status == 404:
                    return None
                else:
                    return None
        except Exception as e:
            print(f"Error fetching stats: {e}")
            return None

    def parse_hiscores_data(self, data: str) -> dict:
        """Parse the hiscores data into a structured format."""
        lines = data.strip().split('\n')
        parsed_data = {"skills": {}, "activities": {}}
        
        # Parse skills (first 24 lines)
        for i, line in enumerate(lines[:24]):
            parts = line.split(',')
            if len(parts) >= 3:
                rank = int(parts[0]) if parts[0] != '-1' else None
                level = int(parts[1]) if parts[1] != '-1' else 1
                xp = int(parts[2]) if parts[2] != '-1' else 0
                
                parsed_data["skills"][self.skills[i]] = {
                    "rank": rank,
                    "level": level,
                    "xp": xp
                }
        
        # Parse activities (remaining lines)
        for i, line in enumerate(lines[24:]):
            if i < len(self.activities):
                parts = line.split(',')
                if len(parts) >= 2:
                    rank = int(parts[0]) if parts[0] != '-1' else None
                    score = int(parts[1]) if parts[1] != '-1' else 0
                    
                    parsed_data["activities"][self.activities[i]] = {
                        "rank": rank,
                        "score": score
                    }
        
        return parsed_data

    def format_number(self, num: int) -> str:
        """Format large numbers with commas."""
        return f"{num:,}"

    def create_stats_embed(self, username: str, stats: dict) -> discord.Embed:
        """Create a Discord embed with player stats."""
        embed = discord.Embed(
            title=f"🗡️ OSRS Stats for {username}",
            color=0x8B4513,  # Brown color for OSRS theme
            url=f"https://secure.runescape.com/m=hiscore_oldschool/hiscorepersonal?user1={username}"
        )
        
        # Overall stats
        overall = stats["skills"]["Overall"]
        embed.add_field(
            name="📊 Overall",
            value=f"**Level:** {overall['level']}\n**XP:** {self.format_number(overall['xp'])}\n**Rank:** {self.format_number(overall['rank']) if overall['rank'] else 'Unranked'}",
            inline=True
        )
        
        # Combat stats
        combat_skills = ["Attack", "Strength", "Defence", "Hitpoints", "Ranged", "Prayer", "Magic"]
        combat_text = ""
        for skill in combat_skills:
            if skill in stats["skills"]:
                level = stats["skills"][skill]["level"]
                combat_text += f"**{skill}:** {level}\n"
        
        embed.add_field(
            name="⚔️ Combat Stats",
            value=combat_text,
            inline=True
        )
        
        # Popular activities
        popular_activities = ["Clue Scrolls (all)", "Barrows Chests", "Zulrah", "Vorkath", "Chambers of Xeric"]
        activities_text = ""
        for activity in popular_activities:
            if activity in stats["activities"] and stats["activities"][activity]["score"] > 0:
                score = stats["activities"][activity]["score"]
                activities_text += f"**{activity}:** {self.format_number(score)}\n"
        
        if activities_text:
            embed.add_field(
                name="🏆 Notable Activities",
                value=activities_text,
                inline=False
            )
        
        # Total level calculation
        total_level = sum(skill_data["level"] for skill_data in stats["skills"].values() if skill_data["level"] > 1)
        embed.add_field(
            name="📈 Total Level",
            value=f"**{total_level}**",
            inline=True
        )
        
        embed.set_footer(text="Data from OSRS Hiscores")
        return embed

    @commands.command(name="osrs", aliases=["osrsstats", "rs"])
    async def osrs_stats(self, ctx, *, username: str):
        """
        Fetch and display OSRS player statistics.
        
        Usage: !osrs <username>
        Example: !osrs Zezima
        """
        # Clean username (remove spaces, convert to proper format)
        username = username.strip().replace(' ', '_')
        
        async with ctx.typing():
            stats = await self.fetch_player_stats(username)
            
            if stats is None:
                embed = discord.Embed(
                    title="❌ Player Not Found",
                    description=f"Could not find player '{username}' on the OSRS Hiscores.\n\nMake sure the username is correct and the player has logged in recently.",
                    color=0xFF0000
                )
                await ctx.send(embed=embed)
                return
            
            embed = self.create_stats_embed(username, stats)
            await ctx.send(embed=embed)

    @commands.command(name="osrsskill")
    async def osrs_skill(self, ctx, username: str, skill: str):
        """
        Get detailed information about a specific skill.
        
        Usage: !osrsskill <username> <skill>
        Example: !osrsskill Zezima woodcutting
        """
        username = username.strip().replace(' ', '_')
        skill = skill.lower().capitalize()
        
        # Handle special cases
        skill_mapping = {
            "Hp": "Hitpoints",
            "Wc": "Woodcutting",
            "Fm": "Firemaking",
            "Rc": "Runecraft"
        }
        skill = skill_mapping.get(skill, skill)
        
        async with ctx.typing():
            stats = await self.fetch_player_stats(username)
            
            if stats is None:
                embed = discord.Embed(
                    title="❌ Player Not Found",
                    description=f"Could not find player '{username}' on the OSRS Hiscores.",
                    color=0xFF0000
                )
                await ctx.send(embed=embed)
                return
            
            if skill not in stats["skills"]:
                available_skills = ", ".join(self.skills[1:])  # Exclude "Overall"
                embed = discord.Embed(
                    title="❌ Invalid Skill",
                    description=f"'{skill}' is not a valid skill.\n\n**Available skills:**\n{available_skills}",
                    color=0xFF0000
                )
                await ctx.send(embed=embed)
                return
            
            skill_data = stats["skills"][skill]
            embed = discord.Embed(
                title=f"🎯 {skill} Stats for {username}",
                color=0x8B4513
            )
            
            embed.add_field(
                name="Level",
                value=f"**{skill_data['level']}**",
                inline=True
            )
            
            embed.add_field(
                name="Experience",
                value=f"**{self.format_number(skill_data['xp'])}**",
                inline=True
            )
            
            embed.add_field(
                name="Rank",
                value=f"**{self.format_number(skill_data['rank']) if skill_data['rank'] else 'Unranked'}**",
                inline=True
            )
            
            # Calculate XP to next level (simplified calculation)
            if skill_data['level'] < 99:
                xp_table = [0, 83, 174, 276, 388, 512, 650, 801, 969, 1154, 1358, 1584, 1833, 2107, 2411, 2746, 3115, 3523, 3973, 4470, 5018, 5624, 6291, 7028, 7842, 8740, 9730, 10824, 12031, 13363, 14833, 16456, 18247, 20224, 22406, 24815, 27473, 30408, 33648, 37224, 41171, 45529, 50339, 55649, 61512, 67983, 75127, 83014, 91721, 101333, 111945, 123660, 136594, 150872, 166636, 184040, 203254, 224466, 247886, 273742, 302288, 333804, 368599, 407015, 449428, 496254, 547953, 605032, 668051, 737627, 814445, 899257, 992895, 1096278, 1210421, 1336443, 1475581, 1629200, 1798808, 1986068, 2192818, 2421087, 2673114, 2951373, 3258594, 3597792, 3972294, 4385776, 4842295, 5346332, 5902831, 6517253, 7195629, 7944614, 8771558, 9684577, 10692629, 11805606, 13034431]
                if skill_data['level'] < len(xp_table):
                    xp_needed = xp_table[skill_data['level']] - skill_data['xp']
                    embed.add_field(
                        name="XP to Next Level",
                        value=f"**{self.format_number(xp_needed)}**",
                        inline=False
                    )
            
            await ctx.send(embed=embed)

def setup(bot: Red):
    bot.add_cog(OSRSStats(bot))