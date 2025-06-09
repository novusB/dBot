import asyncio
import discord
from datetime import datetime, timedelta
from typing import Optional, Dict, Union
from redbot.core import commands, Config, checks
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

    def cog_unload(self):
        """Clean up active votes when cog is unloaded."""
        self.active_votes.clear()

    def _has_matching_roles(self, member1: discord.Member, member2: discord.Member) -> bool:
        """Check if two members have identical roles (excluding @everyone)."""
        roles1 = {role.id for role in member1.roles if role != member1.guild.default_role}
        roles2 = {role.id for role in member2.roles if role != member2.guild.default_role}
        return roles1 == roles2

    @commands.group(name="toxic")
    @commands.guild_only()
    async def toxic(self, ctx):
        """Toxic vote system commands."""
        pass

    @toxic.command(name="vote")
    @commands.guild_only()
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def vote_kick(self, ctx, member: discord.Member, *, reason: str = "No reason provided"):
        """Initiate a vote to kick/ban a member with matching roles."""
        
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
                if vote_data["config"]["ban_mode"]:
                    await vote_data["target"].ban(reason=f"Vote ban: {vote_data['reason']}")
                else:
                    await vote_data["target"].kick(reason=f"Vote kick: {vote_data['reason']}")
                
                embed.color = discord.Color.red()
                embed.add_field(name="Result", value=f"✅ Vote passed! Member {action}ed.", inline=False)
                
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
        
        # Log result
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
        pass

    @config.command(name="duration")
    async def set_duration(self, ctx, seconds: int):
        """Set vote duration (30-3600 seconds)."""
        if not 30 <= seconds <= 3600:
            return await ctx.send("❌ Duration must be between 30 and 3600 seconds.")
        
        await self.config.guild(ctx.guild).vote_duration.set(seconds)
        await ctx.send(f"✅ Vote duration set to {humanize_timedelta(seconds=seconds)}.")

    @config.command(name="votes")
    async def set_votes_needed(self, ctx, count: int):
        """Set votes needed to pass (1-50)."""
        if not 1 <= count <= 50:
            return await ctx.send("❌ Vote count must be between 1 and 50.")
        
        await self.config.guild(ctx.guild).votes_needed.set(count)
        await ctx.send(f"✅ Votes needed set to {count}.")

    @config.command(name="mode")
    async def set_mode(self, ctx, mode: str):
        """Set action mode: 'kick' or 'ban'."""
        mode = mode.lower()
        if mode not in ["kick", "ban"]:
            return await ctx.send("❌ Mode must be 'kick' or 'ban'.")
        
        await self.config.guild(ctx.guild).ban_mode.set(mode == "ban")
        await ctx.send(f"✅ Vote mode set to {mode}.")

    @config.command(name="toggle")
    async def toggle_system(self, ctx):
        """Enable/disable the vote system."""
        current = await self.config.guild(ctx.guild).enabled()
        await self.config.guild(ctx.guild).enabled.set(not current)
        status = "enabled" if not current else "disabled"
        await ctx.send(f"✅ Toxic vote system {status}.")

    @config.command(name="logchannel")
    async def set_log_channel(self, ctx, channel: Optional[discord.TextChannel] = None):
        """Set log channel for vote results."""
        if channel is None:
            await self.config.guild(ctx.guild).log_channel.set(None)
            await ctx.send("✅ Log channel disabled.")
        else:
            await self.config.guild(ctx.guild).log_channel.set(channel.id)
            await ctx.send(f"✅ Log channel set to {channel.mention}.")

    @config.command(name="view")
    async def view_config(self, ctx):
        """View current configuration."""
        config = await self.config.guild(ctx.guild).all()
        
        embed = discord.Embed(title="🔧 Toxic Vote Configuration", color=discord.Color.blue())
        embed.add_field(name="Enabled", value="✅ Yes" if config["enabled"] else "❌ No", inline=True)
        embed.add_field(name="Mode", value="Ban" if config["ban_mode"] else "Kick", inline=True)
        embed.add_field(name="Duration", value=humanize_timedelta(seconds=config["vote_duration"]), inline=True)
        embed.add_field(name="Votes Needed", value=str(config["votes_needed"]), inline=True)
        
        log_channel = ctx.guild.get_channel(config["log_channel"]) if config["log_channel"] else None
        embed.add_field(name="Log Channel", value=log_channel.mention if log_channel else "None", inline=True)
        embed.add_field(name="Emojis", value=" ".join(config["vote_emojis"]), inline=True)
        
        await ctx.send(embed=embed)

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