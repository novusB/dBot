import asyncio
import discord
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Union
from redbot.core import commands, Config, checks
from redbot.core.utils.chat_formatting import humanize_timedelta
from redbot.core.bot import Red

# Try to import modlog, but make it optional
try:
    from redbot.core import modlog
    MODLOG_AVAILABLE = True
except ImportError:
    MODLOG_AVAILABLE = False
    modlog = None

class Toxic(commands.Cog):
    """Vote-based kick/ban system for server members with matching roles."""

    def __init__(self, bot: Red):
        self.bot = bot
        # Use unique letter-based identifier
        self.config = Config.get_conf(self, identifier=2847592847592847, force_registration=True)
        
        default_guild = {
            "vote_duration": 300,  # 5 minutes
            "votes_needed": 3,
            "ban_mode": False,  # False = kick, True = ban
            "vote_emojis": ["👍", "👎", "🤷"],
            "enabled": True,
            "log_channel": None,
            "anonvote": False
        }
        
        self.config.register_guild(**default_guild)
        self.active_votes: Dict[int, Dict[int, dict]] = {}
        self._casetype_registered = False
        self._registration_task = None
        self._is_loaded = False
        
        # Unique instance identifier to prevent duplicates
        self._instance_id = f"toxic_instance_{id(self)}"
        
        # Only register casetypes if modlog is available
        if MODLOG_AVAILABLE:
            self._registration_task = asyncio.create_task(self._register_casetypes())
        
        self._is_loaded = True

    async def _register_casetypes(self):
        """Register custom case types for modlog integration."""
        if not MODLOG_AVAILABLE or self._casetype_registered:
            return
            
        # Wait for bot to be ready
        await self.bot.wait_until_ready()
        
        try:
            # Register vote kick case type
            await modlog.register_casetype(
                name="toxicvotekick",
                default_setting=True,
                image="🗳️",
                case_str="Toxic Vote Kick"
            )
            
            # Register vote ban case type
            await modlog.register_casetype(
                name="toxicvoteban", 
                default_setting=True,
                image="🗳️",
                case_str="Toxic Vote Ban"
            )
            
            self._casetype_registered = True
            
        except RuntimeError:
            # Case types already registered
            self._casetype_registered = True
        except Exception as e:
            # Log any other errors but don't fail
            print(f"Toxic cog: Failed to register modlog case types: {e}")

    def cog_unload(self):
        """Clean up active votes and tasks when cog is unloaded."""
        self._is_loaded = False
        
        # Cancel registration task if still running
        if self._registration_task and not self._registration_task.done():
            self._registration_task.cancel()
        
        # Clear active votes
        self.active_votes.clear()
        
        # Reset registration flag
        self._casetype_registered = False

    def _has_matching_roles(self, member1: discord.Member, member2: discord.Member) -> bool:
        """Check if two members have identical roles (excluding @everyone)."""
        roles1 = {role.id for role in member1.roles if role != member1.guild.default_role}
        roles2 = {role.id for role in member2.roles if role != member2.guild.default_role}
        return roles1 == roles2

    async def _create_modlog_case(self, guild: discord.Guild, action: str, moderator: discord.Member, 
                                 user: discord.Member, reason: str, vote_data: dict):
        """Create a modlog case for the vote action."""
        # Skip if modlog not available
        if not MODLOG_AVAILABLE:
            return
        
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
        
            # Get additional info
            additional_info = vote_data.get("additional_info", {})
        
            # Format role information
            shared_roles_str = ", ".join([role.name for role in additional_info.get("shared_roles", [])]) or "None"
            target_roles_str = ", ".join([role.name for role in additional_info.get("target_roles", [])]) or "None"
            initiator_roles_str = ", ".join([role.name for role in additional_info.get("initiator_roles", [])]) or "None"
        
            # Create comprehensive reason for modlog
            detailed_reason = (
                f"Toxic vote {action} initiated by {vote_data['initiator']} | "
                f"Channel: #{additional_info.get('vote_channel', {}).name if additional_info.get('vote_channel') else 'Unknown'} | "
                f"Request time: {additional_info.get('request_timestamp', 'Unknown').strftime('%Y-%m-%d %H:%M:%S UTC') if additional_info.get('request_timestamp') else 'Unknown'} | "
                f"Votes: {yes_votes} yes, {no_votes} no, {abstain_votes} abstain | "
                f"Target roles: {target_roles_str} | "
                f"Shared roles: {shared_roles_str} | "
                f"Original reason: {reason}"
            )
        
            # Determine case type
            case_type = "toxicvoteban" if action == "ban" else "toxicvotekick"
        
            # Create the modlog case
            await modlog.create_case(
                bot=self.bot,
                guild=guild,
                created_at=datetime.now(timezone(timedelta(hours=-5))),
                action_type=case_type,
                user=user,
                moderator=moderator,
                reason=detailed_reason,
                until=None,
                channel=None
            )
        
        except Exception as e:
            # Log error but don't fail the action
            print(f"Toxic cog: Failed to create modlog case: {e}")

    async def _log_vote_result(self, guild: discord.Guild, embed: discord.Embed, vote_data: dict):
        """Log vote result to configured log channel with detailed information."""
        log_channel_id = vote_data["config"]["log_channel"]
        if not log_channel_id:
            return
        
        log_channel = guild.get_channel(log_channel_id)
        if not log_channel:
            return
        
        try:
            # Get additional info
            additional_info = vote_data.get("additional_info", {})
        
            # Create detailed log embed
            detailed_embed = discord.Embed(
                title="🗳️ Detailed Vote Log",
                color=embed.color,
                timestamp=datetime.now(timezone(timedelta(hours=-5)))
            )
        
            # Basic vote information
            detailed_embed.add_field(
                name="📊 Vote Results",
                value=f"**Target:** {vote_data['target'].mention}\n"
                      f"**Initiator:** {vote_data['initiator'].mention}\n"
                      f"**Reason:** {vote_data['reason']}\n"
                      f"**Action:** {'Ban' if vote_data['config']['ban_mode'] else 'Kick'}\n"
                      f"**Result:** {'✅ PASSED' if vote_data.get('vote_passed', False) else '❌ FAILED'}",
                inline=False
            )
        
            # Request details
            request_time = additional_info.get("request_timestamp")
            vote_channel = additional_info.get("vote_channel")
            detailed_embed.add_field(
                name="📍 Request Details",
                value=f"**Channel:** {vote_channel.mention if vote_channel else 'Unknown'}\n"
                      f"**Request Time:** {request_time.strftime('%Y-%m-%d %H:%M:%S UTC') if request_time else 'Unknown'}\n"
                      f"**Vote Duration:** {humanize_timedelta(seconds=vote_data['config']['vote_duration'])}",
                inline=True
            )
        
            # Target user information
            detailed_embed.add_field(
                name="👤 Target User Info",
                value=f"**Username:** {vote_data['target'].name}\n"
                      f"**User ID:** {vote_data['target'].id}",
                inline=True
            )
        
            # Vote statistics
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
            
            detailed_embed.add_field(
                name="📈 Vote Statistics",
                value=f"**Yes Votes:** {yes_votes}\n"
                      f"**No Votes:** {no_votes}\n"
                      f"**Abstain Votes:** {abstain_votes}\n"
                      f"**Votes Required:** {vote_data['config']['votes_needed']}\n"
                      f"**Total Participants:** {len(vote_data.get('voters', set()))}",
                inline=True
            )
        
            # System information
            detailed_embed.add_field(
                name="⚙️ System Info",
                value=f"**Anonymous Mode:** {'Enabled' if vote_data['config']['anonvote'] else 'Disabled'}\n"
                      f"**Vote ID:** {vote_data.get('instance_id', 'Unknown')}\n"
                      f"**Cog Version:** Toxic v2.0",
                inline=True
            )
        
            # Add footer with additional context
            detailed_embed.set_footer(
                text=f"Vote processed at {datetime.now(timezone(timedelta(hours=-5))).strftime('%Y-%m-%d %H:%M:%S UTC')} | "
                     f"Modlog: {'Available' if MODLOG_AVAILABLE else 'Unavailable'}"
            )
        
            await log_channel.send(embed=detailed_embed)
        
        except discord.HTTPException as e:
            print(f"Toxic cog: Failed to send detailed log: {e}")

    @commands.group(name="toxic", invoke_without_command=True)
    @commands.guild_only()
    async def toxic_main(self, ctx):
        """Toxic vote system commands."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @toxic_main.command(name="vote")
    @commands.guild_only()
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def vote_member(self, ctx, member: discord.Member, *, reason: str = "No reason provided"):
        """Initiate a vote to kick/ban a member with matching roles."""
        
        # Check if cog is properly loaded
        if not self._is_loaded:
            return await ctx.send("❌ Toxic cog is not properly loaded. Please contact an administrator.")
        
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
            return await ctx.send("❌ You can only vote against members with identical roles!")
        
        # Check for existing vote
        guild_votes = self.active_votes.get(ctx.guild.id, {})
        if member.id in guild_votes:
            return await ctx.send(f"❌ Vote already active for {member.mention}!")
        
        # Get settings
        config = await self.config.guild(ctx.guild).all()
        
        # Get detailed information for logging
        vote_channel = ctx.channel
        initiator_roles = [role for role in ctx.author.roles if role != ctx.guild.default_role]
        target_roles = [role for role in member.roles if role != member.guild.default_role]
        shared_roles = [role for role in initiator_roles if role in target_roles]

        # Store additional logging info
        additional_info = {
            "vote_channel": vote_channel,
            "initiator_roles": initiator_roles,
            "target_roles": target_roles,
            "shared_roles": shared_roles,
            "request_timestamp": datetime.now(timezone(timedelta(hours=-5)))
        }
        
        action = "ban" if config["ban_mode"] else "kick"
        
        # Create vote embed
        embed = discord.Embed(
            title=f"🗳️ Vote to {action.title()} {member.display_name}",
            description=f"**Target:** {member.mention}\n"
                       f"**Initiated by:** {'Anonymous' if config['anonvote'] else ctx.author.mention}\n"
                       f"**Reason:** {reason}\n"
                       f"**Action:** {action.title()}\n\n"
                       f"**Votes needed:** {config['votes_needed']}\n"
                       f"**Time remaining:** <t:{int((datetime.now(timezone(timedelta(hours=-5))) + timedelta(seconds=config['vote_duration'])).timestamp())}:R>",
            color=discord.Color.orange(),
            timestamp=datetime.now(timezone(timedelta(hours=-5)))
        )
        
        embed.add_field(
            name="How to vote:",
            value=f"{config['vote_emojis'][0]} - Yes\n"
                  f"{config['vote_emojis'][1]} - No\n"
                  f"{config['vote_emojis'][2]} - Abstain",
            inline=False
        )
        
        footer_text = "Vote results will be logged"
        if MODLOG_AVAILABLE:
            footer_text += " in the moderation log"
        if config["log_channel"]:
            footer_text += " and custom log channel"
        embed.set_footer(text=footer_text)
        
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
            "start_time": datetime.now(timezone(timedelta(hours=-5))),
            "config": config,
            "voters": set(),
            "processed": False,
            "instance_id": self._instance_id,
            "additional_info": additional_info
        }
        
        # Start timer
        asyncio.create_task(self._handle_vote_timer(ctx.guild, member.id))

    async def _handle_vote_timer(self, guild: discord.Guild, member_id: int):
        """Handle vote timer and execution."""
        # Check if this instance should handle this vote
        vote_data = self.active_votes.get(guild.id, {}).get(member_id)
        if (not vote_data or 
            vote_data.get("processed", False) or 
            vote_data.get("instance_id") != self._instance_id):
        return
        
        await asyncio.sleep(vote_data["config"]["vote_duration"])
        
        # Double-check vote still exists and belongs to this instance
        if (guild.id not in self.active_votes or 
            member_id not in self.active_votes[guild.id] or 
            self.active_votes[guild.id][member_id].get("processed", False) or
            self.active_votes[guild.id][member_id].get("instance_id") != self._instance_id):
        return
    
        # Process the vote result (timer completion)
        await self._process_vote_result(guild, member_id, early_completion=False)

    async def _process_vote_result(self, guild: discord.Guild, member_id: int, early_completion: bool = False):
        """Process vote results and execute actions."""
        # Check if this instance should handle this vote
        vote_data = self.active_votes.get(guild.id, {}).get(member_id)
        if (not vote_data or 
            vote_data.get("processed", False) or 
            vote_data.get("instance_id") != self._instance_id):
            return
    
        # Mark as processed to prevent duplicates
        if not vote_data.get("processed", False):
            vote_data["processed"] = True
    
        try:
            message = await vote_data["message"].channel.fetch_message(vote_data["message"].id)
        except discord.NotFound:
            # Clean up if message is gone
            if guild.id in self.active_votes and member_id in self.active_votes[guild.id]:
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
        embed = discord.Embed(
            title="🗳️ Vote Results" + (" (Early Completion)" if early_completion else ""), 
            timestamp=datetime.now(timezone(timedelta(hours=-5)))
        )
        embed.add_field(name="Target", value=vote_data["target"].mention, inline=True)

        # Only show initiator if anonymous voting is disabled
        if not vote_data["config"]["anonvote"]:
            embed.add_field(name="Initiator", value=vote_data["initiator"].mention, inline=True)
        else:
            embed.add_field(name="Initiator", value="Anonymous", inline=True)

        embed.add_field(name="Reason", value=vote_data["reason"], inline=False)
        embed.add_field(name="Yes", value=str(yes_votes), inline=True)
        embed.add_field(name="No", value=str(no_votes), inline=True)
        embed.add_field(name="Abstain", value=str(abstain_votes), inline=True)
    
        # Execute action if vote passed
        votes_needed = vote_data["config"]["votes_needed"]
        vote_passed = yes_votes >= votes_needed and yes_votes > no_votes
    
        # Store vote result for logging
        vote_data["vote_passed"] = vote_passed
    
        if vote_passed:
            action = "ban" if vote_data["config"]["ban_mode"] else "kick"
        
            try:
                # Perform the action
                if vote_data["config"]["ban_mode"]:
                    await vote_data["target"].ban(reason=f"Toxic vote ban: {vote_data['reason']}")
                else:
                    await vote_data["target"].kick(reason=f"Toxic vote kick: {vote_data['reason']}")
            
                # Create modlog case if available
                if MODLOG_AVAILABLE:
                    await self._create_modlog_case(
                        guild=guild,
                        action=action,
                        moderator=guild.me,
                        user=vote_data["target"],
                        reason=vote_data["reason"],
                        vote_data=vote_data
                    )
            
                embed.color = discord.Color.red()
                result_text = f"✅ Vote passed! Member {action}ed."
                if early_completion:
                    result_text += f"\n🚀 Vote completed early ({yes_votes}/{votes_needed} votes reached)"
                if MODLOG_AVAILABLE:
                    result_text += "\n📋 Action logged in moderation log."
                embed.add_field(name="Result", value=result_text, inline=False)
            
            except discord.Forbidden:
                embed.color = discord.Color.orange()
                embed.add_field(name="Result", value=f"❌ No permission to {action}!", inline=False)
            except Exception as e:
                embed.color = discord.Color.orange()
                embed.add_field(name="Result", value=f"❌ Failed to {action}: {e}", inline=False)
        else:
            embed.color = discord.Color.green()
            result_text = "❌ Vote failed."
            if early_completion:
                result_text += f"\n⏰ Vote ended early (insufficient support)"
            embed.add_field(name="Result", value=result_text, inline=False)
    
        # Update message with results
        try:
            await message.edit(embed=embed)
            await message.clear_reactions()
        except discord.HTTPException:
            pass
    
        # Log result to custom log channel
        await self._log_vote_result(guild, embed, vote_data)
    
        # Cleanup
        if guild.id in self.active_votes and member_id in self.active_votes[guild.id]:
            del self.active_votes[guild.id][member_id]

    @toxic_main.command(name="cancel")
    @commands.guild_only()
    async def cancel_vote(self, ctx, member: discord.Member):
        """Cancel an active vote."""
        guild_votes = self.active_votes.get(ctx.guild.id, {})
        
        if member.id not in guild_votes:
            return await ctx.send(f"❌ No active vote for {member.mention}.")
        
        vote_data = guild_votes[member.id]
        
        # Check if already processed
        if vote_data.get("processed", False):
            return await ctx.send(f"❌ Vote for {member.mention} has already concluded.")
        
        # Permission check
        if (ctx.author != vote_data["initiator"] and 
            not ctx.author.guild_permissions.kick_members and 
            ctx.author != ctx.guild.owner):
            return await ctx.send("❌ Only the initiator or moderators can cancel votes.")
        
        # Mark as processed to prevent timer from running
        vote_data["processed"] = True
        
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

    @toxic_main.command(name="list")
    @commands.guild_only()
    async def list_active_votes(self, ctx):
        """List active votes."""
        guild_votes = self.active_votes.get(ctx.guild.id, {})
        
        # Filter out processed votes
        active_votes = {k: v for k, v in guild_votes.items() if not v.get("processed", False)}
        
        if not active_votes:
            return await ctx.send("✅ No active votes.")
        
        embed = discord.Embed(title="🗳️ Active Votes", color=discord.Color.blue())
        
        for member_id, vote_data in active_votes.items():
            time_left = (vote_data["start_time"] + 
                        timedelta(seconds=vote_data["config"]["vote_duration"]) - 
                        datetime.now(timezone(timedelta(hours=-5))))
            
            embed.add_field(
                name=vote_data["target"].display_name,
                value=f"By: {vote_data['initiator'].mention}\n"
                      f"Time left: {humanize_timedelta(timedelta=time_left)}\n"
                      f"Votes needed: {vote_data['config']['votes_needed']}",
                inline=True
            )
        
        await ctx.send(embed=embed)

    @toxic_main.group(name="config", invoke_without_command=True)
    @commands.guild_only()
    async def toxic_config(self, ctx):
        """Configure the toxic vote system."""
        # Check permissions first and provide feedback
        if not (ctx.author.guild_permissions.administrator or 
                ctx.author.guild_permissions.manage_guild or
                await self.bot.is_owner(ctx.author)):
            embed = discord.Embed(
                title="❌ Insufficient Permissions",
                description="You need **Administrator** permissions or **Manage Server** permissions to configure the toxic vote system.",
                color=discord.Color.red()
            )
            embed.add_field(
                name="Required Permissions",
                value="• Administrator\n• Manage Server",
                inline=True
            )
            embed.add_field(
                name="Available Commands",
                value="• `[p]toxic vote @user reason`\n• `[p]toxic list`\n• `[p]toxic cancel @user` (if you started the vote)",
                inline=True
            )
            return await ctx.send(embed=embed)
    
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @toxic_config.command(name="duration")
    @checks.admin_or_permissions(manage_guild=True)
    async def set_vote_duration(self, ctx, time: str):
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
        
        try:
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
        except ValueError:
            return await ctx.send("❌ Invalid time format. Use: `30s`, `5m`, `1h`, or just `300`")
        
        # Validate range
        if not 30 <= seconds <= 86400:  # 30 seconds to 24 hours
            return await ctx.send("❌ Duration must be between 30 seconds and 24 hours.")
        
        await self.config.guild(ctx.guild).vote_duration.set(seconds)
        await ctx.send(f"✅ Vote duration set to **{humanize_timedelta(seconds=seconds)}**.")

    @toxic_config.command(name="votes", aliases=["threshold"])
    @checks.admin_or_permissions(manage_guild=True)
    async def set_votes_required(self, ctx, count: int):
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

    @toxic_config.command(name="mode", aliases=["action", "punishment"])
    @checks.admin_or_permissions(manage_guild=True)
    async def set_punishment_mode(self, ctx, mode: str):
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
            description=f"Vote punishment set to: **{mode.upper()}**",
            color=discord.Color.green() if mode == "kick" else discord.Color.red()
        )
        
        if MODLOG_AVAILABLE:
            embed.description += f"\n📋 All {mode} actions will be logged in the moderation log."
        
        if mode == "ban":
            embed.add_field(
                name="⚠️ Important",
                value="Successful votes will now **permanently ban** users!",
                inline=False
            )
        
        await ctx.send(embed=embed)

    @toxic_config.command(name="toggle", aliases=["enable", "disable"])
    @checks.admin_or_permissions(manage_guild=True)
    async def toggle_toxic_system(self, ctx, state: str = None):
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
                      "• All actions will be logged appropriately",
                inline=False
            )
        
        await ctx.send(embed=embed)

    @toxic_config.command(name="logchannel", aliases=["logs"])
    @checks.admin_or_permissions(manage_guild=True)
    async def set_custom_log_channel(self, ctx, channel: Optional[discord.TextChannel] = None):
        """
        Set a channel where vote results are logged.
        
        Usage:
        - `[p]toxic config logchannel #channel` - Set log channel
        - `[p]toxic config logchannel` - Disable logging
        """
        if channel is None:
            await self.config.guild(ctx.guild).log_channel.set(None)
            msg = "✅ Vote result logging **disabled**."
            if MODLOG_AVAILABLE:
                msg += "\n📋 Actions will still be logged in the moderation log."
            await ctx.send(msg)
        else:
            # Check if bot can send messages in the channel
            if not channel.permissions_for(ctx.guild.me).send_messages:
                return await ctx.send(f"❌ I don't have permission to send messages in {channel.mention}!")
            
            await self.config.guild(ctx.guild).log_channel.set(channel.id)
            
            # Send test message
            embed = discord.Embed(
                title="📋 Vote Logging Enabled",
                description="This channel will now receive detailed vote result logs.",
                color=discord.Color.blue()
            )
            if MODLOG_AVAILABLE:
                embed.description += "\n\n**Note:** Kick/ban actions are also logged in the moderation log."
            
            await channel.send(embed=embed)
            
            msg = f"✅ Vote results will be logged to {channel.mention}."
            if MODLOG_AVAILABLE:
                msg += "\n📋 Actions will also continue to be logged in the moderation log."
            await ctx.send(msg)

    @toxic_config.command(name="preset")
    @checks.admin_or_permissions(manage_guild=True)
    async def apply_config_preset(self, ctx, preset_name: str):
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
                       f"**Mode:** {'Ban' if preset['ban_mode'] else 'Kick'}",
            color=discord.Color.orange()
        )
        
        if MODLOG_AVAILABLE:
            embed.description += f"\n\n📋 All actions will be logged in the moderation log."
        
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
            description=f"**'{preset_name.title()}'** configuration is now active!",
            color=discord.Color.green()
        )
        
        if MODLOG_AVAILABLE:
            embed.description += f"\n\n📋 All moderation actions will be logged in the moderation log."
        
        await ctx.send(embed=embed)

    @toxic_config.command(name="view", aliases=["show", "status"])
    async def view_toxic_config(self, ctx):
        """View current configuration settings."""
        config = await self.config.guild(ctx.guild).all()
        
        embed = discord.Embed(
            title="🔧 Toxic Vote System Configuration",
            color=discord.Color.blue() if config["enabled"] else discord.Color.red(),
            timestamp=datetime.now(timezone(timedelta(hours=-5)))
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
        embed.add_field(name="Log Channel", value=log_text, inline=True)
        
        # Vote emojis
        emoji_text = f"📊 {' '.join(config['vote_emojis'])}"
        embed.add_field(name="Vote Emojis", value=emoji_text, inline=True)

        # Anonymous voting
        anon_text = "🔍 **ENABLED**" if config["anonvote"] else "👁️ **DISABLED**"
        embed.add_field(name="Anonymous Voting", value=anon_text, inline=True)
        
        # Modlog integration info
        if MODLOG_AVAILABLE:
            embed.add_field(
                name="📋 Moderation Log",
                value="✅ **Integrated** - All actions logged automatically",
                inline=False
            )
        else:
            embed.add_field(
                name="📋 Moderation Log",
                value="❌ **Not Available** - Using log channel only",
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

    @toxic_config.command(name="reset")
    @checks.admin_or_permissions(manage_guild=True)
    async def reset_toxic_config(self, ctx):
        """Reset all configuration to default values."""
        embed = discord.Embed(
            title="⚠️ Reset Configuration?",
            description="This will reset **ALL** toxic vote settings to default values:\n\n"
                       "• Duration: 5 minutes\n"
                       "• Votes needed: 3\n"
                       "• Mode: Kick\n"
                       "• System: Enabled\n"
                       "• Log channel: Disabled\n"
                       "• Anonymous voting: Disabled",
            color=discord.Color.red()
        )
        
        if MODLOG_AVAILABLE:
            embed.description += f"\n\n📋 Modlog integration will remain active."
        
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
        
        msg = "✅ Configuration reset to default values!"
        if MODLOG_AVAILABLE:
            msg += "\n📋 Modlog integration remains active."
        await ctx.send(msg)

    @toxic_config.command(name="anonvote")
    @checks.admin_or_permissions(manage_guild=True)
    async def toggle_anonymous_voting(self, ctx, state: str = None):
        """
        Enable or disable anonymous voting.
        
        When enabled, the initiator's name will be hidden in the vote display,
        but will still be logged for accountability.
        
        Usage: 
        - `[p]toxic config anonvote` - Toggle current state
        - `[p]toxic config anonvote on` - Force enable
        - `[p]toxic config anonvote off` - Force disable
        """
        current = await self.config.guild(ctx.guild).anonvote()
    
        if state is None:
            new_state = not current
        elif state.lower() in ["on", "enable", "enabled", "true", "yes"]:
            new_state = True
        elif state.lower() in ["off", "disable", "disabled", "false", "no"]:
            new_state = False
        else:
            return await ctx.send("❌ Invalid state. Use `on`, `off`, or leave empty to toggle.")
    
        await self.config.guild(ctx.guild).anonvote.set(new_state)
    
        status = "**ENABLED** ✅" if new_state else "**DISABLED** ❌"
        color = discord.Color.green() if new_state else discord.Color.red()
    
        embed = discord.Embed(
            title="🔍 Anonymous Voting",
            description=f"Anonymous voting is now {status}",
            color=color
        )
    
        if new_state:
            embed.add_field(
                name="How it works",
                value="• Vote initiator's name will be hidden in vote displays\n"
                      "• Initiator is still logged for accountability\n"
                      "• Only server admins can see who started votes",
                inline=False
            )
    
        await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: Union[discord.Member, discord.User]):
        """Handle vote reactions."""
        if (user.bot or 
            not reaction.message.guild or 
            not self._is_loaded):
            return
        
        guild_votes = self.active_votes.get(reaction.message.guild.id, {})
    
        # Find matching vote message
        for member_id, vote_data in guild_votes.items():
            if (vote_data["message"].id == reaction.message.id and 
                not vote_data.get("processed", False) and
                vote_data.get("instance_id") == self._instance_id):
            
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
            
                # Check if vote threshold has been reached
                try:
                    message = await reaction.message.channel.fetch_message(reaction.message.id)
                    yes_votes = no_votes = abstain_votes = 0
                
                    for msg_reaction in message.reactions:
                        emoji_str = str(msg_reaction.emoji)
                        if emoji_str == emojis[0]:
                            yes_votes = msg_reaction.count - 1
                        elif emoji_str == emojis[1]:
                            no_votes = msg_reaction.count - 1
                        elif emoji_str == emojis[2]:
                            abstain_votes = msg_reaction.count - 1
                
                    votes_needed = vote_data["config"]["votes_needed"]
                
                    # If vote threshold reached, process immediately
                    if yes_votes >= votes_needed and yes_votes > no_votes:
                        # Mark as processed to prevent timer from also processing
                        vote_data["processed"] = True
                    
                        # Process the vote immediately
                        asyncio.create_task(self._process_vote_result(reaction.message.guild, member_id, early_completion=True))
                    
                except discord.NotFound:
                    # Message was deleted, clean up
                    if reaction.message.guild.id in self.active_votes and member_id in self.active_votes[reaction.message.guild.id]:
                        del self.active_votes[reaction.message.guild.id][member_id]
                except Exception as e:
                    print(f"Toxic cog: Error checking vote threshold: {e}")
            
                break

    @toxic_main.error
    async def toxic_error_handler(self, ctx, error):
        """Handle errors for the toxic command group."""
        if isinstance(error, commands.CheckFailure):
            if (ctx.invoked_subcommand and 
                hasattr(ctx.invoked_subcommand, 'parent') and 
                ctx.invoked_subcommand.parent and
                ctx.invoked_subcommand.parent.name == "config"):
                
                embed = discord.Embed(
                    title="❌ Insufficient Permissions",
                    description="You need **Administrator** permissions or **Manage Server** permissions to configure the toxic vote system.",
                    color=discord.Color.red()
                )
                embed.add_field(
                    name="Required Permissions",
                    value="• Administrator\n• Manage Server",
                    inline=True
                )
                embed.add_field(
                    name="Available Commands",
                    value="• `[p]toxic vote @user reason`\n• `[p]toxic list`\n• `[p]toxic cancel @user` (if you started the vote)",
                    inline=True
                )
                await ctx.send(embed=embed)
            else:
                # Handle other permission errors for non-config commands
                await ctx.send("❌ You don't have permission to use this command.")
        else:
            # Re-raise other errors to be handled by Red's default error handler
            raise error