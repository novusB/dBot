import aiohttp
import discord
from redbot.core import commands, Config
from redbot.core.bot import Red
from typing import Optional, Dict, List, Tuple
import asyncio
import math
from datetime import datetime, timedelta

class OSRSStats(commands.Cog):
    """Old School RuneScape player statistics and analysis tools. Supports usernames with spaces using quotes."""
    
    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=7829463051)
        self.session = aiohttp.ClientSession()
        
        # Initialize default config for tracking
        default_global = {}
        default_user = {
            "tracked_players": {},
            "last_update": None
        }
        self.config.register_global(**default_global)
        self.config.register_user(**default_user)
        
        # OSRS Skills mapping with categories
        self.skills = [
            "Overall", "Attack", "Defence", "Strength", "Hitpoints", "Ranged", "Prayer",
            "Magic", "Cooking", "Woodcutting", "Fletching", "Fishing", "Firemaking",
            "Crafting", "Smithing", "Mining", "Herblore", "Agility", "Thieving",
            "Slayer", "Farming", "Runecraft", "Hunter", "Construction"
        ]
        
        # Skill categories for better organization
        self.skill_categories = {
            "Combat": ["Attack", "Strength", "Defence", "Hitpoints", "Ranged", "Prayer", "Magic"],
            "Gathering": ["Mining", "Fishing", "Woodcutting", "Hunter", "Farming"],
            "Artisan": ["Smithing", "Crafting", "Fletching", "Cooking", "Firemaking", "Herblore", "Construction"],
            "Support": ["Runecraft", "Agility", "Thieving", "Slayer"]
        }
        
        # Skill icons for better visual representation
        self.skill_icons = {
            "Attack": "⚔️", "Strength": "💪", "Defence": "🛡️", "Hitpoints": "❤️",
            "Ranged": "🏹", "Prayer": "🙏", "Magic": "🔮", "Cooking": "🍳",
            "Woodcutting": "🪓", "Fletching": "🏹", "Fishing": "🎣", "Firemaking": "🔥",
            "Crafting": "🧵", "Smithing": "🔨", "Mining": "⛏️", "Herblore": "🧪",
            "Agility": "🏃", "Thieving": "🥷", "Slayer": "💀", "Farming": "🌱",
            "Runecraft": "🌟", "Hunter": "🪤", "Construction": "🏠"
        }
        
        # OSRS Activities mapping (complete and up-to-date)
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

        # Boss difficulty ratings for analysis
        self.boss_difficulty = {
            "TzKal-Zuk": 5, "Theatre of Blood: Hard Mode": 5, "Tombs of Amascut: Expert Mode": 5,
            "The Corrupted Gauntlet": 4, "Theatre of Blood": 4, "Chambers of Xeric: Challenge Mode": 4,
            "Nex": 4, "Phosani's Nightmare": 4, "Nightmare": 3, "Chambers of Xeric": 3,
            "Vorkath": 3, "Zulrah": 3, "Cerberus": 3, "Kraken": 2, "Barrows Chests": 2,
            "King Black Dragon": 1, "Giant Mole": 1, "Obor": 1, "Bryophyta": 1
        }

        # Exact XP table for all levels 1-99 and beyond
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

        # Virtual levels beyond 99 (for 200M XP calculations)
        self.virtual_levels = {}
        current_xp = 13034431
        for level in range(100, 127):
            current_xp = int(current_xp * 1.1)
            self.virtual_levels[level] = current_xp

        # Milestone XP values
        self.xp_milestones = {
            1000000: "1M", 5000000: "5M", 10000000: "10M", 
            25000000: "25M", 50000000: "50M", 100000000: "100M", 200000000: "200M"
        }

        # Quest requirements for popular content
        self.quest_requirements = {
            "Barrows": "Priest in Peril",
            "Zulrah": "Regicide",
            "Vorkath": "Dragon Slayer II",
            "Theatre of Blood": "A Taste of Hope",
            "Chambers of Xeric": "No quest requirement",
            "The Gauntlet": "Song of the Elves"
        }

    def cog_unload(self):
        asyncio.create_task(self.session.close())

    def format_username_for_url(self, username: str) -> str:
        """Format username for OSRS API URL - spaces become underscores."""
        return username.replace(' ', '_')

    def format_username_for_display(self, username: str) -> str:
        """Format username for display - keep original formatting."""
        return username

    async def fetch_player_stats(self, username: str, account_type: str = "normal") -> Optional[dict]:
        """Fetch player stats from OSRS Hiscores API with account type support."""
        base_urls = {
            "normal": "https://secure.runescape.com/m=hiscore_oldschool/index_lite.ws",
            "ironman": "https://secure.runescape.com/m=hiscore_oldschool_ironman/index_lite.ws",
            "hardcore": "https://secure.runescape.com/m=hiscore_oldschool_hardcore_ironman/index_lite.ws",
            "ultimate": "https://secure.runescape.com/m=hiscore_oldschool_ultimate/index_lite.ws",
            "deadman": "https://secure.runescape.com/m=hiscore_oldschool_deadman/index_lite.ws",
            "seasonal": "https://secure.runescape.com/m=hiscore_oldschool_seasonal/index_lite.ws"
        }
        
        # Format username for URL (spaces to underscores)
        url_username = self.format_username_for_url(username)
        url = f"{base_urls.get(account_type, base_urls['normal'])}?player={url_username}"
        
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
        """Parse the hiscores data into a structured format with enhanced analysis."""
        lines = data.strip().split('\n')
        parsed_data = {"skills": {}, "activities": {}, "analysis": {}}
        
        # Parse skills with enhanced data
        for i, line in enumerate(lines[:24]):
            if i < len(self.skills):
                parts = line.split(',')
                if len(parts) >= 3:
                    rank = int(parts[0]) if parts[0] != '-1' else None
                    level = int(parts[1]) if parts[1] != '-1' else 1
                    xp = int(parts[2]) if parts[2] != '-1' else 0
                    
                    # Calculate various metrics
                    xp_to_next = None
                    virtual_level = level
                    percentage_to_next = 0
                    
                    if level < 99:
                        if level < len(self.xp_table):
                            xp_to_next = self.xp_table[level] - xp
                            if level > 1:
                                current_level_xp = self.xp_table[level - 1]
                                next_level_xp = self.xp_table[level]
                                xp_in_level = xp - current_level_xp
                                xp_for_level = next_level_xp - current_level_xp
                                percentage_to_next = (xp_in_level / xp_for_level) * 100
                    else:
                        # Calculate virtual level for 99+ skills
                        for virt_level, virt_xp in self.virtual_levels.items():
                            if xp >= virt_xp:
                                virtual_level = virt_level + 1
                            else:
                                break
                    
                    # Determine next milestone
                    next_milestone = None
                    for milestone_xp, milestone_name in self.xp_milestones.items():
                        if xp < milestone_xp:
                            next_milestone = {"xp": milestone_xp, "name": milestone_name, "remaining": milestone_xp - xp}
                            break
                    
                    parsed_data["skills"][self.skills[i]] = {
                        "rank": rank,
                        "level": level,
                        "xp": xp,
                        "xp_to_next": xp_to_next,
                        "virtual_level": virtual_level,
                        "percentage_to_next": percentage_to_next,
                        "next_milestone": next_milestone,
                        "icon": self.skill_icons.get(self.skills[i], "📊")
                    }
        
        # Parse activities
        for i, line in enumerate(lines[24:]):
            if i < len(self.activities):
                parts = line.split(',')
                if len(parts) >= 2:
                    rank = int(parts[0]) if parts[0] != '-1' else None
                    score = int(parts[1]) if parts[1] != '-1' else 0
                    
                    parsed_data["activities"][self.activities[i]] = {
                        "rank": rank,
                        "score": score,
                        "difficulty": self.boss_difficulty.get(self.activities[i], 0)
                    }
        
        # Generate analysis
        parsed_data["analysis"] = self.generate_analysis(parsed_data)
        
        return parsed_data

    def generate_analysis(self, stats: dict) -> dict:
        """Generate detailed analysis of player stats."""
        analysis = {}
        
        # Account progression analysis
        total_level = sum(skill_data["level"] for skill_data in stats["skills"].values() if skill_data["level"] > 1)
        total_xp = stats["skills"]["Overall"]["xp"]
        
        # Determine account stage
        if total_level < 500:
            account_stage = "Early Game"
        elif total_level < 1000:
            account_stage = "Mid Game"
        elif total_level < 1500:
            account_stage = "Late Game"
        else:
            account_stage = "End Game"
        
        # Combat analysis
        combat_level = self.calculate_combat_level(stats)
        combat_stats = {skill: stats["skills"][skill]["level"] for skill in self.skill_categories["Combat"]}
        
        # Find highest and lowest skills
        skill_levels = {skill: data["level"] for skill, data in stats["skills"].items() if skill != "Overall"}
        highest_skill = max(skill_levels, key=skill_levels.get)
        lowest_skill = min(skill_levels, key=skill_levels.get)
        
        # Boss analysis
        boss_kills = {name: data["score"] for name, data in stats["activities"].items() 
                     if data["score"] > 0 and name not in ["League Points", "LMS - Rank", "PvP Arena - Rank", "Soul Wars Zeal"]}
        total_boss_kills = sum(boss_kills.values())
        
        # PvM difficulty analysis
        high_level_pvm = sum(kills for boss, kills in boss_kills.items() 
                           if self.boss_difficulty.get(boss, 0) >= 4)
        
        # Skill balance analysis
        skill_variance = max(skill_levels.values()) - min(skill_levels.values())
        
        analysis = {
            "account_stage": account_stage,
            "combat_level": combat_level,
            "total_level": total_level,
            "total_xp": total_xp,
            "highest_skill": {"name": highest_skill, "level": skill_levels[highest_skill]},
            "lowest_skill": {"name": lowest_skill, "level": skill_levels[lowest_skill]},
            "skill_variance": skill_variance,
            "total_boss_kills": total_boss_kills,
            "high_level_pvm": high_level_pvm,
            "combat_stats": combat_stats,
            "maxed_skills": len([level for level in skill_levels.values() if level >= 99]),
            "skills_above_90": len([level for level in skill_levels.values() if level >= 90]),
            "skills_above_80": len([level for level in skill_levels.values() if level >= 80])
        }
        
        return analysis

    def calculate_combat_level(self, stats: dict) -> int:
        """Calculate accurate combat level using OSRS formula."""
        try:
            attack = stats["skills"]["Attack"]["level"]
            strength = stats["skills"]["Strength"]["level"]
            defence = stats["skills"]["Defence"]["level"]
            hitpoints = stats["skills"]["Hitpoints"]["level"]
            prayer = stats["skills"]["Prayer"]["level"]
            ranged = stats["skills"]["Ranged"]["level"]
            magic = stats["skills"]["Magic"]["level"]
            
            base = 0.25 * (defence + hitpoints + math.floor(prayer / 2))
            melee = 0.325 * (attack + strength)
            ranged_level = 0.325 * (ranged * 1.5)
            magic_level = 0.325 * (magic * 1.5)
            
            combat_level = base + max(melee, ranged_level, magic_level)
            return int(combat_level)
        except:
            return 3

    def format_number(self, num: int) -> str:
        """Format large numbers with appropriate suffixes."""
        if num >= 1000000000:
            return f"{num/1000000000:.1f}B"
        elif num >= 1000000:
            return f"{num/1000000:.1f}M"
        elif num >= 1000:
            return f"{num/1000:.1f}K"
        else:
            return f"{num:,}"

    def get_efficiency_rating(self, stats: dict) -> str:
        """Calculate efficiency rating based on XP distribution."""
        total_xp = stats["skills"]["Overall"]["xp"]
        total_level = sum(skill_data["level"] for skill_data in stats["skills"].values() if skill_data["level"] > 1)
        
        # Calculate efficiency based on XP per level
        if total_level > 0:
            xp_per_level = total_xp / total_level
            if xp_per_level > 100000:
                return "Very High"
            elif xp_per_level > 50000:
                return "High"
            elif xp_per_level > 25000:
                return "Medium"
            else:
                return "Low"
        return "Unknown"

    def create_detailed_overview_embed(self, username: str, stats: dict, account_type: str = "normal") -> discord.Embed:
        """Create a comprehensive overview embed with detailed analysis."""
        analysis = stats["analysis"]
        account_type_display = account_type.replace("_", " ").title() if account_type != "normal" else ""
        display_username = self.format_username_for_display(username)
        url_username = self.format_username_for_url(username)
        
        embed = discord.Embed(
            title=f"🗡️ {account_type_display} OSRS Analysis for {display_username}",
            color=0x8B4513,
            url=f"https://secure.runescape.com/m=hiscore_oldschool/hiscorepersonal?user1={url_username}"
        )
        
        # Account Overview
        efficiency = self.get_efficiency_rating(stats)
        embed.add_field(
            name="📊 Account Overview",
            value=f"**Stage:** {analysis['account_stage']}\n"
                  f"**Combat Level:** {analysis['combat_level']}\n"
                  f"**Total Level:** {self.format_number(analysis['total_level'])}\n"
                  f"**Total XP:** {self.format_number(analysis['total_xp'])}\n"
                  f"**Efficiency:** {efficiency}",
            inline=True
        )
        
        # Skill Progress
        embed.add_field(
            name="🎯 Skill Progress",
            value=f"**99s Achieved:** {analysis['maxed_skills']}/23\n"
                  f"**90+ Skills:** {analysis['skills_above_90']}\n"
                  f"**80+ Skills:** {analysis['skills_above_80']}\n"
                  f"**Highest:** {analysis['highest_skill']['name']} ({analysis['highest_skill']['level']})\n"
                  f"**Lowest:** {analysis['lowest_skill']['name']} ({analysis['lowest_skill']['level']})",
            inline=True
        )
        
        # PvM Analysis
        embed.add_field(
            name="🐉 PvM Analysis",
            value=f"**Total Boss Kills:** {self.format_number(analysis['total_boss_kills'])}\n"
                  f"**High-Level PvM:** {self.format_number(analysis['high_level_pvm'])}\n"
                  f"**Skill Variance:** {analysis['skill_variance']} levels",
            inline=True
        )
        
        # Combat Stats with detailed breakdown
        combat_text = ""
        for skill in self.skill_categories["Combat"]:
            if skill in stats["skills"]:
                skill_data = stats["skills"][skill]
                icon = skill_data["icon"]
                level = skill_data["level"]
                xp = skill_data["xp"]
                combat_text += f"{icon} **{skill}:** {level} ({self.format_number(xp)} xp)\n"
        
        embed.add_field(
            name="⚔️ Combat Skills",
            value=combat_text,
            inline=False
        )
        
        # Skill recommendations based on analysis
        recommendations = self.generate_recommendations(stats)
        if recommendations:
            embed.add_field(
                name="💡 Recommendations",
                value=recommendations,
                inline=False
            )
        
        embed.set_footer(text=f"Account Stage: {analysis['account_stage']} • Use .osrs skill/boss/goals for more details")
        return embed

    def generate_recommendations(self, stats: dict) -> str:
        """Generate personalized recommendations based on player stats."""
        recommendations = []
        analysis = stats["analysis"]
        
        # Combat recommendations
        combat_stats = analysis["combat_stats"]
        if combat_stats["Attack"] < 70 and analysis["account_stage"] in ["Mid Game", "Late Game"]:
            recommendations.append("Consider training Attack to 70+ for better weapons")
        
        if combat_stats["Defence"] < combat_stats["Attack"] - 10:
            recommendations.append("Balance Defence with your Attack level")
        
        # Skill balance recommendations
        if analysis["skill_variance"] > 30:
            lowest_skill = analysis["lowest_skill"]
            recommendations.append(f"Consider training {lowest_skill['name']} to balance your account")
        
        # PvM recommendations
        if analysis["total_boss_kills"] < 100 and analysis["combat_level"] > 100:
            recommendations.append("Try some PvM content - you have the combat level for it!")
        
        # Efficiency recommendations
        skills_to_train = []
        for skill, data in stats["skills"].items():
            if skill != "Overall" and data["level"] < 70 and skill in ["Slayer", "Farming", "Construction"]:
                skills_to_train.append(skill)
        
        if skills_to_train:
            recommendations.append(f"Focus on: {', '.join(skills_to_train[:2])} for account progression")
        
        return "\n".join(f"• {rec}" for rec in recommendations[:4])  # Limit to 4 recommendations

    @commands.group(name="osrs", aliases=["osrsstats", "oldschool"], invoke_without_command=True)
    async def osrs_stats(self, ctx, *, args: str):
        """
        Get comprehensive OSRS player statistics with detailed analysis and recommendations.
        
        Main command that provides complete account overview including combat level, total XP,
        skill progress, PvM statistics, and personalized recommendations.
        
        Supports all account types: normal, ironman, hardcore, ultimate, deadman, seasonal
        Use quotes around usernames with spaces: .osrs "tcp syn ack"
        
        Examples:
        .osrs "tcp syn ack"
        .osrs "tcp syn ack" ironman
        .osrs Zezima
        .osrs Zezima hardcore
        
        Subcommands available:
        .osrs skill - Detailed skill analysis
        .osrs boss - Boss kill counts
        .osrs goals - XP goal calculator
        .osrs help - Complete command guide
        """
        # Parse arguments - handle quoted usernames and account types
        parts = []
        current_part = ""
        in_quotes = False
        
        for char in args:
            if char == '"' and not in_quotes:
                in_quotes = True
            elif char == '"' and in_quotes:
                in_quotes = False
                if current_part:
                    parts.append(current_part)
                    current_part = ""
            elif char == ' ' and not in_quotes:
                if current_part:
                    parts.append(current_part)
                    current_part = ""
            else:
                current_part += char
        
        if current_part:
            parts.append(current_part)
        
        if not parts:
            await ctx.send("❌ Please provide a username!\n\n**Usage:**\n`.osrs \"username with spaces\"`\n`.osrs username_without_spaces`\n\n**Subcommands:**\n`.osrs skill` - Skill analysis\n`.osrs boss` - Boss kills\n`.osrs goals` - Goal calculator\n`.osrs help` - Full help guide")
            return
        
        username = parts[0]
        account_type = parts[1].lower() if len(parts) > 1 else "normal"
        
        valid_types = ["normal", "ironman", "hardcore", "ultimate", "deadman", "seasonal"]
        if account_type not in valid_types:
            account_type = "normal"
        
        async with ctx.typing():
            stats = await self.fetch_player_stats(username, account_type)
            
            if stats is None:
                display_username = self.format_username_for_display(username)
                embed = discord.Embed(
                    title="❌ Player Not Found",
                    description=f"Could not find player '{display_username}' on the {account_type.title()} OSRS Hiscores.\n\n"
                               f"**Make sure:**\n"
                               f"• The username is spelled correctly\n"
                               f"• The player has logged in recently\n"
                               f"• Use quotes for usernames with spaces: `.osrs \"tcp syn ack\"`",
                    color=0xFF0000
                )
                await ctx.send(embed=embed)
                return
            
            embed = self.create_detailed_overview_embed(username, stats, account_type)
            await ctx.send(embed=embed)

    @osrs_stats.command(name="skill", aliases=["sk", "skills"])
    async def osrs_skill(self, ctx, *, args: str):
        """
        Get detailed analysis of a specific OSRS skill with progress tracking and unlocks.
        
        Shows comprehensive skill information including XP, level progress, virtual levels,
        milestones, skill-specific unlocks, and training recommendations.
        
        Use quotes around usernames with spaces: .osrs skill "tcp syn ack" woodcutting
        
        Examples:
        .osrs skill "tcp syn ack" woodcutting
        .osrs skill "tcp syn ack" attack ironman
        .osrs skill Zezima mining
        .osrs sk Zezima hp ultimate
        
        Skill abbreviations supported:
        hp=Hitpoints, wc=Woodcutting, fm=Firemaking, rc=Runecraft, att=Attack,
        str=Strength, def=Defence, range=Ranged, mage=Magic, pray=Prayer, etc.
        """
        # Parse arguments - handle quoted usernames
        parts = []
        current_part = ""
        in_quotes = False
        
        for char in args:
            if char == '"' and not in_quotes:
                in_quotes = True
            elif char == '"' and in_quotes:
                in_quotes = False
                if current_part:
                    parts.append(current_part)
                    current_part = ""
            elif char == ' ' and not in_quotes:
                if current_part:
                    parts.append(current_part)
                    current_part = ""
            else:
                current_part += char
        
        if current_part:
            parts.append(current_part)
        
        if len(parts) < 2:
            await ctx.send("❌ Please provide both username and skill!\n\n**Usage:**\n`.osrs skill \"username with spaces\" skill`\n`.osrs skill username_without_spaces skill`")
            return
        
        username = parts[0]
        skill = parts[1].lower().capitalize()
        account_type = parts[2].lower() if len(parts) > 2 else "normal"
        
        # Enhanced skill mapping with more abbreviations
        skill_mapping = {
            "Hp": "Hitpoints", "Wc": "Woodcutting", "Fm": "Firemaking", "Rc": "Runecraft",
            "Att": "Attack", "Str": "Strength", "Def": "Defence", "Range": "Ranged",
            "Mage": "Magic", "Pray": "Prayer", "Cook": "Cooking", "Fish": "Fishing",
            "Fletch": "Fletching", "Craft": "Crafting", "Smith": "Smithing", "Mine": "Mining",
            "Herb": "Herblore", "Agil": "Agility", "Thiev": "Thieving", "Slay": "Slayer",
            "Farm": "Farming", "Hunt": "Hunter", "Con": "Construction", "Overall": "Overall"
        }
        skill = skill_mapping.get(skill, skill)
        
        async with ctx.typing():
            stats = await self.fetch_player_stats(username, account_type)
            
            if stats is None:
                display_username = self.format_username_for_display(username)
                embed = discord.Embed(
                    title="❌ Player Not Found",
                    description=f"Could not find player '{display_username}' on the OSRS Hiscores.\n\n"
                               f"Use quotes for usernames with spaces: `.osrs skill \"tcp syn ack\" woodcutting`",
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
            embed = self.create_detailed_skill_embed(username, skill, skill_data, account_type)
            await ctx.send(embed=embed)

    def create_detailed_skill_embed(self, username: str, skill: str, skill_data: dict, account_type: str) -> discord.Embed:
        """Create an extremely detailed skill analysis embed."""
        icon = skill_data["icon"]
        display_username = self.format_username_for_display(username)
        
        embed = discord.Embed(
            title=f"{icon} {skill} Analysis for {display_username}",
            color=0x8B4513
        )
        
        # Basic stats
        embed.add_field(
            name="📊 Current Stats",
            value=f"**Level:** {skill_data['level']}\n"
                  f"**Experience:** {self.format_number(skill_data['xp'])}\n"
                  f"**Rank:** {self.format_number(skill_data['rank']) if skill_data['rank'] else 'Unranked'}\n"
                  f"**Virtual Level:** {skill_data['virtual_level']}",
            inline=True
        )
        
        # Progress information
        progress_text = ""
        if skill_data['xp_to_next'] is not None and skill_data['xp_to_next'] > 0:
            progress_text += f"**XP to {skill_data['level'] + 1}:** {self.format_number(skill_data['xp_to_next'])}\n"
            progress_text += f"**Progress:** {skill_data['percentage_to_next']:.1f}%\n"
        elif skill_data['level'] >= 99:
            progress_text += "**Status:** Level 99 Achieved! 🎉\n"
        
        if skill_data['next_milestone']:
            milestone = skill_data['next_milestone']
            progress_text += f"**Next Milestone:** {milestone['name']} ({self.format_number(milestone['remaining'])} xp)"
        
        if progress_text:
            embed.add_field(
                name="📈 Progress",
                value=progress_text,
                inline=True
            )
        
        # XP breakdown
        if skill_data['level'] > 1 and skill_data['level'] <= len(self.xp_table):
            current_level_xp = self.xp_table[skill_data['level'] - 1] if skill_data['level'] > 1 else 0
            xp_gained_this_level = skill_data['xp'] - current_level_xp
            
            embed.add_field(
                name="🔢 XP Breakdown",
                value=f"**XP This Level:** {self.format_number(xp_gained_this_level)}\n"
                      f"**Level {skill_data['level']} XP:** {self.format_number(current_level_xp)}\n"
                      f"**99 Requirement:** {self.format_number(13034431)}\n"
                      f"**200M XP:** {self.format_number(200000000)}",
                inline=True
            )
        
        # Skill-specific information
        skill_info = self.get_skill_specific_info(skill, skill_data)
        if skill_info:
            embed.add_field(
                name="ℹ️ Skill Information",
                value=skill_info,
                inline=False
            )
        
        embed.set_footer(text=f"Skill Category: {self.get_skill_category(skill)} • Virtual Level: {skill_data['virtual_level']}")
        return embed

    def get_skill_category(self, skill: str) -> str:
        """Get the category of a skill."""
        for category, skills in self.skill_categories.items():
            if skill in skills:
                return category
        return "Other"

    def get_skill_specific_info(self, skill: str, skill_data: dict) -> str:
        """Get skill-specific information and tips."""
        level = skill_data['level']
        info = []
        
        # Skill-specific unlocks and information
        skill_unlocks = {
            "Attack": {
                40: "Rune weapons", 50: "Granite maul", 60: "Dragon weapons", 70: "Whip/Barrows weapons", 75: "Godswords"
            },
            "Defence": {
                40: "Rune armor", 45: "Berserker helm", 60: "Dragon armor", 70: "Barrows armor"
            },
            "Slayer": {
                55: "Broad bolts", 62: "Dust devils", 72: "Skeletal Wyverns", 75: "Gargoyles", 85: "Abyssal demons"
            },
            "Prayer": {
                43: "Protection prayers", 70: "Piety", 74: "Rigour", 77: "Augury"
            },
            "Magic": {
                55: "High Level Alchemy", 59: "Teleblock", 82: "Vengeance", 94: "Ice Barrage"
            },
            "Runecraft": {
                44: "Nature runes", 54: "Law runes", 77: "Blood runes", 91: "Double nature runes"
            }
        }
        
        if skill in skill_unlocks:
            unlocks = skill_unlocks[skill]
            next_unlock = None
            for unlock_level, unlock_name in unlocks.items():
                if level < unlock_level:
                    next_unlock = f"Level {unlock_level}: {unlock_name}"
                    break
            
            if next_unlock:
                info.append(f"**Next Unlock:** {next_unlock}")
        
        # General milestones
        if level < 99:
            levels_to_99 = 99 - level
            info.append(f"**Levels to 99:** {levels_to_99}")
        
        return "\n".join(info) if info else None

    @osrs_stats.command(name="boss", aliases=["bosses", "pvm"])
    async def osrs_boss(self, ctx, *, args: str):
        """
        Display all boss kill counts and PvM statistics for an OSRS player.
        
        Shows comprehensive PvM data including kill counts for all bosses, raids,
        and high-level content. Sorted by kill count with total statistics.
        
        Use quotes around usernames with spaces: .osrs boss "tcp syn ack"
        
        Examples:
        .osrs boss "tcp syn ack"
        .osrs boss "tcp syn ack" ironman
        .osrs boss Zezima
        .osrs bosses Zezima hardcore
        .osrs pvm Zezima ultimate
        
        Includes all PvM content:
        • All boss kill counts
        • Raid completions (CoX, ToB, ToA)
        • Minigame scores
        • Clue scroll completions
        """
        # Parse arguments
        parts = []
        current_part = ""
        in_quotes = False
        
        for char in args:
            if char == '"' and not in_quotes:
                in_quotes = True
            elif char == '"' and in_quotes:
                in_quotes = False
                if current_part:
                    parts.append(current_part)
                    current_part = ""
            elif char == ' ' and not in_quotes:
                if current_part:
                    parts.append(current_part)
                    current_part = ""
            else:
                current_part += char
        
        if current_part:
            parts.append(current_part)
        
        if not parts:
            await ctx.send("❌ Please provide a username!\n\n**Usage:**\n`.osrs boss \"username with spaces\"`\n`.osrs boss username_without_spaces`")
            return
        
        username = parts[0]
        account_type = parts[1].lower() if len(parts) > 1 else "normal"
        
        async with ctx.typing():
            stats = await self.fetch_player_stats(username, account_type)
            
            if stats is None:
                display_username = self.format_username_for_display(username)
                embed = discord.Embed(
                    title="❌ Player Not Found",
                    description=f"Could not find player '{display_username}' on the OSRS Hiscores.\n\n"
                               f"Use quotes for usernames with spaces: `.osrs boss \"tcp syn ack\"`",
                    color=0xFF0000
                )
                await ctx.send(embed=embed)
                return
            
            display_username = self.format_username_for_display(username)
            url_username = self.format_username_for_url(username)
            
            embed = discord.Embed(
                title=f"🐉 Boss Kill Counts for {display_username}",
                color=0x8B4513,
                url=f"https://secure.runescape.com/m=hiscore_oldschool/hiscorepersonal?user1={url_username}"
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

    @osrs_stats.command(name="goals", aliases=["goal", "targets", "target"])
    async def osrs_goals(self, ctx, *, args: str):
        """
        Calculate XP requirements and time estimates to reach target levels in OSRS.
        
        Provides detailed goal analysis including XP needed, progress percentage,
        and realistic time estimates for different training methods.
        
        Use quotes around usernames with spaces: .osrs goals "tcp syn ack" 99 woodcutting
        
        Examples:
        .osrs goals "tcp syn ack" 99 woodcutting
        .osrs goals "tcp syn ack" 90
        .osrs goals Zezima 99 attack
        .osrs targets Zezima 85 slayer
        .osrs goal Zezima 126 (virtual levels supported)
        
        Features:
        • XP calculations for levels 1-126
        • Progress tracking and percentages
        • Time estimates for popular training methods
        • Virtual level support (99+)
        • Milestone tracking (1M, 5M, 10M, etc.)
        """
        # Parse arguments
        parts = []
        current_part = ""
        in_quotes = False
        
        for char in args:
            if char == '"' and not in_quotes:
                in_quotes = True
            elif char == '"' and in_quotes:
                in_quotes = False
                if current_part:
                    parts.append(current_part)
                    current_part = ""
            elif char == ' ' and not in_quotes:
                if current_part:
                    parts.append(current_part)
                    current_part = ""
            else:
                current_part += char
        
        if current_part:
            parts.append(current_part)
        
        if len(parts) < 2:
            await ctx.send("❌ Please provide username and target level!\n\n**Usage:**\n`.osrs goals \"username with spaces\" 99 skill`\n`.osrs goals username_without_spaces 99 skill`")
            return
        
        username = parts[0]
        try:
            target_level = int(parts[1])
        except ValueError:
            await ctx.send("❌ Target level must be a number!")
            return
        
        skill = parts[2].lower().capitalize() if len(parts) > 2 else "Overall"
        
        # Skill mapping
        skill_mapping = {
            "Hp": "Hitpoints", "Wc": "Woodcutting", "Fm": "Firemaking", "Rc": "Runecraft",
            "Att": "Attack", "Str": "Strength", "Def": "Defence", "Range": "Ranged",
            "Mage": "Magic", "Pray": "Prayer", "Cook": "Cooking", "Fish": "Fishing",
            "Fletch": "Fletching", "Craft": "Crafting", "Smith": "Smithing", "Mine": "Mining",
            "Herb": "Herblore", "Agil": "Agility", "Thiev": "Thieving", "Slay": "Slayer",
            "Farm": "Farming", "Hunt": "Hunter", "Con": "Construction", "Overall": "Overall"
        }
        skill = skill_mapping.get(skill, skill)
        
        if target_level < 1 or target_level > 126:
            await ctx.send("❌ Target level must be between 1 and 126.")
            return
        
        async with ctx.typing():
            stats = await self.fetch_player_stats(username)
            
            if stats is None:
                display_username = self.format_username_for_display(username)
                embed = discord.Embed(
                    title="❌ Player Not Found",
                    description=f"Could not find player '{display_username}' on the OSRS Hiscores.\n\n"
                               f"Use quotes for usernames with spaces: `.osrs goals \"tcp syn ack\" 99 woodcutting`",
                    color=0xFF0000
                )
                await ctx.send(embed=embed)
                return
            
            if skill not in stats["skills"]:
                await ctx.send(f"❌ Invalid skill: {skill}")
                return
            
            current_level = stats["skills"][skill]["level"]
            current_xp = stats["skills"][skill]["xp"]
            display_username = self.format_username_for_display(username)
            
            if current_level >= target_level:
                await ctx.send(f"🎉 {display_username} has already achieved level {target_level} {skill}!")
                return
            
            # Calculate target XP
            if target_level <= 99:
                target_xp = self.xp_table[target_level - 1]
            else:
                target_xp = self.virtual_levels.get(target_level, 200000000)
            
            xp_needed = target_xp - current_xp
            
            embed = discord.Embed(
                title=f"🎯 Goal Calculator: {skill} Level {target_level}",
                description=f"Analysis for {display_username}",
                color=0x00FF00
            )
            
            embed.add_field(
                name="📊 Current Progress",
                value=f"**Current Level:** {current_level}\n"
                      f"**Current XP:** {self.format_number(current_xp)}\n"
                      f"**Target Level:** {target_level}\n"
                      f"**Target XP:** {self.format_number(target_xp)}",
                inline=True
            )
            
            embed.add_field(
                name="🎯 Requirements",
                value=f"**XP Needed:** {self.format_number(xp_needed)}\n"
                      f"**Levels to Gain:** {target_level - current_level}\n"
                      f"**Progress:** {(current_xp/target_xp)*100:.1f}%",
                inline=True
            )
            
            # Add time estimates based on common XP rates
            xp_rates = self.get_skill_xp_rates(skill)
            if xp_rates:
                time_estimates = ""
                for method, rate in xp_rates.items():
                    hours = xp_needed / rate
                    if hours < 24:
                        time_estimates += f"**{method}:** {hours:.1f} hours\n"
                    else:
                        days = hours / 24
                        time_estimates += f"**{method}:** {days:.1f} days\n"
                
                embed.add_field(
                    name="⏱️ Time Estimates",
                    value=time_estimates,
                    inline=False
                )
            
            await ctx.send(embed=embed)

    def get_skill_xp_rates(self, skill: str) -> dict:
        """Get common XP rates for different training methods."""
        xp_rates = {
            "Woodcutting": {"Yews": 35000, "Magic logs": 50000, "Redwoods": 65000},
            "Mining": {"Iron ore": 40000, "Granite": 60000, "MLM": 30000},
            "Fishing": {"Barbarian": 50000, "Monkfish": 35000, "Sharks": 25000},
            "Cooking": {"Wines": 400000, "Karambwans": 200000, "Sharks": 150000},
            "Firemaking": {"Wintertodt": 300000, "Yew logs": 200000, "Magic logs": 150000},
            "Fletching": {"Darts": 800000, "Longbows": 300000, "Arrows": 500000},
            "Crafting": {"Superglass": 300000, "D'hide bodies": 250000, "Gems": 200000},
            "Smithing": {"Blast Furnace": 350000, "Cannonballs": 25000, "Platebodies": 200000}
        }
        
        return xp_rates.get(skill, {})

    @osrs_stats.command(name="help", aliases=["commands", "info"])
    async def osrs_help(self, ctx):
        """
        Display comprehensive help information for all OSRS commands and subcommands.
        
        Complete guide covering all available commands, usage examples, account types,
        skill abbreviations, and important notes about usernames with spaces.
        
        Shows detailed information about:
        • Main stats command (.osrs)
        • All subcommands (skill, boss, goals, help)
        • Account type support
        • Username formatting rules
        • Skill abbreviations
        • Usage examples for every command
        """
        embed = discord.Embed(
            title="🗡️ OSRS Stats Commands - Complete Guide",
            description="Comprehensive guide for all OSRS statistics commands and subcommands",
            color=0x8B4513
        )
        
        embed.add_field(
            name="📊 Main Command",
            value="**`.osrs \"username\" [account_type]`**\n"
                  "**Aliases:** `.osrsstats`, `.oldschool`\n"
                  "Get complete player analysis with recommendations\n\n"
                  "**Examples:**\n"
                  "`.osrs \"tcp syn ack\"` - Normal account\n"
                  "`.osrs \"tcp syn ack\" ironman` - Ironman account\n"
                  "`.osrs Zezima` - No spaces, no quotes needed\n"
                  "`.osrs Zezima hardcore` - Hardcore ironman",
            inline=False
        )
        
        embed.add_field(
            name="🎯 Skill Analysis Subcommand",
            value="**`.osrs skill \"username\" <skill> [account_type]`**\n"
                  "**Aliases:** `.osrs sk`, `.osrs skills`\n"
                  "Get detailed skill information and progress tracking\n\n"
                  "**Examples:**\n"
                  "`.osrs skill \"tcp syn ack\" woodcutting`\n"
                  "`.osrs sk \"tcp syn ack\" attack ironman`\n"
                  "`.osrs skill Zezima mining`\n"
                  "`.osrs skills Zezima hp ultimate`",
            inline=False
        )
        
        embed.add_field(
            name="🐉 Boss Kill Subcommand",
            value="**`.osrs boss \"username\" [account_type]`**\n"
                  "**Aliases:** `.osrs bosses`, `.osrs pvm`\n"
                  "Display all boss kill counts and PvM statistics\n\n"
                  "**Examples:**\n"
                  "`.osrs boss \"tcp syn ack\"`\n"
                  "`.osrs bosses \"tcp syn ack\" ironman`\n"
                  "`.osrs boss Zezima`\n"
                  "`.osrs pvm Zezima hardcore`",
            inline=False
        )
        
        embed.add_field(
            name="🏆 Goal Calculator Subcommand",
            value="**`.osrs goals \"username\" <target_level> [skill]`**\n"
                  "**Aliases:** `.osrs goal`, `.osrs targets`, `.osrs target`\n"
                  "Calculate XP and time estimates to reach target levels\n\n"
                  "**Examples:**\n"
                  "`.osrs goals \"tcp syn ack\" 99 woodcutting`\n"
                  "`.osrs goals \"tcp syn ack\" 90` - Overall level\n"
                  "`.osrs targets Zezima 99 attack`\n"
                  "`.osrs goal Zezima 85 slayer`",
            inline=False
        )
        
        embed.add_field(
            name="ℹ️ Help Subcommand",
            value="**`.osrs help`**\n"
                  "**Aliases:** `.osrs commands`, `.osrs info`\n"
                  "Display this comprehensive help guide\n\n"
                  "**Examples:**\n"
                  "`.osrs help` - Show this help menu\n"
                  "`.osrs commands` - Alternative help command\n"
                  "`.osrs info` - Another help alias",
            inline=False
        )
        
        embed.add_field(
            name="⚙️ Account Types",
            value="• `normal` - Regular accounts (default)\n"
                  "• `ironman` - Ironman accounts\n"
                  "• `hardcore` - Hardcore ironman accounts\n"
                  "• `ultimate` - Ultimate ironman accounts\n"
                  "• `deadman` - Deadman mode accounts\n"
                  "• `seasonal` - Seasonal/League accounts",
            inline=True
        )
        
        embed.add_field(
            name="🔤 Skill Abbreviations",
            value="• `hp` = Hitpoints • `wc` = Woodcutting\n"
                  "• `fm` = Firemaking • `rc` = Runecraft\n"
                  "• `att` = Attack • `str` = Strength\n"
                  "• `def` = Defence • `range` = Ranged\n"
                  "• `mage` = Magic • `pray` = Prayer\n"
                  "• `cook` = Cooking • `fish` = Fishing\n"
                  "• `fletch` = Fletching • `craft` = Crafting\n"
                  "• `smith` = Smithing • `mine` = Mining\n"
                  "• `herb` = Herblore • `agil` = Agility\n"
                  "• `thiev` = Thieving • `slay` = Slayer\n"
                  "• `farm` = Farming • `hunt` = Hunter\n"
                  "• `con` = Construction",
            inline=True
        )
        
        embed.add_field(
            name="⚠️ Important Usage Notes",
            value="• **Always use quotes around usernames with spaces!**\n"
                  "• All commands are now subcommands of `.osrs`\n"
                  "• Account type is optional (defaults to normal)\n"
                  "• Skill abbreviations work in all skill commands\n"
                  "• Case doesn't matter for usernames or skills\n"
                  "• All subcommands support multiple aliases",
            inline=False
        )
        
        embed.add_field(
            name="🔍 Username Format Examples",
            value="**✅ Correct Usage:**\n"
                  "• `.osrs \"tcp syn ack\"` - Spaces with quotes\n"
                  "• `.osrs skill \"iron man btw\" woodcutting` - Spaces with quotes\n"
                  "• `.osrs boss Zezima` - No spaces, no quotes needed\n"
                  "• `.osrs goals Lynx_Titan 99 rc` - Underscores work fine\n\n"
                  "**❌ Incorrect Usage:**\n"
                  "• `.osrs tcp syn ack` - Missing quotes\n"
                  "• `.osrs skill tcp syn ack woodcutting` - Missing quotes",
            inline=False
        )
        
        embed.add_field(
            name="🚀 Quick Start Guide",
            value="**New to OSRS commands? Start here:**\n"
                  "1. `.osrs \"your username\"` - Get your stats overview\n"
                  "2. `.osrs skill \"your username\" attack` - Check a specific skill\n"
                  "3. `.osrs boss \"your username\"` - See your boss kills\n"
                  "4. `.osrs goals \"your username\" 99 woodcutting` - Set a goal\n"
                  "5. `.osrs help` - View this help anytime",
            inline=False
        )
        
        embed.set_footer(text="💡 Pro Tip: All commands are now organized under .osrs - use subcommands for specific features!")
        
        await ctx.send(embed=embed)

def setup(bot: Red):
    bot.add_cog(OSRSStats(bot))