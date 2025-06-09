import asyncio
import discord
from datetime import datetime, timedelta
from typing import Optional, Dict, Set, Union
from redbot.core import commands, Config, checks
from redbot.core.utils.chat_formatting import humanize_timedelta
from redbot.core.utils.predicates import MessagePredicate
from redbot.core.bot import Red
from .utils import format_time_remaining, has_matching_roles
# We're not actually using views yet, but we'll import it to prevent the error
from . import views

class Toxicity(commands.Cog):
    """
    Vote-based kick/ban system for server members with matching roles.
    """

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        
        # Default settings
        default_guild = {
            "vote_duration": 300,  # 5 minutes in seconds
            "votes_needed": 3,     # Number of votes needed to pass
            "ban_mode": False,     # False = kick, True = ban
            "vote_emojis": ["👍", "👎", "🤷"],  # Yes, No, Abstain
            "enabled": True,
            "log_channel": None
        }
        
        self.config.register_guild(**default_guild)
        
        # Track active votes: guild_id -> {user_id: vote_data}
        self.active_votes: Dict[int, Dict[int, dict]] = {}
        
        # Start task to clean up expired votes
        self.cleanup_task = self.bot.loop.create_task(self._cleanup_expired_votes())

    def cog_unload(self):
        """Clean up when cog is unloaded."""
        if self.cleanup_task:
            self.cleanup_task.cancel()

    async def _cleanup_expired_votes(self):
        """Task to clean up expired votes."""
        await self.bot.wait_until_ready()
        while self == self.bot.get_cog("Toxicity"):
            try:
                for guild_id in list(self.active_votes.keys()):
                    for member_id in list(self.active_votes.get(guild_id, {}).keys()):
                        vote_data = self.active_votes[guild_id][member_id]
                        expiry_time = vote_data["start_time"] + timedelta(seconds=vote_data["duration"])
                        
                        # If vote has expired but wasn't processed
                        if datetime.utcnow() > expiry_time:
                            guild = self.bot.get_guild(guild_id)
                            if guild:
                                await self._handle_vote_timer(guild, member_id)
            except Exception as e:
                pass  # Prevent the task from dying
                
            await asyncio.sleep(60)  # Check every minute

    @commands.group(name="toxic")
    @commands.guild_only()
    async def toxic(self, ctx):
        """Toxic vote system commands."""
        pass

    @toxic.command(name="vote")
    @commands.guild_only()
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def vote_kick(self, ctx, member: discord.Member, *, reason: str = "No reason provided"):
        """
        Initiate a vote to kick/ban a member.
        You must have the exact same roles as the target member.
        """
        if not await self.config.guild(ctx.guild).enabled():
            return await ctx.send("❌ The toxic vote system is disabled in this server.")
        
        # Check if user is trying to vote on themselves
        if member == ctx.author:
            return await ctx.send("❌ You cannot vote to kick yourself!")
        
        # Check if target is bot owner or server owner
        if member == ctx.guild.owner or await self.bot.is_owner(member):
            return await ctx.send("❌ You cannot vote to kick the server owner or bot owner!")
        
        # Check if target has higher roles than author
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.send("❌ You cannot vote to kick someone with equal or higher roles!")
        
        # Check if roles match exactly (excluding @everyone)
        if not has_matching_roles(ctx.author, member) and ctx.author != ctx.guild.owner and not ctx.author.guild_permissions.kick_members:
            return await ctx.send("❌ You can only vote to kick members with the exact same roles as you!")
        
        # Check if there's already an active vote for this member
        guild_votes = self.active_votes.get(ctx.guild.id, {})
        if member.id in guild_votes:
            return await ctx.send(f"❌ There is already an active vote for {member.mention}!")
        
        # Get configuration
        vote_duration = await self.config.guild(ctx.guild).vote_duration()
        votes_needed = await self.config.guild(ctx.guild).votes_needed()
        ban_mode = await self.config.guild(ctx.guild).ban_mode()
        emojis = await self.config.guild(ctx.guild).vote_emojis()
        
        action = "ban" if ban_mode else "kick"
        
        # Create vote embed
        embed = discord.Embed(
            title=f"🗳️ Vote to {action.title()} {member.display_name}",
            description=f"**Target:** {member.mention}\n"
                       f"**Initiated by:** {ctx.author.mention}\n"
                       f"**Reason:** {reason}\n"
                       f"**Action:** {action.title()}\n\n"
                       f"**Votes needed:** {votes_needed}\n"
                       f"**Time remaining:** {format_time_remaining(vote_duration)}",
            color=discord.Color.orange(),
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(
            name="How to vote:",
            value=f"{emojis[0]} - Yes, {action} them\n"
                  f"{emojis[1]} - No, don't {action}\n"
                  f"{emojis[2]} - Abstain",
            inline=False
        )
        
        vote_message = await ctx.send(embed=embed)
        
        # Add reaction emojis
        for emoji in emojis:
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
            "duration": vote_duration,
            "votes_needed": votes_needed,
            "ban_mode": ban_mode,
            "emojis": emojis,
            "voters": set()  # Track who has voted to prevent double voting
        }
        
        # Start vote timer
        self.bot.loop.create_task(self._handle_vote_timer(ctx.guild, member.id))

    async def _handle_vote_timer(self, guild: discord.Guild, member_id: int):
        """Handle the vote timer and execute action if needed."""
        # Wait for the vote duration
        if guild.id in self.active_votes and member_id in self.active_votes[guild.id]:
            await asyncio.sleep(self.active_votes[guild.id][member_id]["duration"])
        
        # Check if vote is still active
        if guild.id not in self.active_votes or member_id not in self.active_votes[guild.id]:
            return
        
        vote_data = self.active_votes[guild.id][member_id]
        message = vote_data["message"]
        
        try:
            # Refresh message to get current reactions
            message = await message.channel.fetch_message(message.id)
        except discord.NotFound:
            # Message was deleted, cancel vote
            del self.active_votes[guild.id][member_id]
            return
        
        # Count votes
        yes_votes = 0
        no_votes = 0
        abstain_votes = 0
        
        for reaction in message.reactions:
            if str(reaction.emoji) == vote_data["emojis"][0]:  # Yes
                yes_votes = reaction.count - 1  # Subtract bot's reaction
            elif str(reaction.emoji) == vote_data["emojis"][1]:  # No
                no_votes = reaction.count - 1
            elif str(reaction.emoji) == vote_data["emojis"][2]:  # Abstain
                abstain_votes = reaction.count - 1
        
        # Create result embed
        embed = discord.Embed(
            title="🗳️ Vote Results",
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(name="Target", value=vote_data["target"].mention, inline=True)
        embed.add_field(name="Initiator", value=vote_data["initiator"].mention, inline=True)
        embed.add_field(name="Reason", value=vote_data["reason"], inline=False)
        embed.add_field(name="Yes Votes", value=str(yes_votes), inline=True)
        embed.add_field(name="No Votes", value=str(no_votes), inline=True)
        embed.add_field(name="Abstain Votes", value=str(abstain_votes), inline=True)
        
        # Determine if vote passed
        if yes_votes >= vote_data["votes_needed"] and yes_votes > no_votes:
            # Vote passed - execute action
            action = "ban" if vote_data["ban_mode"] else "kick"
            
            try:
                if vote_data["ban_mode"]:
                    await vote_data["target"].ban(reason=f"Vote ban: {vote_data['reason']}")
                else:
                    await vote_data["target"].kick(reason=f"Vote kick: {vote_data['reason']}")
                
                embed.color = discord.Color.red()
                embed.add_field(
                    name="Result", 
                    value=f"✅ Vote passed! {vote_data['target'].mention} has been {action}ed.", 
                    inline=False
                )
                
            except discord.Forbidden:
                embed.color = discord.Color.orange()
                embed.add_field(
                    name="Result", 
                    value=f"❌ Vote passed but I don't have permission to {action} {vote_data['target'].mention}.", 
                    inline=False
                )
            except discord.HTTPException as e:
                embed.color = discord.Color.orange()
                embed.add_field(
                    name="Result", 
                    value=f"❌ Vote passed but failed to {action}: {str(e)}", 
                    inline=False
                )
        else:
            # Vote failed
            embed.color = discord.Color.green()
            embed.add_field(
                name="Result", 
                value="❌ Vote failed - not enough votes or more 'No' votes.", 
                inline=False
            )
        
        await message.edit(embed=embed)
        await message.clear_reactions()
        
        # Log the result
        log_channel_id = await self.config.guild(guild).log_channel()
        if log_channel_id:
            log_channel = guild.get_channel(log_channel_id)
            if log_channel:
                await log_channel.send(embed=embed)
        
        # Clean up
        del self.active_votes[guild.id][member_id]

    @toxic.command(name="cancel")
    @commands.guild_only()
    async def cancel_vote(self, ctx, member: discord.Member):
        """Cancel an active vote (only initiator, mods, or admins can cancel)."""
        guild_votes = self.active_votes.get(ctx.guild.id, {})
        
        if member.id not in guild_votes:
            return await ctx.send(f"❌ No active vote found for {member.mention}.")
        
        vote_data = guild_votes[member.id]
        
        # Check permissions
        if (ctx.author != vote_data["initiator"] and 
            not ctx.author.guild_permissions.kick_members and 
            ctx.author != ctx.guild.owner):
            return await ctx.send("❌ You can only cancel votes you initiated, or you need kick permissions.")
        
        # Cancel the vote
        try:
            embed = discord.Embed(
                title="🗳️ Vote Cancelled",
                description=f"The vote for {member.mention} has been cancelled by {ctx.author.mention}.",
                color=discord.Color.red(),
                timestamp=datetime.utcnow()
            )
            await vote_data["message"].edit(embed=embed)
            await vote_data["message"].clear_reactions()
        except discord.HTTPException:
            pass
        
        del self.active_votes[ctx.guild.id][member.id]
        await ctx.send(f"✅ Vote for {member.mention} has been cancelled.")

    @toxic.group(name="config")
    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    async def toxic_config(self, ctx):
        """Configure the toxic vote system."""
        pass

    @toxic_config.command(name="duration")
    async def set_duration(self, ctx, seconds: int):
        """Set how long votes stay active (in seconds)."""
        if seconds < 30:
            return await ctx.send("❌ Vote duration must be at least 30 seconds.")
        if seconds > 3600:
            return await ctx.send("❌ Vote duration cannot exceed 1 hour (3600 seconds).")
        
        await self.config.guild(ctx.guild).vote_duration.set(seconds)
        await ctx.send(f"✅ Vote duration set to {humanize_timedelta(seconds=seconds)}.")

    @toxic_config.command(name="votes")
    async def set_votes_needed(self, ctx, count: int):
        """Set how many votes are needed for a vote to pass."""
        if count < 1:
            return await ctx.send("❌ At least 1 vote is required.")
        if count > 50:
            return await ctx.send("❌ Maximum 50 votes allowed.")
        
        await self.config.guild(ctx.guild).votes_needed.set(count)
        await ctx.send(f"✅ Votes needed set to {count}.")

    @toxic_config.command(name="mode")
    async def set_mode(self, ctx, mode: str):
        """Set the action mode: 'kick' or 'ban'."""
        mode = mode.lower()
        if mode not in ["kick", "ban"]:
            return await ctx.send("❌ Mode must be either 'kick' or 'ban'.")
        
        ban_mode = mode == "ban"
        await self.config.guild(ctx.guild).ban_mode.set(ban_mode)
        await ctx.send(f"✅ Vote mode set to {mode}.")

    @toxic_config.command(name="toggle")
    async def toggle_system(self, ctx):
        """Enable or disable the toxic vote system."""
        current = await self.config.guild(ctx.guild).enabled()
        await self.config.guild(ctx.guild).enabled.set(not current)
        status = "enabled" if not current else "disabled"
        await ctx.send(f"✅ Toxic vote system {status}.")

    @toxic_config.command(name="logchannel")
    async def set_log_channel(self, ctx, channel: Optional[discord.TextChannel] = None):
        """Set the log channel for vote results."""
        if channel is None:
            await self.config.guild(ctx.guild).log_channel.set(None)
            await ctx.send("✅ Log channel disabled.")
        else:
            await self.config.guild(ctx.guild).log_channel.set(channel.id)
            await ctx.send(f"✅ Log channel set to {channel.mention}.")

    @toxic_config.command(name="view")
    async def view_config(self, ctx):
        """View current configuration."""
        config = await self.config.guild(ctx.guild).all()
        
        embed = discord.Embed(
            title="🔧 Toxic Vote System Configuration",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(name="Enabled", value="✅ Yes" if config["enabled"] else "❌ No", inline=True)
        embed.add_field(name="Mode", value="Ban" if config["ban_mode"] else "Kick", inline=True)
        embed.add_field(name="Vote Duration", value=humanize_timedelta(seconds=config["vote_duration"]), inline=True)
        embed.add_field(name="Votes Needed", value=str(config["votes_needed"]), inline=True)
        
        log_channel = ctx.guild.get_channel(config["log_channel"]) if config["log_channel"] else None
        embed.add_field(name="Log Channel", value=log_channel.mention if log_channel else "None", inline=True)
        embed.add_field(name="Vote Emojis", value=" ".join(config["vote_emojis"]), inline=True)
        
        await ctx.send(embed=embed)

    @toxic.command(name="list")
    @commands.guild_only()
    async def list_votes(self, ctx):
        """List all active votes in the server."""
        guild_votes = self.active_votes.get(ctx.guild.id, {})
        
        if not guild_votes:
            return await ctx.send("✅ No active votes in this server.")
        
        embed = discord.Embed(
            title="🗳️ Active Votes",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        
        for member_id, vote_data in guild_votes.items():
            time_left = vote_data["start_time"] + timedelta(seconds=vote_data["duration"]) - datetime.utcnow()
            embed.add_field(
                name=f"{vote_data['target'].display_name}",
                value=f"Initiated by: {vote_data['initiator'].mention}\n"
                      f"Time left: {humanize_timedelta(timedelta=time_left)}\n"
                      f"Votes needed: {vote_data['votes_needed']}",
                inline=True
            )
        
        await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: Union[discord.Member, discord.User]):
        """Handle vote reactions."""
        if user.bot:
            return
            
        message = reaction.message
        if not message.guild:
            return
            
        guild_votes = self.active_votes.get(message.guild.id, {})
        
        # Find if this is a vote message
        for member_id, vote_data in guild_votes.items():
            if vote_data["message"].id == message.id:
                # This is a vote message
                if str(reaction.emoji) not in vote_data["emojis"]:
                    # Not a valid voting emoji
                    try:
                        await message.remove_reaction(reaction.emoji, user)
                    except discord.HTTPException:
                        pass
                    return
                    
                # Check if user already voted
                if user.id in vote_data["voters"]:
                    # Already voted, remove this reaction
                    try:
                        await message.remove_reaction(reaction.emoji, user)
                    except discord.HTTPException:
                        pass
                    return
                    
                # Valid vote, add to voters
                vote_data["voters"].add(user.id)
                
                # Remove any other reactions from this user
                for emoji in vote_data["emojis"]:
                    if str(reaction.emoji) != emoji:
                        try:
                            await message.remove_reaction(emoji, user)
                        except (discord.NotFound, discord.HTTPException):
                            pass
                
                break