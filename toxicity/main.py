import discord
from redbot.core import commands, app_commands, Config, modlog
from redbot.core.bot import Red
from redbot.core.utils import chat_formatting as cf
from typing import Literal, Union
from datetime import timedelta

from .views import ToxicityView
from .utils import GuildSettings, EmojiConverter


class Toxicity(commands.Cog): # Changed class name from Toxic to Toxicity
    """
    A custom cog for Red Discord Bot that allows users to vote to punish members due to toxicity.
    """

    def __init__(self, bot: Red):
        """
        Constructor for the Toxicity cog.
        Args:
            bot: The Red bot instance.
        """
        self.bot = bot
        # Initialize the Config object for this cog with a unique identifier and cog_name.
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True, cog_name="Toxicity")
        
        # Define default settings for each guild.
        default_guild = {
            "timeout": 60 * 5,  # Default vote duration: 5 minutes
            "game_roles": [],   # List of role IDs required to participate in/be targeted by votes
            "votes_needed": 4,  # Number of votes required for the punishment to pass
            "anon_votes": True, # Whether voters' identities are kept anonymous in the channel
            "ignore_hierarchy": False, # Whether to ignore Discord's role hierarchy for voting
            "action": "kick",   # Default action to take: "kick" or "ban"
            "button": {
                "style": discord.ButtonStyle.red.value, # Default button style (red)
                "label": "Vote to {action} {target}", # Button label template
                "emoji": "\N{BALLOT BOX WITH BALLOT}", # Default emoji for the button
            },
        }

        # Register the default guild settings.
        self.config.register_guild(**default_guild)

    async def cog_load(self):
        """
        Called when the cog is loaded. Registers the custom casetype for modlog.
        """
        # Define the custom casetype for modlog integration.
        case_type = {
            "name": "Toxicity",  # Changed casetype name from Toxic to Toxicity
            "default_setting": True, # Whether this casetype is enabled by default
            "image": "\N{BALLOT BOX WITH BALLOT}", # Emoji/icon for the casetype
            "case_str": "Toxicity", # Changed casetype string from Toxic to Toxicity
        }
        try:
            # Register the casetype with Red's modlog.
            await modlog.register_casetype(**case_type)
        except RuntimeError:
            # This exception is raised if the casetype is already registered.
            pass

    @commands.command(name="toxicity") # Changed command name from toxic to toxicity
    @commands.max_concurrency(1, commands.BucketType.guild) # Only one vote can be active per guild at a time
    @commands.guild_only() # Command can only be used in a Discord guild (server)
    @commands.bot_has_permissions(kick_members=True, ban_members=True) # Bot must have both kick/ban permissions
    async def toxicity(self, ctx: commands.Context, user: discord.Member, *, reason: str): # Changed command function name to toxicity
        """
        Starts a vote to punish a user due to toxicity in the server.

        The punishment (kick/ban) is determined by server settings.
        The vote will last for a configured duration, and requires a certain
        number of votes to pass.

        Usage:
        [p]toxicity <@user_mention_or_id> <reason_for_vote>

        Examples:
        [p]toxicity @AnnoyingUser spamming chat with nonsense
        [p]toxicity 123456789012345678 constantly being disruptive
        """
        settings: GuildSettings = await self.config.guild(ctx.guild).all()

        # Basic checks to prevent invalid votes
        if user.id == ctx.author.id:
            return await ctx.send("You cannot start a vote to kick yourself!")
        
        if user.id == self.bot.user.id:
            return await ctx.send("You cannot start a vote to kick the bot!")
        
        if user == ctx.guild.owner:
            return await ctx.send("You cannot start a vote to kick the server owner!")

        if user.bot:
            return await ctx.send("You cannot start a vote to kick server bots.")

        # Check bot's permissions for the configured action BEFORE the vote starts
        required_perm = "kick_members" if settings["action"] == "kick" else "ban_members"
        if not getattr(ctx.guild.me.guild_permissions, required_perm):
            return await ctx.send(
                f"I don't have the '{required_perm.replace('_', ' ').capitalize()}' permission "
                f"to perform the configured action ({settings['action']}). Please grant it to me."
            )
        
        # Check if the target user has a higher role than the bot.
        # The bot cannot kick/ban members with higher or equal roles.
        if ctx.guild.me.top_role <= user.top_role:
            return await ctx.send(f"I cannot {settings['action']} {user.display_name} as they have a higher or equal role to me.")

        # Check role hierarchy if 'ignore_hierarchy' is false.
        if settings["ignore_hierarchy"] is False and ctx.author.top_role < user.top_role:
            return await ctx.send(
                "You cannot start a vote to kick/ban someone with a higher role than you."
            )

        # Game roles logic: checks if the invoker has a game role AND the target has one.
        # This part ensures that votes are relevant to specific "game" contexts if roles are configured.
        invoker_has_game_role = any(r.id in settings["game_roles"] for r in ctx.author.roles)
        target_has_game_role = any(r.id in settings["game_roles"] for r in user.roles)

        # Determine if staff override game role requirements
        is_staff_invoker = await self.bot.is_owner(ctx.author) or await self.bot.is_admin(ctx.author) or await self.bot.is_mod(ctx.author)
        is_staff_target = await self.bot.is_owner(user) or await self.bot.is_admin(user) or await self.bot.is_mod(user)

        if settings["game_roles"]: # If game roles are configured
            if not is_staff_invoker and not invoker_has_game_role:
                return await ctx.send(
                    "You cannot start this vote because you do not have any of the configured game roles."
                )
            if not is_staff_target and not target_has_game_role:
                return await ctx.send(
                    f"You cannot start a vote against {user.display_name} because they do not have any of the configured game roles."
                )

        # Create and start the interactive voting view.
        view = ToxicityView(self.bot, settings, ctx.author, user, reason) # Changed ToxicView to ToxicityView
        await view.start(ctx)
        await view.wait() # Wait for the view to complete (timeout or button press)

    @commands.group(
        name="toxicitysettings", aliases=["toxicityset", "tset", "tsettings"], invoke_without_command=True # Changed group name and aliases
    )
    @commands.guild_only() # Ensure settings commands are only usable in a guild
    @commands.has_permissions(manage_guild=True) # Only users with manage_guild permission can access settings
    async def vs(self, ctx: commands.Context):
        """
        Change the Toxicity Player Punishment Settings for this server.
        """
        settings: GuildSettings = await self.config.guild(ctx.guild).all()
        
        # Format game roles for display.
        game_roles_display = "No roles set. Anyone can start/be targeted by votes."
        if settings["game_roles"]:
            # Filter out roles that no longer exist in the guild to prevent errors.
            valid_game_roles = [
                f"<@&{r_id}>" for r_id in settings["game_roles"] if ctx.guild.get_role(r_id)
            ]
            game_roles_display = cf.humanize_list(valid_game_roles) if valid_game_roles else "No valid roles found."

        settings_embed = discord.Embed(
            title="Toxicity Player Settings", # Changed title
            description=(
                f"**Vote Timeout:** {cf.humanize_timedelta(seconds=settings['timeout'])} before voting ends.\n"
                f"**Game Roles:** {game_roles_display}\n"
                f"**Votes Needed:** {settings['votes_needed']} votes required to {settings['action']} user.\n"
                f"**Anon Votes:** Voters will{' not ' if settings['anon_votes'] else ' '}be announced in the channel. (Punishments will still be logged!)\n"
                f"**Ignore Hierarchy:** Role hierarchy will{' ' if settings['ignore_hierarchy'] else ' not '}be ignored when initiating votes.\n"
                f"**Action to take:** {settings['action']} user\n"
            ),
            color=await ctx.embed_color(),
        )
        await ctx.send(embed=settings_embed)

    @vs.command(name="timeout")
    @commands.admin_or_permissions(manage_guild=True) # Admin or manage_guild can set timeout
    async def vs_timeout(
        self,
        ctx: commands.Context,
        duration: timedelta = commands.param(
            converter=commands.get_timedelta_converter(
                allowed_units=["seconds", "minutes"], # Only allow seconds and minutes
                maximum=timedelta(minutes=15), # Max vote duration 15 minutes
                minimum=timedelta(seconds=60), # Min vote duration 60 seconds
                default_unit="seconds", # Default unit if none specified
            )
        ),
    ):
        """
        Change the time duration before the vote expires.

        The duration must be between 60 seconds and 15 minutes.
        Examples: `120s`, `5m`
        """
        await self.config.guild(ctx.guild).timeout.set(int(duration.total_seconds()))
        await ctx.send(
            f"Successfully changed the voting timeout to {cf.humanize_timedelta(timedelta=duration)}."
        )

    @vs.command(name="gameroles", aliases=["groles"])
    @commands.admin_or_permissions(manage_guild=True) # Admin or manage_guild can set game roles
    async def vs_game_roles(
        self, ctx: commands.Context, *roles: discord.Role
    ):
        """
        Set the roles required for users to call or be targeted by a vote.

        If no roles are provided, all users can participate in votes.
        Only users with these roles (or higher staff roles) can initiate a vote.
        Only users with these roles (or higher staff roles) can be targeted by a vote.
        
        Provide role mentions or IDs. Use without arguments to clear roles.
        Examples:
        [p]toxicitysettings gameroles @GameRole1 @GameRole2
        [p]toxicitysettings gameroles (to clear roles)
        """
        if not roles:
            await self.config.guild(ctx.guild).game_roles.set([])
            return await ctx.send("Game roles cleared. Anyone can now participate in votes.")

        await self.config.guild(ctx.guild).game_roles.set(
            [role.id for role in roles] # Store only role IDs
        )
        await ctx.send(
            f"Successfully set game roles to {cf.humanize_list(list(map(lambda x: f'<@&{x.id}>', roles)))}."
        )

    @vs.command(name="votesneeded")
    @commands.admin_or_permissions(manage_guild=True) # Admin or manage_guild can set votes needed
    async def vs_votes_needed(
        self, ctx: commands.Context, votes_needed: commands.Range[int, 2, None]
    ):
        """
        Change the minimum number of votes required for a punishment to pass.

        Must be at least 2 votes.
        """
        await self.config.guild(ctx.guild).votes_needed.set(votes_needed)
        await ctx.send(f"Successfully set votes needed to: {votes_needed}.")

    @vs.command(name="anonymousvotes", aliases=["anonvotes"])
    @commands.admin_or_permissions(manage_guild=True) # Admin or manage_guild can set anonymity
    async def vs_anon_votes(self, ctx: commands.Context, value: bool):
        """
        Set whether or not the voters' identities are announced in the channel.

        If set to True, voters' names will not be publicly displayed.
        Punishments will always be logged in modlog regardless of this setting.
        """
        await self.config.guild(ctx.guild).anon_votes.set(value)
        await ctx.send(f"Voters will {'' if value else 'not '}be anonymous now.")

    @vs.command(name="ignorehierarchy", aliases=["ignorehier"])
    @commands.admin_or_permissions(manage_guild=True) # Admin or manage_guild can set hierarchy ignoring
    async def vs_ignore_hierarchy(self, ctx: commands.Context, value: bool):
        """
        Set whether or not to ignore Discord's role hierarchy for voting.

        If set to True, a user can initiate a vote against someone with a higher role.
        The bot's hierarchy limitations still apply.
        """
        await self.config.guild(ctx.guild).ignore_hierarchy.set(value)
        await ctx.send(f"Role hierarchy will {'' if value else 'not '}be ignored now.")

    @vs.command(name="action")
    @commands.admin_or_permissions(manage_guild=True) # Admin or manage_guild can set action
    async def vs_action(self, ctx: commands.Context, action: Literal["kick", "ban"]):
        """
        Change the action to take on a toxicity user if the vote passes.

        Choose between `kick` or `ban`.
        """
        # Ensure the bot has the required permission for the new action before setting.
        required_perm = "kick_members" if action == "kick" else "ban_members"
        if not getattr(ctx.guild.me.guild_permissions, required_perm):
            return await ctx.send(
                f"I don't have the '{required_perm.replace('_', ' ').capitalize()}' permission "
                f"to perform the action `{action}`. Please grant it to me before setting."
            )

        await self.config.guild(ctx.guild).action.set(action)
        await ctx.send(f"Successfully set action to `{action}`.")

    @vs.group(name="button", invoke_without_command=True)
    @commands.admin_or_permissions(manage_guild=True) # Admin or manage_guild can set button settings
    async def vs_button(self, ctx: commands.Context):
        """
        Change the button settings for starting a toxicity user vote.
        """
        settings: GuildSettings = await self.config.guild(ctx.guild).all()
        button_embed = discord.Embed(
            title="Toxicity Player Button Settings", # Changed title
            description=(
                f"**Style:** {discord.ButtonStyle(settings['button']['style']).name}\n"
                f"**Label:** `{settings['button']['label']}`\n"
                f"**Emoji:** {settings['button']['emoji'] or 'No emoji set.'}\n"
            ),
            color=await ctx.embed_color(),
        )
        # Create a preview button
        view = discord.ui.View(timeout=0)
        try:
            preview_button = discord.ui.Button(
                label=settings["button"]["label"].replace("{target}", "UserExample").replace("{votes}", "X").replace("{votes_needed}", "Y").replace("{action}", settings["action"]),
                emoji=settings["button"]["emoji"],
                style=discord.ButtonStyle(settings["button"]["style"]),
                disabled=True,
            )
            view.add_item(preview_button)
        except Exception as e:
            await ctx.send(f"Could not create a preview button due to an error: {e}. Please check your button settings.")
            self.bot.logger.error(f"Toxicity cog button preview error: {e}") # Changed log message

        await ctx.send(embed=button_embed, view=view)

    @vs_button.command(name="style")
    @commands.admin_or_permissions(manage_guild=True) # Admin or manage_guild can set button style
    async def vs_button_style(
        self, ctx: commands.Context, style: commands.Range[int, 1, 4]
    ):
        """
        Change the style (color) of the button.

        1: blurple, 2: grey, 3: green, 4: red.
        """
        await self.config.guild(ctx.guild).button.style.set(style)
        await ctx.send(f"Successfully set style to {discord.ButtonStyle(style).name.capitalize()}.")

    @vs_button.command(name="label")
    @commands.admin_or_permissions(manage_guild=True) # Admin or manage_guild can set button label
    async def vs_button_label(
        self, ctx: commands.Context, *, label: commands.Range[str, 1, 80]
    ):
        """
        Change the label (text) of the button.

        You can use variables that will be replaced dynamically:
        `{target}`: The user's display name being voted out.
        `{votes}`: The current number of votes.
        `{votes_needed}`: The total votes required.
        `{action}`: The configured action (kick/ban).
        """
        await self.config.guild(ctx.guild).button.label.set(label)
        await ctx.send(f"Successfully set label to: `{label}`.")

    @vs_button.command(name="emoji")
    @commands.admin_or_permissions(manage_guild=True) # Admin or manage_guild can set button emoji
    async def vs_button_emoji(
        self,
        ctx: commands.Context,
        emoji: Optional[Union[discord.Emoji, discord.PartialEmoji]] = commands.param(
            converter=EmojiConverter, default=None # Allow setting no emoji
        ),
    ):
        """
        Change the emoji displayed on the button.

        Provide a custom emoji (from this server or others if bot is in them)
        or a standard emoji. Use without argument to remove the emoji.
        Examples: `😂`, `:red_circle:`, `<:custom_emoji:1234567890>`
        """
        # Store the string representation of the emoji, as discord.Emoji objects are not picklable.
        if emoji:
            await self.config.guild(ctx.guild).button.emoji.set(str(emoji))
            await ctx.send(f"Successfully set button emoji to {emoji}.")
        else:
            await self.config.guild(ctx.guild).button.emoji.set("")
            await ctx.send("Successfully removed button emoji.")