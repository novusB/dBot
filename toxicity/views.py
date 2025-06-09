import discord
from redbot.core import commands, modlog
from redbot.core.bot import Red
from typing import Optional, Tuple, Set


class BaseView(discord.ui.View):
    """
    Base class for interactive Discord UI views.
    Provides common methods for sending initial messages and disabling items.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.message: discord.Message = None
        self._author_id: Optional[int] = None

    async def send_initial_message(
        self, ctx: commands.Context, content: str = None, **kwargs
    ) -> discord.Message:
        """
        Sends the initial message with the view attached.
        """
        self._author_id = ctx.author.id
        # Reference the original message to keep context in Discord UI.
        kwargs["reference"] = ctx.message.to_reference(fail_if_not_exists=False)
        kwargs["mention_author"] = False
        message = await ctx.send(content, view=self, **kwargs)
        self.message = message
        return message

    def disable_items(self, *, ignore_color: Tuple[discord.ui.Button] = ()):
        """
        Disables all interactive items in the view and optionally greys out buttons.
        """
        for item in self.children:
            if isinstance(item, discord.ui.Button) and item not in ignore_color:
                item.style = discord.ButtonStyle.gray
            item.disabled = True

    async def on_timeout(self):
        """
        Called when the view times out. Disables items and updates the message.
        """
        self.disable_items()
        if self.message:
            await self.message.edit(view=self)


class ToxicityView(BaseView):
    """
    An interactive view for handling the toxicity user vote.
    """
    def __init__(
        self,
        bot: Red,
        settings: dict, # Type hint remains as dict
        invoker: discord.Member,
        target: discord.Member,
        reason: str,
    ):
        """
        Initializes the ToxicityView.
        Args:
            bot: The Red bot instance.
            settings: Guild settings for the toxicity cog (passed as a dictionary).
            invoker: The member who initiated the vote.
            target: The member who is being voted against.
            reason: The reason provided for the vote.
        """
        self.bot = bot
        super().__init__(timeout=settings["timeout"])
        self.settings = settings
        self.votes: Set[int] = set([invoker.id])
        self.target = target
        self.invoker = invoker
        self.reason = reason

        # Dynamically set button properties based on guild settings.
        self.vote.label = (
            settings["button"]["label"]
            .replace("{action}", settings["action"])
            .replace("{votes}", str(len(self.votes)))
            .replace("{votes_needed}", str(settings["votes_needed"]))
            .replace("{target}", target.display_name)
            .replace("{timeout}", f"{settings['timeout'] // 60}m" if settings['timeout'] % 60 == 0 else f"{settings['timeout']}s")
        )
        self.vote.emoji = settings["button"]["emoji"] or None
        self.vote.style = discord.ButtonStyle(settings["button"]["style"])

    @discord.ui.button(label="vote", style=discord.ButtonStyle.red, custom_id="vote_button")
    async def vote(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        Handles vote button clicks. Users can add or remove their vote.
        """
        if interaction.user.id == self.target.id:
            return await interaction.response.send_message(
                "You cannot vote against yourself!", ephemeral=True
            )
        if interaction.user.id == self.invoker.id:
            return await interaction.response.send_message(
                "You cannot remove your vote from a vote you initiated.",
                ephemeral=True,
            )
        
        # Check if the user is allowed to vote based on game roles if configured.
        if self.settings["game_roles"]:
            user_has_game_role = any(r.id in self.settings["game_roles"] for r in interaction.user.roles)
            is_staff_voter = await self.bot.is_owner(interaction.user) or await self.bot.is_admin(interaction.user) or await self.bot.is_mod(interaction.user)
            if not is_staff_voter and not user_has_game_role:
                return await interaction.response.send_message(
                    "You do not have the required role(s) to vote in this poll.",
                    ephemeral=True,
                )

        content_message = ""
        if interaction.user.id in self.votes:
            self.votes.remove(interaction.user.id)
            content_message = (
                f"Your vote to {self.settings['action']} {self.target.display_name} has been removed."
            )
        else:
            self.votes.add(interaction.user.id)
            content_message = (
                f"You have voted to {self.settings['action']} {self.target.display_name}."
            )

        # Update button label with current vote count.
        button.label = (
            self.settings["button"]["label"]
            .replace("{action}", self.settings["action"])
            .replace("{votes}", str(len(self.votes)))
            .replace("{votes_needed}", str(self.settings["votes_needed"]))
            .replace("{target}", self.target.display_name)
            .replace("{timeout}", f"{settings['timeout'] // 60}m" if settings['timeout'] % 60 == 0 else f"{settings['timeout']}s")
        )

        # Generate content for the message edit.
        to_edit = self.generate_content()
        await interaction.response.edit_message(**to_edit, view=self)

        # Send an ephemeral follow-up message to the voter.
        await interaction.followup.send(content_message, ephemeral=True)
        
        # Announce vote publicly if not anonymous.
        if not self.settings["anon_votes"]:
            await interaction.followup.send(
                f"{interaction.user.mention} voted to {self.settings['action']} {self.target.display_name}."
            )
        
        # Check if enough votes have been reached to end the vote early.
        if len(self.votes) >= self.settings["votes_needed"]:
            self.stop() # Stop the view, which will trigger on_timeout

    def generate_content(self):
        """
        Generates the content (message and embed) for the vote.
        """
        # Determine who initiated the vote for display.
        invoker_display = self.invoker.display_name if not self.settings["anon_votes"] else "someone"
        
        return {
            "content": (
                f"# Vote to {self.settings['action']} {self.target.display_name} "
                f"{f'initiated by {invoker_display}' if not self.settings['anon_votes'] else ''}"
            ),
            "embed": discord.Embed(
                description=(
                    f"**Reason:** `{self.reason or 'No reason provided.'}`\n"
                    f"**Current Votes:** {len(self.votes)}\n"
                    f"**Votes Needed:** {self.settings['votes_needed']}\n"
                    f"**Time Remaining:** {cf.humanize_timedelta(seconds=self.settings['timeout'] - (discord.utils.utcnow() - self.message.created_at).total_seconds() if self.message else self.settings['timeout'])}"
                ),
                color=self.target.color,
            ),
        }

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """
        Checks if the user interacting with the button is not a bot.
        Allows any human user to interact with the voting button.
        """
        return not interaction.user.bot

    async def on_timeout(self):
        """
        Called when the view times out or when `self.stop()` is called.
        Executes the punishment if enough votes are gathered, or announces vote failure.
        """
        self.disable_items() # Disable buttons to prevent further interaction
        
        # Check if the message still exists before editing.
        # This can happen if the message was deleted manually before timeout.
        if self.message:
            try:
                # Update the message to show the final state of the vote.
                final_content = self.generate_content()
                await self.message.edit(**final_content, view=self)
            except discord.NotFound:
                # Message was already deleted, no need to proceed with edit.
                self.bot.logger.warning("Vote message not found on timeout. It might have been deleted manually.")
                return # Exit the function early if message is gone.
            except discord.Forbidden:
                self.bot.logger.error("Bot lacks permissions to edit the vote message on timeout.")
                # Fallback to sending a new message if cannot edit.
                await self.message.channel.send("Failed to update vote message due to permissions, but outcome will be announced.")
            except Exception as e:
                self.bot.logger.error(f"Error editing vote message on timeout: {e}")
                await self.message.channel.send("An error occurred while finalizing the vote message, but outcome will be announced.")


        # Check if enough votes were gathered to proceed with punishment.
        if len(self.votes) >= self.settings["votes_needed"]:
            action = self.settings["action"]
            actioned = "kicked" if action == "kick" else "banned"
            
            # Construct the reason for modlog and public announcement.
            reason_for_log = (
                f"{self.target.display_name} was {actioned} by a vote initiated by {self.invoker.display_name} "
                f"for `{self.reason or 'being toxic'}` with {len(self.votes)} out of {self.settings['votes_needed']} votes."
            )
            
            public_announcement = (
                f"{self.target.mention} was {actioned} by a community vote ({len(self.votes)}/{self.settings['votes_needed']} votes) "
                f"for: `{self.reason or 'No reason provided.'}`"
            )

            try:
                if action == "kick":
                    await self.target.kick(reason=reason_for_log)
                elif action == "ban":
                    await self.target.ban(reason=reason_for_log)
                
                await self.message.channel.send(f"**Vote passed!** {public_announcement}")

                # Create a modlog case for the action.
                case = await modlog.create_case(
                    self.bot,
                    self.message.guild,
                    discord.utils.utcnow(), # Timestamp of the action
                    "Toxicity",
                    self.target, # The user who was affected
                    self.invoker, # The user who initiated the vote (moderator for log purposes)
                    reason_for_log, # Detailed reason for the log
                    None, # Optional: ban/kick duration if applicable (not used here)
                    self.message.channel, # Channel where the vote took place
                    # Optional: extra info like thread ID, etc.
                )
                self.bot.logger.info(f"Modlog case created: {case.id} for {self.target.display_name}")

            except discord.Forbidden:
                # If the bot somehow loses permissions during the vote, inform the channel.
                await self.message.channel.send(
                    f"**Vote passed, but I couldn't {action} {self.target.display_name}!** "
                    f"I might be missing the necessary permissions. Please check my role permissions."
                )
                self.bot.logger.error(f"Failed to {action} {self.target.display_name} due to missing permissions.")
            except discord.HTTPException as e:
                await self.message.channel.send(f"An error occurred while trying to {action} the user: {e}")
                self.bot.logger.error(f"HTTPException during {action} for {self.target.display_name}: {e}")
            except Exception as e:
                await self.message.channel.send(f"An unexpected error occurred during punishment: {e}")
                self.bot.logger.error(f"Unexpected error during punishment for {self.target.display_name}: {e}")

        else:
            # If not enough votes, announce vote failure.
            await self.message.channel.send(
                f"**Vote failed!** Required votes were {self.settings['votes_needed']} "
                f"but the vote only gathered {len(self.votes)} votes. "
                f"{self.target.display_name} will not be {actioned}."
            )

        self.stop() # Ensure the view is stopped after handling timeout/result

    async def start(self, ctx: commands.Context):
        """
        Starts the vote by sending the initial message with the interactive view.
        """
        content = self.generate_content()
        # Send the message and store it for future edits/deletions.
        await self.send_initial_message(ctx, **content)