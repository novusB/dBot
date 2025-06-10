import asyncio
import discord
from datetime import datetime, timedelta
from typing import Optional, Dict, Union
from redbot.core import commands, Config, checks, modlog
from redbot.core.utils.chat_formatting import humanize_timedelta
from redbot.core.bot import Red

class Toxic(commands.Cog):
    """Vote-based kick/ban system for server members with matching roles."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        
        default_guild = {
            "vote_duration": 300,  # 5 minutes
            "votes_needed": 3,
            "ban_mode": False,  # False = kick, True = ban
            "vote_emojis": ["👍", "👎", "🤷"],
            "enabled": True,
            "log_channel": None
        }
        
        self.config.register_guild(**default_guild)
        self.active_votes: Dict[int, Dict[int, dict]] = {}
        
        # Register modlog case types
        self._register_casetypes()

    def _register_casetypes(self):
        """Register custom case types for modlog integration."""
        try:
            # Register vote kick case type
            modlog.register_casetype(
                name="votekick",
                default_setting=True,
                image="🗳️",
                case_str="Vote Kick"
            )
            
            # Register vote ban case type
            modlog.register_casetype(
                name="voteban", 
                default_setting=True,
                image="🗳️",
                case_str="Vote Ban"
            )
        except RuntimeError:
            # Case types already registered
            pass

    def cog_unload(self):
        """Clean up active votes when cog is unloaded."""
        self.active_votes.clear()

    def _has_matching_roles(self, member1: discord.Member, member2: discord.Member) -> bool:
        """Check if two members have identical roles (excluding @everyone)."""
        roles1 = {role.id for role in member1.roles if role != member1.guild.default_role}
        roles2 = {role.id for role in member2.roles if role != member2.guild.default_role}
        return roles1 == roles2

    async def _create_modlog_case(self, guild: discord.Guild, action: str, moderator: discord.Member, 
                                 user: discord.Member, reason: str, vote_data: dict):
        """Create a modlog case for the vote action."""
        try:
            # Count final votes for the case
            message = vote_data["message"]
            try:
                message = await message.channel.fetch_message(message.id)
                yes_votes = no_votes = abstain_votes = 0
                emojis = vote_data["config"]["vote_emojis"]
                
                for reaction in message.reactions:
                    emoji_str = str(reaction.emoji)
                    if emoji_str == emojis[0]:
                        yes_votes = reaction.count - 1
                    elif emoji_str == emojis[1]:
                        no_votes = reaction.count - 1
                    elif emoji_str == emojis[2]:
                        abstain_votes = reaction.count - 1
            except discord.NotFound:
                yes_votes = no_votes = abstain_votes = 0
            
            # Create detailed reason for modlog
            detailed_reason = (
                f"Vote {action} initiated by {vote_data['initiator']} | "
                f"Votes: {yes_votes} yes, {no_votes} no, {abstain_votes} abstain | "
                f"Original reason: {reason}"
            )
            
            # Determine case type
            case_type = "voteban" if action == "ban" else "votekick"
            
            # Create the modlog case
            await modlog.create_case(
                bot=self.bot,
                guild=guild,
                created_at=datetime.utcnow(),
                action_type=case_type,
                user=user,
                moderator=moderator,
                reason=detailed_reason,
                until=None,
                channel=None
            )
            
        except Exception as e:
            # Log error but don't fail the action
            print(f"Failed to create modlog case: {e}")

    @commands.group(name="toxic")
    @commands.guild_only()
    async def toxic(self, ctx):
        """Toxic vote system commands."""
        pass

    @toxic.command(name="vote")
    @commands.guild_only()
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def vote_kick(self, ctx, member: discord.Member, *, reason: str = "No reason provided"):
        """Initiate a vote to kick/ban a toxic member."""
        
        # Basic checks
        if not await self.config.guild(ctx.guild).enabled():
            return await ctx.send("❌ The toxic vote system is disabled.")
        
        if member == ctx.author:
            return await ctx.send("❌ You cannot vote against yourself!")
        
        if member == ctx.guild.owner or await self.bot.is_owner(member):
            return await ctx.send("❌ Cannot vote against server/bot owners!")
        
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.send("❌ Cannot vote against members with equal or higher roles!")
        
        # Role matching check (bypass for server owner and kick permissions)
        if (not self._has_matching_roles(ctx.author, member) and 
            ctx.author != ctx.guild.owner and 
            not ctx.author.guild_permissions.kick_members):
            return await ctx.send("❌ You can only vote against toxic players who play the same games as you!")
        
        # Check for existing vote
        guild_votes = self.active_votes.get(ctx.guild.id, {})
        if member.id in guild_votes:
            return await ctx.send(f"❌ Vote already active for {member.mention}!")
        
        # Get settings
        config = await self.config.guild(ctx.guild).all()
        action = "ban" if config["ban_mode"] else "kick"
        
        # Create vote embed
        embed = discord.Embed(
            title=f"🗳️ Vote to {action.title()} {member.display_name}",
            description=f"**Target:** {member.mention}\n"
                       f"**Initiated by:** {ctx.author.mention}\n"
                       f"**Reason:** {reason}\n"
                       f"**Action:** {action.title()}\n\n"
                       f"**Votes needed:** {config['votes_needed']}\n"
                       f"**Time remaining:** {humanize_timedelta(seconds=config['vote_duration'])}",
            color=discord.Color.orange(),
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(
            name="How to vote:",
            value=f"{config['vote_emojis'][0]} - Yes\n"
                  f"{config['vote_emojis'][1]} - No\n"
                  f"{config['vote_emojis'][2]} - Abstain",
            inline=False
        )
        
        embed.set_footer(text="This action will be logged in the moderation log if successful")
        
        vote_message = await ctx.send(embed=embed)
        
        # Add reactions
        for emoji in config["vote_emojis"]:
            try:
                await vote_message.add_reaction(emoji)
            except discord.HTTPException:
                pass
        
        # Store vote data
        if ctx.guild.id not in self.active_votes:
            self.active_votes[ctx.guild.id] = {}
        
        self.active_votes[ctx.guild.id][member.id] = {
            "message": vote_message,
            "target": member,
            "initiator": ctx.author,
            "reason": reason,
            "start_time": datetime.utcnow(),
            "config": config,
            "voters": set()
        }
        
        # Start timer
        asyncio.create_task(self._handle_vote_timer(ctx.guild, member.id))

    async def _handle_vote_timer(self, guild: discord.Guild, member_id: int):
        """Handle vote timer and execution."""
        vote_data = self.active_votes.get(guild.id, {}).get(member_id)
        if not vote_data:
            return
            
        await asyncio.sleep(vote_data["config"]["vote_duration"])
        
        # Check if vote still exists
        if guild.id not in self.active_votes or member_id not in self.active_votes[guild.id]:
            return
        
        vote_data = self.active_votes[guild.id][member_id]
        
        try:
            message = await vote_data["message"].channel.fetch_message(vote_data["message"].id)
        except discord.NotFound:
            del self.active_votes[guild.id][member_id]
            return
        
        # Count votes
        yes_votes = no_votes = abstain_votes = 0
        emojis = vote_data["config"]["vote_emojis"]
        
        for reaction in message.reactions:
            emoji_str = str(reaction.emoji)
            if emoji_str == emojis[0]:
                yes_votes = reaction.count - 1
            elif emoji_str == emojis[1]:
                no_votes = reaction.count - 1
            elif emoji_str == emojis[2]:
                abstain_votes = reaction.count - 1
        
        # Create result embed
        embed = discord.Embed(title="🗳️ Vote Results", timestamp=datetime.utcnow())
        embed.add_field(name="Target", value=vote_data["target"].mention, inline=True)
        embed.add_field(name="Initiator", value=vote_data["initiator"].mention, inline=True)
        embed.add_field(name="Reason", value=vote_data["reason"], inline=False)
        embed.add_field(name="Yes", value=str(yes_votes), inline=True)
        embed.add_field(name="No", value=str(no_votes), inline=True)
        embed.add_field(name="Abstain", value=str(abstain_votes), inline=True)
        
        # Execute action if vote passed
        votes_needed = vote_data["config"]["votes_needed"]
        if yes_votes >= votes_needed and yes_votes > no_votes:
            action = "ban" if vote_data["config"]["ban_mode"] else "kick"
            
            try:
                # Perform the action
                if vote_data["config"]["ban_mode"]:
                    await vote_data["target"].ban(reason=f"Vote ban: {vote_data['reason']}")
                else:
                    await vote_data["target"].kick(reason=f"Vote kick: {vote_data['reason']}")
                
                # Create modlog case
                await self._create_modlog_case(
                    guild=guild,
                    action=action,
                    moderator=guild.me,  # Bot is the moderator
                    user=vote_data["target"],
                    reason=vote_data["reason"],
                    vote_data=vote_data
                )
                
                embed.color = discord.Color.red()
                embed.add_field(
                    name="Result", 
                    value=f"✅ Vote passed! Member {action}ed.\n📋 Action logged in moderation log.", 
                    inline=False
                )
                
            except discord.Forbidden:
                embed.color = discord.Color.orange()
                embed.add_field(name="Result", value=f"❌ No permission to {action}!", inline=False)
            except Exception as e:
                embed.color = discord.Color.orange()
                embed.add_field(name="Result", value=f"❌ Failed to {action}: {e}", inline=False)
        else:
            embed.color = discord.Color.green()
            embed.add_field(name="Result", value="❌ Vote failed.", inline=False)
        
        await message.edit(embed=embed)
        await message.clear_reactions()
        
        # Log result to custom log channel (in addition to modlog)
        log_channel_id = vote_data["config"]["log_channel"]
        if log_channel_id:
            log_channel = guild.get_channel(log_channel_id)
            if log_channel:
                await log_channel.send(embed=embed)
        
        # Cleanup
        del self.active_votes[guild.id][member_id]

    @toxic.command(name="cancel")
    @commands.guild_only()
    async def cancel_vote(self, ctx, member: discord.Member):
        """Cancel an active vote."""
        guild_votes = self.active_votes.get(ctx.guild.id, {})
        
        if member.id not in guild_votes:
            return await ctx.send(f"❌ No active vote for {member.mention}.")
        
        vote_data = guild_votes[member.id]
        
        # Permission check
        if (ctx.author != vote_data["initiator"] and 
            not ctx.author.guild_permissions.kick_members and 
            ctx.author != ctx.guild.owner):
            return await ctx.send("❌ Only the initiator or moderators can cancel votes.")
        
        # Cancel vote
        try:
            embed = discord.Embed(
                title="🗳️ Vote Cancelled",
                description=f"Vote for {member.mention} cancelled by {ctx.author.mention}.",
                color=discord.Color.red()
            )
            await vote_data["message"].edit(embed=embed)
            await vote_data["message"].clear_reactions()
        except discord.HTTPException:
            pass
        
        del self.active_votes[ctx.guild.id][member.id]
        await ctx.send(f"✅ Vote for {member.mention} cancelled.")

    @toxic.command(name="list")
    @commands.guild_only()
    async def list_votes(self, ctx):
        """List active votes."""
        guild_votes = self.active_votes.get(ctx.guild.id, {})
        
        if not guild_votes:
            return await ctx.send("✅ No active votes.")
        
        embed = discord.Embed(title="🗳️ Active Votes", color=discord.Color.blue())
        
        for member_id, vote_data in guild_votes.items():
            time_left = (vote_data["start_time"] + 
                        timedelta(seconds=vote_data["config"]["vote_duration"]) - 
                        datetime.utcnow())
            
            embed.add_field(
                name=vote_data["target"].display_name,
                value=f"By: {vote_data['initiator'].mention}\n"
                      f"Time left: {humanize_timedelta(timedelta=time_left)}\n"
                      f"Votes needed: {vote_data['config']['votes_needed']}",
                inline=True
            )
        
        await ctx.send(embed=embed)

    @toxic.group(name="config")
    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    async def config(self, ctx):
        """Configure the toxic vote system."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @config.command(name="duration")
    @checks.admin_or_permissions(manage_guild=True)
    async def set_duration(self, ctx, time: str):
        """
        Set vote duration. 
        
        Examples:
        - `30s` or `30` = 30 seconds
        - `5m` = 5 minutes  
        - `1h` = 1 hour
        - `90s` = 1 minute 30 seconds
        
        Range: 30 seconds to 24 hours
        """
        # Parse time string
        time = time.lower().strip()
        
        # Handle different time formats
        if time.endswith('s'):
            seconds = int(time[:-1])
        elif time.endswith('m'):
            seconds = int(time[:-1]) * 60
        elif time.endswith('h'):
            seconds = int(time[:-1]) * 3600
        elif time.isdigit():
            seconds = int(time)
        else:
            return await ctx.send("❌ Invalid time format. Use: `30s`, `5m`, `1h`, or just `300`")
        
        # Validate range
        if not 30 <= seconds <= 86400:  # 30 seconds to 24 hours
            return await ctx.send("❌ Duration must be between 30 seconds and 24 hours.")
        
        await self.config.guild(ctx.guild).vote_duration.set(seconds)
        await ctx.send(f"✅ Vote duration set to **{humanize_timedelta(seconds=seconds)}**.")

    @config.command(name="votes", aliases=["threshold"])
    @checks.admin_or_permissions(manage_guild=True)
    async def set_votes_needed(self, ctx, count: int):
        """
        Set how many YES votes are needed for a vote to pass.
        
        Range: 1-50 votes
        Recommended: 3-5 for small servers, 5-10 for large servers
        """
        if not 1 <= count <= 50:
            return await ctx.send("❌ Vote count must be between 1 and 50.")
        
        await self.config.guild(ctx.guild).votes_needed.set(count)
        
        # Provide recommendations based on server size
        member_count = ctx.guild.member_count
        if member_count < 50 and count > 5:
            recommendation = "💡 **Tip:** For smaller servers, 3-5 votes usually work better."
        elif member_count > 200 and count < 5:
            recommendation = "💡 **Tip:** For larger servers, consider 5-10 votes to prevent abuse."
        else:
            recommendation = ""
        
        await ctx.send(f"✅ Votes needed set to **{count}**.\n{recommendation}")

    @config.command(name="mode", aliases=["action", "punishment"])
    @checks.admin_or_permissions(manage_guild=True)
    async def set_mode(self, ctx, mode: str):
        """
        Set the punishment type: 'kick' or 'ban'
        
        - **kick**: Removes user from server (they can rejoin)
        - **ban**: Permanently bans user from server
        
        ⚠️ **Warning:** Ban mode is more severe and permanent!
        """
        mode = mode.lower()
        if mode not in ["kick", "ban"]:
            return await ctx.send("❌ Mode must be either `kick` or `ban`.")
        
        # Confirmation for ban mode
        if mode == "ban":
            embed = discord.Embed(
                title="⚠️ Confirm Ban Mode",
                description="You're about to enable **BAN MODE**.\n\n"
                           "This means successful votes will **permanently ban** users from the server.\n"
                           "Are you sure you want to continue?",
                color=discord.Color.red()
            )
            
            confirm_msg = await ctx.send(embed=embed)
            await confirm_msg.add_reaction("✅")
            await confirm_msg.add_reaction("❌")
            
            def check(reaction, user):
                return (user == ctx.author and 
                       str(reaction.emoji) in ["✅", "❌"] and 
                       reaction.message.id == confirm_msg.id)
            
            try:
                reaction, user = await self.bot.wait_for('reaction_add', timeout=30.0, check=check)
                if str(reaction.emoji) == "❌":
                    return await ctx.send("❌ Ban mode setup cancelled.")
            except asyncio.TimeoutError:
                return await ctx.send("❌ Confirmation timed out. Ban mode not enabled.")
        
        await self.config.guild(ctx.guild).ban_mode.set(mode == "ban")
        
        embed = discord.Embed(
            title="✅ Vote Mode Updated",
            description=f"Vote punishment set to: **{mode.upper()}**\n\n"
                       f"📋 All {mode} actions will be logged in the moderation log.",
            color=discord.Color.green() if mode == "kick" else discord.Color.red()
        )
        
        if mode == "ban":
            embed.add_field(
                name="⚠️ Important",
                value="Successful votes will now **permanently ban** users!",
                inline=False
            )
        
        await ctx.send(embed=embed)

    @config.command(name="toggle", aliases=["enable", "disable"])
    @checks.admin_or_permissions(manage_guild=True)
    async def toggle_system(self, ctx, state: str = None):
        """
        Enable or disable the toxic vote system.
        
        Usage: 
        - `[p]toxic config toggle` - Toggle current state
        - `[p]toxic config toggle on` - Force enable
        - `[p]toxic config toggle off` - Force disable
        """
        current = await self.config.guild(ctx.guild).enabled()
        
        if state is None:
            new_state = not current
        elif state.lower() in ["on", "enable", "enabled", "true", "yes"]:
            new_state = True
        elif state.lower() in ["off", "disable", "disabled", "false", "no"]:
            new_state = False
        else:
            return await ctx.send("❌ Invalid state. Use `on`, `off`, or leave empty to toggle.")
        
        await self.config.guild(ctx.guild).enabled.set(new_state)
        
        status = "**ENABLED** ✅" if new_state else "**DISABLED** ❌"
        color = discord.Color.green() if new_state else discord.Color.red()
        
        embed = discord.Embed(
            title="🔧 System Status Updated",
            description=f"Toxic vote system is now {status}",
            color=color
        )
        
        if new_state:
            embed.add_field(
                name="Next Steps",
                value="• Users can now start votes with `[p]toxic vote @user reason`\n"
                      "• Check settings with `[p]toxic config view`\n"
                      "• All actions will be logged in the moderation log",
                inline=False
            )
        
        await ctx.send(embed=embed)

    @config.command(name="logchannel", aliases=["logs"])
    @checks.admin_or_permissions(manage_guild=True)
    async def set_log_channel(self, ctx, channel: Optional[discord.TextChannel] = None):
        """
        Set an additional channel where vote results are logged.
        
        Note: All kick/ban actions are automatically logged in the moderation log.
        This setting adds an extra log channel for vote-specific information.
        
        Usage:
        - `[p]toxic config logchannel #channel` - Set additional log channel
        - `[p]toxic config logchannel` - Disable additional logging
        """
        if channel is None:
            await self.config.guild(ctx.guild).log_channel.set(None)
            await ctx.send("✅ Additional vote result logging **disabled**.\n"
                          "📋 Actions will still be logged in the moderation log.")
        else:
            # Check if bot can send messages in the channel
            if not channel.permissions_for(ctx.guild.me).send_messages:
                return await ctx.send(f"❌ I don't have permission to send messages in {channel.mention}!")
            
            await self.config.guild(ctx.guild).log_channel.set(channel.id)
            
            # Send test message
            embed = discord.Embed(
                title="📋 Additional Vote Logging Enabled",
                description="This channel will now receive detailed vote result logs.\n\n"
                           "**Note:** Kick/ban actions are also logged in the moderation log.",
                color=discord.Color.blue()
            )
            await channel.send(embed=embed)
            await ctx.send(f"✅ Additional vote results will be logged to {channel.mention}.\n"
                          "📋 Actions will also continue to be logged in the moderation log.")

    @config.command(name="preset")
    @checks.admin_or_permissions(manage_guild=True)
    async def config_preset(self, ctx, preset_name: str):
        """
        Apply a configuration preset.
        
        Available presets:
        - `strict` - Short duration, high vote threshold, ban mode
        - `moderate` - Balanced settings for most servers  
        - `lenient` - Longer duration, lower threshold, kick only
        - `small` - Optimized for small servers (<50 members)
        - `large` - Optimized for large servers (>200 members)
        """
        presets = {
            "strict": {
                "vote_duration": 180,  # 3 minutes
                "votes_needed": 5,
                "ban_mode": True,
                "description": "Short votes, high threshold, permanent bans"
            },
            "moderate": {
                "vote_duration": 300,  # 5 minutes
                "votes_needed": 3,
                "ban_mode": False,
                "description": "Balanced settings for most servers"
            },
            "lenient": {
                "vote_duration": 600,  # 10 minutes
                "votes_needed": 2,
                "ban_mode": False,
                "description": "Longer votes, lower threshold, kicks only"
            },
            "small": {
                "vote_duration": 300,  # 5 minutes
                "votes_needed": 2,
                "ban_mode": False,
                "description": "Optimized for small servers"
            },
            "large": {
                "vote_duration": 240,  # 4 minutes
                "votes_needed": 7,
                "ban_mode": False,
                "description": "Optimized for large servers"
            }
        }
        
        preset_name = preset_name.lower()
        if preset_name not in presets:
            preset_list = "\n".join([f"• `{name}` - {data['description']}" for name, data in presets.items()])
            return await ctx.send(f"❌ Invalid preset. Available presets:\n{preset_list}")
        
        preset = presets[preset_name]
        
        # Confirmation
        embed = discord.Embed(
            title=f"🔧 Apply '{preset_name.title()}' Preset?",
            description=f"**{preset['description']}**\n\n"
                       f"**Duration:** {humanize_timedelta(seconds=preset['vote_duration'])}\n"
                       f"**Votes needed:** {preset['votes_needed']}\n"
                       f"**Mode:** {'Ban' if preset['ban_mode'] else 'Kick'}\n\n"
                       f"📋 All actions will be logged in the moderation log.",
            color=discord.Color.orange()
        )
        
        confirm_msg = await ctx.send(embed=embed)
        await confirm_msg.add_reaction("✅")
        await confirm_msg.add_reaction("❌")
        
        def check(reaction, user):
            return (user == ctx.author and 
                   str(reaction.emoji) in ["✅", "❌"] and 
                   reaction.message.id == confirm_msg.id)
        
        try:
            reaction, user = await self.bot.wait_for('reaction_add', timeout=30.0, check=check)
            if str(reaction.emoji) == "❌":
                return await ctx.send("❌ Preset application cancelled.")
        except asyncio.TimeoutError:
            return await ctx.send("❌ Confirmation timed out.")
        
        # Apply preset
        guild_config = self.config.guild(ctx.guild)
        await guild_config.vote_duration.set(preset["vote_duration"])
        await guild_config.votes_needed.set(preset["votes_needed"])
        await guild_config.ban_mode.set(preset["ban_mode"])
        
        embed = discord.Embed(
            title="✅ Preset Applied Successfully",
            description=f"**'{preset_name.title()}'** configuration is now active!\n\n"
                       f"📋 All moderation actions will be logged in the moderation log.",
            color=discord.Color.green()
        )
        
        await ctx.send(embed=embed)

    @config.command(name="view", aliases=["show", "status"])
    async def view_config(self, ctx):
        """View current configuration settings."""
        config = await self.config.guild(ctx.guild).all()
        
        embed = discord.Embed(
            title="🔧 Toxic Vote System Configuration",
            color=discord.Color.blue() if config["enabled"] else discord.Color.red(),
            timestamp=datetime.utcnow()
        )
        
        # Status
        status = "🟢 **ENABLED**" if config["enabled"] else "🔴 **DISABLED**"
        embed.add_field(name="System Status", value=status, inline=True)
        
        # Mode with warning for ban
        mode_text = "🔨 **KICK**" if not config["ban_mode"] else "⚠️ **BAN**"
        embed.add_field(name="Punishment Mode", value=mode_text, inline=True)
        
        # Duration
        duration_text = f"⏱️ **{humanize_timedelta(seconds=config['vote_duration'])}**"
        embed.add_field(name="Vote Duration", value=duration_text, inline=True)
        
        # Votes needed
        votes_text = f"🗳️ **{config['votes_needed']} votes**"
        embed.add_field(name="Votes Required", value=votes_text, inline=True)
        
        # Log channel
        log_channel = ctx.guild.get_channel(config["log_channel"]) if config["log_channel"] else None
        log_text = f"📋 {log_channel.mention}" if log_channel else "📋 **Disabled**"
        embed.add_field(name="Additional Logs", value=log_text, inline=True)
        
        # Vote emojis
        emoji_text = f"📊 {' '.join(config['vote_emojis'])}"
        embed.add_field(name="Vote Emojis", value=emoji_text, inline=True)
        
        # Modlog integration info
        embed.add_field(
            name="📋 Moderation Log",
            value="✅ **Integrated** - All actions logged automatically",
            inline=False
        )
        
        # Add recommendations
        member_count = ctx.guild.member_count
        recommendations = []
        
        if member_count < 50 and config["votes_needed"] > 5:
            recommendations.append("• Consider lowering vote threshold for smaller server")
        elif member_count > 200 and config["votes_needed"] < 5:
            recommendations.append("• Consider raising vote threshold for larger server")
            
        if config["ban_mode"]:
            recommendations.append("• ⚠️ Ban mode is enabled - votes will permanently ban users!")
            
        if recommendations:
            embed.add_field(
                name="💡 Recommendations",
                value="\n".join(recommendations),
                inline=False
            )
        
        # Quick setup help
        embed.add_field(
            name="🚀 Quick Setup",
            value="Use `[p]toxic config preset moderate` for balanced settings\n"
                  "Or `[p]toxic config preset small/large` based on server size",
            inline=False
        )
        
        await ctx.send(embed=embed)

    @config.command(name="reset")
    @checks.admin_or_permissions(manage_guild=True)
    async def reset_config(self, ctx):
        """Reset all configuration to default values."""
        embed = discord.Embed(
            title="⚠️ Reset Configuration?",
            description="This will reset **ALL** toxic vote settings to default values:\n\n"
                       "• Duration: 5 minutes\n"
                       "• Votes needed: 3\n"
                       "• Mode: Kick\n"
                       "• System: Enabled\n"
                       "• Additional log channel: Disabled\n\n"
                       "📋 Modlog integration will remain active.",
            color=discord.Color.red()
        )
        
        confirm_msg = await ctx.send(embed=embed)
        await confirm_msg.add_reaction("✅")
        await confirm_msg.add_reaction("❌")
        
        def check(reaction, user):
            return (user == ctx.author and 
                   str(reaction.emoji) in ["✅", "❌"] and 
                   reaction.message.id == confirm_msg.id)
        
        try:
            reaction, user = await self.bot.wait_for('reaction_add', timeout=30.0, check=check)
            if str(reaction.emoji) == "❌":
                return await ctx.send("❌ Configuration reset cancelled.")
        except asyncio.TimeoutError:
            return await ctx.send("❌ Confirmation timed out.")
        
        # Reset to defaults
        await self.config.guild(ctx.guild).clear()
        await ctx.send("✅ Configuration reset to default values!\n"
                      "📋 Modlog integration remains active.")

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: Union[discord.Member, discord.User]):
        """Handle vote reactions."""
        if user.bot or not reaction.message.guild:
            return
            
        guild_votes = self.active_votes.get(reaction.message.guild.id, {})
        
        # Find matching vote message
        for member_id, vote_data in guild_votes.items():
            if vote_data["message"].id == reaction.message.id:
                emojis = vote_data["config"]["vote_emojis"]
                
                # Remove invalid reactions
                if str(reaction.emoji) not in emojis:
                    try:
                        await reaction.message.remove_reaction(reaction.emoji, user)
                    except discord.HTTPException:
                        pass
                    return
                
                # Prevent double voting
                if user.id in vote_data["voters"]:
                    try:
                        await reaction.message.remove_reaction(reaction.emoji, user)
                    except discord.HTTPException:
                        pass
                    return
                
                # Record vote and remove other reactions from this user
                vote_data["voters"].add(user.id)
                for emoji in emojis:
                    if str(reaction.emoji) != emoji:
                        try:
                            await reaction.message.remove_reaction(emoji, user)
                        except discord.HTTPException:
                            pass
                break