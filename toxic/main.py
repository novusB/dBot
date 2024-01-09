import discord
from redbot.core import commands, app_commands, Config, modlog
from redbot.core.bot import Red
from redbot.core.utils import chat_formatting as cf
from typing import Literal, Union
from datetime import timedelta

from .views import ToxicView
from .utils import GuildSettings, EmojiConverter


class Toxic(commands.Cog):
    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        default_guild = {
            "timeout": 60 * 5,
            "game_roles": [],
            "votes_needed": 4,
            "anon_votes": True,
            "ignore_hierarchy": False,
            "action": "kick",
            "button": {
                "style": discord.ButtonStyle.red.value,
                "label": "Vote to kick {target}",
                "emoji": "\N{BALLOT BOX WITH BALLOT}",
            },
        }

        self.config.register_guild(**default_guild)

    async def cog_load(self):
        case_type = {
            "name": "Toxic",
            "default_setting": True,
            "image": "\N{BALLOT BOX WITH BALLOT}",
            "case_str": "Toxic",
        }
        try:
            await modlog.register_casetype(**case_type)
        except RuntimeError:
            pass

    @commands.command(name="vote")
    @commands.max_concurrency(1, commands.BucketType.guild)
    @commands.guild_only()
    async def vote(self, ctx: commands.Context, user: discord.Member, *, reason: str):
        """Start a vote to kick toxic user."""
        settings: GuildSettings = await self.config.guild(ctx.guild).all()
        print(settings)
        if user.id == ctx.author.id or user.id == self.bot.user.id:
            return await ctx.send("You cannot vote to kick yourself or the bot!")

        if user == ctx.guild.owner:
            return await ctx.send("You cannot vote to kick the owner!")

        if user.bot:
            return await ctx.send("You cannot vote to kick server bots.")

        if (
            settings["ignore_hierarchy"] is False
            and ctx.author.top_role < user.top_role
        ):
            return await ctx.send(
                "You cannot vote to kick someone with a higher role than you."
            )

        user_role = next(
            filter(
                lambda x: ctx.author.get_role(x) is not None,
                settings["game_roles"],
            ),
            None,
        )
        override = any(
            [
                await self.bot.is_owner(user),
                await self.bot.is_admin(user),
                await self.bot.is_mod(user),
            ]
        )
        if not user_role and not override:
            return await ctx.send(
                "You cannot vote to kick this user because you aren't playing the same game!"
            )

        elif user_role and not override:
            if not any(
                user.get_role(role) for role in settings["game_roles"]
            ):
                return await ctx.send(
                    "You cannot vote out this user because they don't have any of the allowed roles."
                )
            if not user.get_role(user_role):
                return await ctx.send(
                    "You cannot vote to kick this user because you aren't playing the same game!"
                )

        view = ToxicView(ctx.bot, settings, ctx.author, user, reason)

        await view.start(ctx)

        await view.wait()

    @commands.group(
        name="toxicsettings", aliases=["toxicset", "tset"], invoke_without_command=True
    )
    async def vs(self, ctx: commands.Context):
        """Change the settings for the commands"""
        settings: GuildSettings = await self.config.guild(ctx.guild).all()
        settings_embed = discord.Embed(
            title="Toxic Player Settings",
            description=(
                f"**Voting Timeout:** {cf.humanize_timedelta(seconds=settings['timeout'])} before voting ends.\n"
                f"**Game Roles:** {cf.humanize_list(list(map(lambda x: f'<@&{x}>', settings['game_roles']))) or 'No roles set up. Admin/mod roles required to set roles.'}\n"
                f"**Votes Needed:** {settings['votes_needed']} votes required to {settings['action']} user.\n"
                f"**Anonymous Votes:** Voters will{' not ' if settings['anon_votes'] else ' '}be announced. (Actions still be logged)\n"
                f"**Ignore Hierarchy:** Role hierarchy will{' ' if settings['ignore_hierarchy'] else ' not '}be ignored.\n"
                f"**Action to take if vote passes:** {settings['action']} user\n"
            ),
            color=await ctx.embed_color(),
        )
        await ctx.send(embed=settings_embed)

    @vs.command(name="timeout")
    async def vs_timeout(
        self,
        ctx: commands.Context,
        duration: timedelta = commands.param(
            converter=commands.get_timedelta_converter(
                allowed_units=["seconds", "minutes"],
                maximum=timedelta(minutes=15),
                minimum=timedelta(seconds=60),
                default_unit="seconds",
            )
        ),
    ):
        """Change the timeout for voteout."""
        await self.config.guild(ctx.guild).timeout.set(duration.total_seconds())
        await ctx.send(
            f"Successfully changed the voting timeout to {cf.humanize_timedelta(timedelta=duration)}."
        )

    @vs.command(name="gameroles", aliases=["groles"])
    async def vs_game_roles(
        self, ctx: commands.Context, *roles: discord.Role
    ):
        """Change the roles needed to call a vote."""
        if not roles:
            return await ctx.send_help()

        await self.config.guild(ctx.guild).game_roles.set(
            [*{role.id for role in roles}]
        )
        await ctx.send(
            f"Successfully set game roles to {cf.humanize_list(list(map(lambda x: f'<@&{x.id}>', roles)))}."
        )

    @vs.command(name="votes_needed")
    async def vs_votes_needed(
        self, ctx: commands.Context, votes_needed: commands.Range[int, 2, None]
    ):
        """Change the votes_needed for a vote, this is the number of votes required to take action on a toxic user."""
        await self.config.guild(ctx.guild).votes_needed.set(votes_needed)
        await ctx.send(f"Successfully set votes needed to: {votes_needed}.")

    @vs.command(name="anonymousvotes", aliases=["anonvotes"])
    async def vs_anon_votes(self, ctx: commands.Context, value: bool):
        """Change whether or not the votes are anonymous."""
        await self.config.guild(ctx.guild).anon_votes.set(value)
        await ctx.send(f"Votes will {'' if value else 'not '}be anonymous now.")

    @vs.command(name="ignorehierarchy", aliases=["ignorehier"])
    async def vs_ignore_hierarchy(self, ctx: commands.Context, value: bool):
        """Change whether or not to ignore role hierarchy when users vote out other users."""
        await self.config.guild(ctx.guild).ignore_hierarchy.set(value)
        await ctx.send(f"Role hierarchy will {'' if value else 'not '}be ignored now.")

    @vs.command(name="action")
    async def vs_action(self, ctx: commands.Context, action: Literal["kick", "ban"]):
        """Change the action to take on a voted out user."""
        await self.config.guild(ctx.guild).action.set(action)
        await ctx.send(f"Successfully set action to {action}.")

    @vs.group(name="button", invoke_without_command=True)
    async def vs_button(self, ctx: commands.Context):
        """Change the button settings for kicking toxic user."""
        settings: GuildSettings = await self.config.guild(ctx.guild).all()
        button_embed = discord.Embed(
            title="Toxic Player Button Settings",
            description=(
                f"**Style:** {discord.ButtonStyle(settings['button']['style']).name}\n"
                f"**Label:** {settings['button']['label']}\n"
                f"**Emoji:** {settings['button']['emoji']}\n"
            ),
            color=await ctx.embed_color(),
        )
        view = discord.ui.View(timeout=0)
        view.add_item(
            discord.ui.Button(
                label=settings["button"]["label"],
                emoji=settings["button"]["emoji"],
                style=discord.ButtonStyle(settings["button"]["style"]),
                disabled=True,
            )
        )
        await ctx.send(embed=button_embed, view=view)

    @vs_button.command(name="style")
    async def vs_button_style(
        self, ctx: commands.Context, style: commands.Range[int, 1, 4]
    ):
        """Change the style of the button.

        1 is blurple, 2 is grey, 3 is green and 4 is red."""
        await self.config.guild(ctx.guild).button.style.set(style)
        await ctx.send(f"Successfully set style to {style}.")

    @vs_button.command(name="label")
    async def vs_button_label(
        self, ctx: commands.Context, *, label: commands.Range[str, 1, 80]
    ):
        """Change the label of the button.

        Variables:
            "{target}" will be replaced with the user's name that's being voted out.
            "{votes}" will be replaced with the number of votes needed.
            "{timeout}" will be replaced with the voting timeout.
            "{action}" will be replaced with the action to take on user if the vote passes.
        """
        await self.config.guild(ctx.guild).button.label.set(label)
        await ctx.send(f"Successfully set label to {label}.")

    @vs_button.command(name="emoji")
    async def vs_button_emoji(
        self,
        ctx: commands.Context,
        emoji: Union[discord.Emoji, discord.PartialEmoji] = commands.param(
            converter=EmojiConverter
        ),
    ):
        """Change the emoji of the button."""
        await self.config.guild(ctx.guild).button.emoji.set(emoji)
        await ctx.send(f"Successfully set emoji to {emoji}.")