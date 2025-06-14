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
        
        # OSRS Skills mapping (exact order from hiscores API)
        self.skills = [
            "Overall", "Attack", "Defence", "Strength", "Hitpoints", "Ranged", "Prayer",
            "Magic", "Cooking", "Woodcutting", "Fletching", "Fishing", "Firemaking",
            "Crafting", "Smithing", "Mining", "Herblore", "Agility", "Thieving",
            "Slayer", "Farming", "Runecraft", "Hunter", "Construction"
        ]
        
        # OSRS Activities mapping (exact order from hiscores API)
        self.activities = [
            "League Points", "Bounty Hunter - Hunter", "Bounty Hunter - Rogue",
            "Bounty Hunter (Legacy) - Hunter", "Bounty Hunter (Legacy) - Rogue",
            "Clue Scrolls (all)", "Clue Scrolls (beginner)", "Clue Scrolls (easy)",
            "Clue Scrolls (medium)", "Clue Scrolls (hard)", "Clue Scrolls (elite)",
            "Clue Scrolls (master)", "LMS - Rank", "PvP Arena - Rank", "Soul Wars Zeal",
            "Rifts closed", "Colosseum Glory", "Abyssal Sire", "Alchemical Hydra",
            "Artio", "Barrows Chests", "Bryophyta", "Callisto", "Cal'varion", "Cerberus",
            "Chambers of Xeric", "Chambers of Xeric: Challenge Mode", "Chaos Elemental",
            "Chaos Fanatic", "Commander Zilyana", "Corporeal Beast", "Crazy Archaeologist",
            "Dagannoth Prime", "Dagannoth Rex", "Dagannoth Supreme", "Deranged Archaeologist",
            "Duke Sucellus", "General Graardor", "Giant Mole", "Grotesque Guardians",
            "Hespori", "Kalphite Queen", "King Black Dragon", "Kraken", "Kree'Arra",
            "K'ril Tsutsaroth", "Leviathan", "Mimic", "Nex", "Nightmare", "Phosani's Nightmare",
            "Obor", "Phantom Muspah", "Sarachnis", "Scorpia", "Scurrius", "Skotizo",
            "Spindel", "Tempoross", "The Gauntlet", "The Corrupted Gauntlet", "The Leviathan",
            "The Whisperer", "Theatre of Blood", "Theatre of Blood: Hard Mode",
            "Thermonuclear Smoke Devil", "Tombs of Amascut", "Tombs of Amascut: Expert Mode",
            "TzKal-Zuk", "TzTok-Jad", "Vardorvis", "Venenatis", "Vet'ion", "Vorkath",
            "Wintertodt", "Zalcano", "Zulrah"
        ]

        # Exact XP table for all levels 1-99
        self.xp_table = [
            0, 83, 174, 276, 388, 512, 650, 801, 969, 1154, 1358, 1584, 1833, 2107, 2411, 2746,
            3115, 3523, 3973, 4470, 5018, 5624, 6291, 7028, 7842, 8740, 9730, 10824, 12031, 13363,
            14833, 16456, 18247, 20224, 22406, 24815, 27473, 30408, 33648, 37224, 41171, 45529,
            50339, 55649, 61512, 67983, 75127, 83014, 91721, 101333, 111945, 123660, 136594,
            150872, 166636, 184040, 203254, 224466, 247886, 273742, 302288, 333804, 368599,
            407015, 449428, 496254, 547953, 605032, 668051, 737627, 814445, 899257, 992895,
            1096278, 1210421, 1336443, 1475581, 1629200, 1798808, 1986068, 2192818, 2421087,
            2673114, 2951373, 3258594, 3597792, 3972294, 4385776, 4842295, 5346332, 5902831,
            6517253, 7195629, 7944614, 8771558, 9684577, 10692629, 11805606, 13034431
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
            if i < len(self.skills):
                parts = line.split(',')
                if len(parts) >= 3:
                    rank = int(parts[0]) if parts[0] != '-1' else None
                    level = int(parts[1]) if parts[1] != '-1' else 1
                    xp = int(parts[2]) if parts[2] != '-1' else 0
                    
                    # Calculate XP to next level
                    xp_to_next = None
                    if level < 99 and level < len(self.xp_table):
                        xp_to_next = self.xp_table[level] - xp
                    
                    parsed_data["skills"][self.skills[i]] = {
                        "rank": rank,
                        "level": level,
                        "xp": xp,
                        "xp_to_next": xp_to_next
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

    def calculate_combat_level(self, stats: dict) -> int:
        """Calculate accurate combat level."""
        try:
            attack = stats["skills"]["Attack"]["level"]
            strength = stats["skills"]["Strength"]["level"]
            defence = stats["skills"]["Defence"]["level"]
            hitpoints = stats["skills"]["Hitpoints"]["level"]
            prayer = stats["skills"]["Prayer"]["level"]
            ranged = stats["skills"]["Ranged"]["level"]
            magic = stats["skills"]["Magic"]["level"]
            
            # Combat level formula
            base = 0.25 * (defence + hitpoints + (prayer // 2))
            melee = 0.325 * (attack + strength)
            ranged_level = 0.325 * (ranged * 1.5)
            magic_level = 0.325 * (magic * 1.5)
            
            combat_level = base + max(melee, ranged_level, magic_level)
            return int(combat_level)
        except:
            return 3  # Default combat level

    def create_comprehensive_embed(self, username: str, stats: dict) -> discord.Embed:
        """Create a comprehensive Discord embed with all player stats."""
        embed = discord.Embed(
            title=f"🗡️ Complete OSRS Stats for {username}",
            color=0x8B4513,
            url=f"https://secure.runescape.com/m=hiscore_oldschool/hiscorepersonal?user1={username}"
        )
        
        # Overall stats and combat level
        overall = stats["skills"]["Overall"]
        combat_level = self.calculate_combat_level(stats)
        total_level = sum(skill_data["level"] for skill_data in stats["skills"].values() if skill_data["level"] > 1)
        
        embed.add_field(
            name="📊 Overview",
            value=f"**Combat Level:** {combat_level}\n**Total Level:** {total_level}\n**Total XP:** {self.format_number(overall['xp'])}\n**Overall Rank:** {self.format_number(overall['rank']) if overall['rank'] else 'Unranked'}",
            inline=True
        )
        
        # All Combat Skills with exact XP
        combat_skills = ["Attack", "Strength", "Defence", "Hitpoints", "Ranged", "Prayer", "Magic"]
        combat_text = ""
        for skill in combat_skills:
            if skill in stats["skills"]:
                skill_data = stats["skills"][skill]
                combat_text += f"**{skill}:** {skill_data['level']} ({self.format_number(skill_data['xp'])} xp)\n"
        
        embed.add_field(
            name="⚔️ Combat Skills",
            value=combat_text,
            inline=True
        )
        
        # All Non-Combat Skills with exact XP
        non_combat_skills = ["Cooking", "Woodcutting", "Fletching", "Fishing", "Firemaking", 
                           "Crafting", "Smithing", "Mining", "Herblore", "Agility", "Thieving",
                           "Slayer", "Farming", "Runecraft", "Hunter", "Construction"]
        
        # Split into two columns for better display
        skills_col1 = non_combat_skills[:8]
        skills_col2 = non_combat_skills[8:]
        
        skills_text1 = ""
        for skill in skills_col1:
            if skill in stats["skills"]:
                skill_data = stats["skills"][skill]
                skills_text1 += f"**{skill}:** {skill_data['level']} ({self.format_number(skill_data['xp'])} xp)\n"
        
        skills_text2 = ""
        for skill in skills_col2:
            if skill in stats["skills"]:
                skill_data = stats["skills"][skill]
                skills_text2 += f"**{skill}:** {skill_data['level']} ({self.format_number(skill_data['xp'])} xp)\n"
        
        embed.add_field(
            name="🛠️ Skills (Part 1)",
            value=skills_text1,
            inline=True
        )
        
        embed.add_field(
            name="🛠️ Skills (Part 2)",
            value=skills_text2,
            inline=True
        )
        
        embed.add_field(
            name="⠀",  # Invisible character for spacing
            value="⠀",
            inline=True
        )
        
        # All Boss Kill Counts
        boss_activities = [name for name in self.activities if any(boss in name.lower() for boss in 
            ['sire', 'hydra', 'artio', 'bryophyta', 'callisto', "cal'varion", 'cerberus', 'chambers', 
             'chaos', 'zilyana', 'corporeal', 'archaeologist', 'duke', 'graardor', 'mole', 'grotesque',
             'hespori', 'kalphite', 'king black', 'kraken', 'kree', 'k\'ril', 'leviathan', 'mimic',
             'nex', 'nightmare', 'obor', 'phantom', 'sarachnis', 'scorpia', 'scurrius', 'skotizo',
             'spindel', 'gauntlet', 'whisperer', 'theatre', 'thermonuclear', 'tombs', 'tzkal', 'tztok',
             'vardorvis', 'venenatis', 'vet\'ion', 'vorkath', 'zalcano', 'zulrah'])]
        
        boss_text = ""
        boss_count = 0
        for boss in boss_activities:
            if boss in stats["activities"] and stats["activities"][boss]["score"] > 0:
                score = stats["activities"][boss]["score"]
                boss_text += f"**{boss}:** {self.format_number(score)}\n"
                boss_count += 1
                if boss_count >= 15:  # Limit to prevent embed being too long
                    boss_text += f"*... and more*\n"
                    break
        
        if boss_text:
            embed.add_field(
                name="🐉 Boss Kill Counts",
                value=boss_text,
                inline=False
            )
        
        # Clue Scrolls and Minigames
        clue_activities = [name for name in self.activities if 'clue' in name.lower() or 
                          name in ['League Points', 'LMS - Rank', 'PvP Arena - Rank', 'Soul Wars Zeal', 
                                 'Rifts closed', 'Colosseum Glory', 'Tempoross', 'Wintertodt']]
        
        clue_text = ""
        for activity in clue_activities:
            if activity in stats["activities"] and stats["activities"][activity]["score"] > 0:
                score = stats["activities"][activity]["score"]
                clue_text += f"**{activity}:** {self.format_number(score)}\n"
        
        if clue_text:
            embed.add_field(
                name="🗞️ Clues & Minigames",
                value=clue_text,
                inline=True
            )
        
        embed.set_footer(text="Complete data from OSRS Hiscores • Use !osrsskill for detailed skill info")
        return embed

    def create_skill_embed(self, username: str, skill: str, skill_data: dict) -> discord.Embed:
        """Create a detailed embed for a specific skill."""
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
        
        # XP to next level
        if skill_data['xp_to_next'] is not None and skill_data['xp_to_next'] > 0:
            embed.add_field(
                name="XP to Next Level",
                value=f"**{self.format_number(skill_data['xp_to_next'])}**",
                inline=True
            )
        elif skill_data['level'] >= 99:
            embed.add_field(
                name="Status",
                value="**Level 99 Achieved!**",
                inline=True
            )
        
        # XP at current level
        if skill_data['level'] > 1 and skill_data['level'] <= len(self.xp_table):
            current_level_xp = self.xp_table[skill_data['level'] - 1]
            xp_gained_this_level = skill_data['xp'] - current_level_xp
            embed.add_field(
                name="XP Gained This Level",
                value=f"**{self.format_number(xp_gained_this_level)}**",
                inline=True
            )
        
        return embed

    @commands.command(name="osrs", aliases=["osrsstats", "oldschool"])
    async def osrs_stats(self, ctx, *, username: str):
        """
        Fetch and display complete OSRS player statistics with all skills and boss kills.
        
        Usage: !osrs <username>
        Example: !osrs Zezima
        """
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
            
            embed = self.create_comprehensive_embed(username, stats)
            await ctx.send(embed=embed)

    @commands.command(name="osrsskill", aliases=["osrssk", "oldschoolskill"])
    async def osrs_skill(self, ctx, username: str, skill: str):
        """
        Get detailed information about a specific skill with exact XP values.
        
        Usage: !osrsskill <username> <skill>
        Example: !osrsskill Zezima woodcutting
        """
        username = username.strip().replace(' ', '_')
        skill = skill.lower().capitalize()
        
        # Handle special cases and abbreviations
        skill_mapping = {
            "Hp": "Hitpoints",
            "Wc": "Woodcutting",
            "Fm": "Firemaking",
            "Rc": "Runecraft",
            "Att": "Attack",
            "Str": "Strength",
            "Def": "Defence",
            "Range": "Ranged",
            "Mage": "Magic",
            "Pray": "Prayer",
            "Cook": "Cooking",
            "Fish": "Fishing",
            "Fletch": "Fletching",
            "Craft": "Crafting",
            "Smith": "Smithing",
            "Mine": "Mining",
            "Herb": "Herblore",
            "Agil": "Agility",
            "Thiev": "Thieving",
            "Slay": "Slayer",
            "Farm": "Farming",
            "Hunt": "Hunter",
            "Con": "Construction"
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
                available_skills = ", ".join(self.skills[1:])
                embed = discord.Embed(
                    title="❌ Invalid Skill",
                    description=f"'{skill}' is not a valid skill.\n\n**Available skills:**\n{available_skills}",
                    color=0xFF0000
                )
                await ctx.send(embed=embed)
                return
            
            skill_data = stats["skills"][skill]
            embed = self.create_skill_embed(username, skill, skill_data)
            await ctx.send(embed=embed)

    @commands.command(name="osrsboss", aliases=["osrsbosses", "oldschoolboss"])
    async def osrs_boss(self, ctx, *, username: str):
        """
        Display all boss kill counts for a player.
        
        Usage: !osrsboss <username>
        Example: !osrsboss Zezima
        """
        username = username.strip().replace(' ', '_')
        
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
            
            embed = discord.Embed(
                title=f"🐉 Boss Kill Counts for {username}",
                color=0x8B4513,
                url=f"https://secure.runescape.com/m=hiscore_oldschool/hiscorepersonal?user1={username}"
            )
            
            # Get all boss activities with kills
            boss_activities = []
            for activity in self.activities:
                if activity in stats["activities"] and stats["activities"][activity]["score"] > 0:
                    # Check if it's likely a boss (exclude clues, minigames, etc.)
                    if not any(exclude in activity.lower() for exclude in 
                             ['clue', 'league', 'bounty', 'lms', 'pvp', 'soul wars', 'rifts', 'colosseum']):
                        boss_activities.append((activity, stats["activities"][activity]["score"]))
            
            if not boss_activities:
                embed.description = "No boss kills found for this player."
                await ctx.send(embed=embed)
                return
            
            # Sort by kill count (highest first)
            boss_activities.sort(key=lambda x: x[1], reverse=True)
            
            # Split into multiple fields if needed
            boss_text = ""
            for boss, kills in boss_activities:
                boss_text += f"**{boss}:** {self.format_number(kills)}\n"
            
            # Split into chunks if too long
            if len(boss_text) > 1024:
                chunks = []
                current_chunk = ""
                for boss, kills in boss_activities:
                    line = f"**{boss}:** {self.format_number(kills)}\n"
                    if len(current_chunk + line) > 1024:
                        chunks.append(current_chunk)
                        current_chunk = line
                    else:
                        current_chunk += line
                if current_chunk:
                    chunks.append(current_chunk)
                
                for i, chunk in enumerate(chunks):
                    field_name = "🐉 Boss Kills" if i == 0 else f"🐉 Boss Kills (Part {i+1})"
                    embed.add_field(name=field_name, value=chunk, inline=False)
            else:
                embed.add_field(name="🐉 Boss Kills", value=boss_text, inline=False)
            
            total_boss_kills = sum(kills for _, kills in boss_activities)
            embed.set_footer(text=f"Total Boss Kills: {self.format_number(total_boss_kills)}")
            
            await ctx.send(embed=embed)

def setup(bot: Red):
    bot.add_cog(OSRSStats(bot))