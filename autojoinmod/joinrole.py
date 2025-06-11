import asyncio
import discord
from redbot.core import commands, Config
from redbot.core.utils.predicates import MessagePredicate

# We'll need these for buttons
from discord.ui import View, Button
from discord.enums import ButtonStyle

# --- Views for Button Interactions ---

class PurposeSelectionView(View):
    """View for selecting the user's purpose."""
    def __init__(self, cog, member, channel, timeout=300):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.member = member
        self.channel = channel
        self.selected_purpose = None
        self.message = None # To store the message with the buttons

        # Define buttons for each purpose
        self.purpose_buttons_data = {
            "Gaming": ButtonStyle.blurple,
            "Social": ButtonStyle.green,
            "Hanging Out": ButtonStyle.green,
            "Meeting New Friends": ButtonStyle.green,
        }

        # Add buttons dynamically
        for label, style in self.purpose_buttons_data.items():
            button = Button(label=label, style=style, custom_id=f"purpose_{label.lower().replace(' ', '_')}")
            button.callback = self.button_callback
            self.add_item(button)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            await self.message.edit(content=f"{self.member.mention}, you took too long to respond. Please rejoin the server to restart enrollment.", view=self)
        await self.cog._cleanup_and_delete_channel(self.member, self.channel)
        self.stop()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Only allow the member who joined to interact with these buttons
        if interaction.user != self.member:
            await interaction.response.send_message("This interaction is not for you!", ephemeral=True)
            return False
        return True

    async def button_callback(self, interaction: discord.Interaction):
        await interaction.response.defer() # Defer the interaction to show it's being processed
        self.selected_purpose = interaction.custom_id.replace("purpose_", "").replace("_", " ")
        self.stop() # Stop the view once a selection is made

class GameSelectionView(View):
    """View for selecting multiple games."""
    def __init__(self, cog, member, channel, game_options, timeout=300):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.member = member
        self.channel = channel
        self.game_options = game_options # dict of {game_name: role_id}
        self.selected_games_roles = [] # Store actual role objects
        self.message = None # To store the message with the buttons

        # Add a "Done" button
        done_button = Button(label="Done with Game Selection", style=ButtonStyle.success, custom_id="game_done")
        done_button.callback = self.done_callback
        self.add_item(done_button)

        # Add game buttons (can't have too many, Discord limits buttons per message)
        # If too many games, a text-based fallback might be needed or multiple pages.
        # For this example, we'll assume a reasonable number.
        for i, (game_name, role_id) in enumerate(game_options.items()):
            if i >= 20: # Discord button limit per view is 25, reserving one for "Done"
                break
            button = Button(label=game_name.title(), style=ButtonStyle.primary, custom_id=f"game_{game_name.lower().replace(' ', '_')}")
            button.callback = self.game_button_callback
            self.add_item(button)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            await self.message.edit(content=f"{self.member.mention}, you took too long to select games. Skipping game selection.", view=self)
        self.stop()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.member:
            await interaction.response.send_message("This interaction is not for you!", ephemeral=True)
            return False
        return True

    async def game_button_callback(self, interaction: discord.Interaction):
        game_key = interaction.custom_id.replace("game_", "").replace("_", " ")
        role_id = self.game_options.get(game_key)
        if role_id:
            role = self.member.guild.get_role(role_id)
            if role and role not in self.selected_games_roles:
                self.selected_games_roles.append(role)
                await interaction.response.send_message(f"Selected: **{role.name}**", ephemeral=True)
            elif role and role in self.selected_games_roles:
                self.selected_games_roles.remove(role)
                await interaction.response.send_message(f"Deselected: **{role.name}**", ephemeral=True)
            else:
                await interaction.response.send_message("Couldn't find that role. Please inform a moderator.", ephemeral=True)
        else:
            await interaction.response.send_message("Invalid game selection.", ephemeral=True)

    async def done_callback(self, interaction: discord.Interaction):
        await interaction.response.defer() # Defer the interaction
        self.stop() # Stop the view and proceed


# --- JoinRole Cog ---

class JoinRole(commands.Cog):
    """
    Automated Server Join Role Enrollment System.

    Guides new members through role selection in a temporary private channel using buttons.
    """

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)

        default_guild_settings = {
            "verified_role_id": None,
            "purpose_roles": {},
            "game_roles": {},
            "temp_channel_category_id": None,
            "initial_welcome_message": "Welcome {user}! What is your main purpose for joining this server?\n\n"
                                       "Please select one of the options below:"
        }
        self.config.register_guild(**default_guild_settings)
        self.active_channels = {} # To keep track of temporary channels

    # --- Admin Commands for Configuration (Remain largely the same) ---

    @commands.group(name="joinrole", aliases=["jr"])
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def joinrole_group(self, ctx: commands.Context):
        """Manage the Automated Join Role system settings."""
        pass

    @joinrole_group.command(name="setverifiedrole")
    async def set_verified_role(self, ctx: commands.Context, role: discord.Role):
        """Sets the role new members receive after completing enrollment.

        This role should give access to the rest of the server.
        """
        await self.config.guild(ctx.guild).verified_role_id.set(role.id)
        await ctx.send(f"The **Verified** role has been set to `{role.name}`.")

    @joinrole_group.command(name="setpurposerole")
    async def set_purpose_role(self, ctx: commands.Context, purpose: str, role: discord.Role):
        """Sets a role for a specific purpose (e.g., Gaming, Social).

        `purpose` should be one of: `gaming`, `social`, `hanging out`, `meeting new friends`.
        """
        purpose_lower = purpose.lower()
        valid_purposes = ["gaming", "social", "hanging out", "meeting new friends"]
        if purpose_lower not in valid_purposes:
            return await ctx.send(
                f"Invalid purpose. Must be one of: {', '.join(valid_purposes)}."
            )
        async with self.config.guild(ctx.guild).purpose_roles() as roles:
            roles[purpose_lower] = role.id
        await ctx.send(f"The role for purpose `{purpose}` has been set to `{role.name}`.")

    @joinrole_group.command(name="setgamerole")
    async def set_game_role(self, ctx: commands.Context, game_name: str, role: discord.Role):
        """Sets a role for a specific game (e.g., "oldschool runescape", "valorant").

        Enclose multi-word game names in quotes.
        """
        game_lower = game_name.lower()
        async with self.config.guild(ctx.guild).game_roles() as roles:
            roles[game_lower] = role.id
        await ctx.send(f"The role for game `{game_name}` has been set to `{role.name}`.")

    @joinrole_group.command(name="settempchannelcategory")
    async def set_temp_channel_category(self, ctx: commands.Context, category: discord.CategoryChannel = None):
        """Sets the category where temporary channels will be created.

        If no category is provided, temporary channels will be created at the top level.
        """
        if category:
            await self.config.guild(ctx.guild).temp_channel_category_id.set(category.id)
            await ctx.send(f"Temporary channels will now be created in category `{category.name}`.")
        else:
            await self.config.guild(ctx.guild).temp_channel_category_id.set(None)
            await ctx.send("Temporary channels will now be created at the top level (no specific category).")

    @joinrole_group.command(name="setinitialwelcomemessage")
    async def set_initial_welcome_message(self, ctx: commands.Context, *, message: str):
        """Sets the initial welcome message shown to new users.

        Use `{user}` as a placeholder for the new member's mention.
        """
        await self.config.guild(ctx.guild).initial_welcome_message.set(message)
        await ctx.send("Initial welcome message updated.")

    @joinrole_group.command(name="viewsettings")
    async def view_settings(self, ctx: commands.Context):
        """Displays the current configuration for the Join Role system."""
        settings = await self.config.guild(ctx.guild).all()
        embed = discord.Embed(
            title="Join Role System Settings",
            color=await ctx.embed_color()
        )

        verified_role = ctx.guild.get_role(settings["verified_role_id"]) if settings["verified_role_id"] else "Not set"
        embed.add_field(name="Verified Role", value=verified_role, inline=False)

        purpose_roles_str = "\n".join(
            [f"`{p.capitalize()}`: {ctx.guild.get_role(r).name if ctx.guild.get_role(r) else 'N/A (ID:' + str(r) + ')'}"
             for p, r in settings["purpose_roles"].items()]
        ) or "No purpose roles set."
        embed.add_field(name="Purpose Roles", value=purpose_roles_str, inline=False)

        game_roles_str = "\n".join(
            [f"`{g.title()}`: {ctx.guild.get_role(r).name if ctx.guild.get_role(r) else 'N/A (ID:' + str(r) + ')'}"
             for g, r in settings["game_roles"].items()]
        ) or "No game roles set."
        embed.add_field(name="Game Roles", value=game_roles_str, inline=False)

        temp_category = ctx.guild.get_channel(settings["temp_channel_category_id"]) if settings["temp_channel_category_id"] else "None (top level)"
        embed.add_field(name="Temporary Channel Category", value=temp_category, inline=False)

        embed.add_field(name="Initial Welcome Message Preview",
                        value=settings["initial_welcome_message"].format(user=ctx.author.mention)[:1020] + "..." if len(settings["initial_welcome_message"]) > 1020 else settings["initial_welcome_message"],
                        inline=False)


        await ctx.send(embed=embed)


    # --- Listener for New Members ---

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """
        Handles new member joining the server.
        Creates a temporary channel and starts the enrollment process.
        """
        guild = member.guild
        settings = await self.config.guild(guild).all()

        verified_role_id = settings["verified_role_id"]
        purpose_roles_map = settings["purpose_roles"]
        game_roles_map = settings["game_roles"]
        temp_category_id = settings["temp_channel_category_id"]
        initial_welcome_message = settings["initial_welcome_message"]

        # Basic check if the system is configured enough to run
        if not verified_role_id or not purpose_roles_map:
            print(f"JoinRole: Not enough configuration for guild {guild.name}. Skipping for {member.name}.")
            return

        # Ensure bot has necessary permissions
        bot_member = guild.me
        if not bot_member.guild_permissions.manage_channels or \
           not bot_member.guild_permissions.manage_roles:
            print(f"JoinRole: Bot lacks 'Manage Channels' or 'Manage Roles' permissions in {guild.name}. Skipping for {member.name}.")
            return

        # Check if the member is already going through the process (e.g., due to rapid re-joins)
        if member.id in self.active_channels:
            print(f"JoinRole: {member.name} is already in an active enrollment process. Skipping.")
            return

        temp_channel = None
        try:
            # Set permissions for the temporary channel
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                member: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True,
                                                     manage_channels=True, manage_roles=True)
            }

            category = guild.get_channel(temp_category_id) if temp_category_id else None

            # Create the temporary channel
            temp_channel = await guild.create_text_channel(
                f"welcome-{member.name.lower().replace(' ', '-')}",
                overwrites=overwrites,
                category=category,
                topic=f"Temporary channel for {member.name} to select roles."
            )
            self.active_channels[member.id] = temp_channel.id
            print(f"JoinRole: Created temporary channel {temp_channel.name} for {member.name}.")

            # --- Purpose Selection with Buttons ---
            purpose_view = PurposeSelectionView(self, member, temp_channel)
            purpose_embed = discord.Embed(
                title="Welcome to the Server!",
                description=initial_welcome_message.format(user=member.mention),
                color=discord.Color.blue()
            )
            purpose_embed.add_field(name="Your Intentions:", value="Please select your main purpose for joining below.", inline=False)
            
            # Send the message with buttons and store it for later editing
            purpose_view.message = await temp_channel.send(embed=purpose_embed, view=purpose_view)
            
            # Wait for the user to make a selection
            await purpose_view.wait()
            
            selected_purpose = purpose_view.selected_purpose

            if not selected_purpose: # Timed out or no selection
                await temp_channel.send("No purpose selected. Please rejoin if you wish to try again.")
                return await self._cleanup_and_delete_channel(member, temp_channel)

            # Disable buttons after selection
            for item in purpose_view.children:
                item.disabled = True
            await purpose_view.message.edit(view=purpose_view)


            # Assign purpose role
            purpose_role = guild.get_role(purpose_roles_map.get(selected_purpose))
            if purpose_role:
                await member.add_roles(purpose_role)
                await temp_channel.send(f"Assigned you the `{purpose_role.name}` role!")
            else:
                await temp_channel.send(f"Could not find the role for '{selected_purpose}'. Please inform a moderator.")


            # --- Game Selection (if Gaming) with Buttons ---
            if selected_purpose == "gaming":
                if not game_roles_map:
                    await temp_channel.send("No specific game roles are configured for this server yet. Skipping game selection.")
                else:
                    game_view = GameSelectionView(self, member, temp_channel, game_roles_map)
                    game_embed = discord.Embed(
                        title="Game Selection",
                        description=f"{member.mention}, which games do you play? Click to select/deselect. Click **'Done'** when finished.",
                        color=discord.Color.purple()
                    )
                    
                    # Send the message with game buttons
                    game_view.message = await temp_channel.send(embed=game_embed, view=game_view)
                    
                    # Wait for the user to finish game selection
                    await game_view.wait()

                    # Disable buttons after selection
                    for item in game_view.children:
                        item.disabled = True
                    await game_view.message.edit(view=game_view)

                    if game_view.selected_games_roles:
                        await member.add_roles(*game_view.selected_games_roles)
                        assigned_game_names = [r.name for r in game_view.selected_games_roles]
                        await temp_channel.send(f"Assigned you the following game roles: {', '.join(assigned_game_names)}!")
                    else:
                        await temp_channel.send("No game roles were assigned.")

            # --- Finalization: Assign Verified Role and Cleanup ---
            verified_role = guild.get_role(verified_role_id)
            if verified_role:
                await member.add_roles(verified_role)
                await temp_channel.send(
                    f"You are all set, {member.mention}! You now have access to the main server channels. "
                    "This channel will be deleted shortly."
                )
                print(f"JoinRole: Assigned verified role to {member.name}.")
                await asyncio.sleep(5) # Give user a moment to read
            else:
                await temp_channel.send(
                    f"Could not find the **Verified** role (ID: {verified_role_id}). "
                    "Please contact a moderator to gain full access to the server."
                )
                print(f"JoinRole: Verified role not found for guild {guild.name}. Member: {member.name}.")
                await asyncio.sleep(10) # Longer wait if no verified role assigned

            await self._cleanup_and_delete_channel(member, temp_channel)


        except discord.errors.Forbidden:
            print(f"JoinRole Error: Bot does not have permissions to create/manage channels or roles in {guild.name}.")
            if temp_channel and member.id in self.active_channels:
                del self.active_channels[member.id]
        except Exception as e:
            print(f"JoinRole Unhandled Error for {member.name} in {guild.name}: {e}")
            if temp_channel and member.id in self.active_channels:
                del self.active_channels[member.id]
            if temp_channel:
                try:
                    await temp_channel.send("An unexpected error occurred during enrollment. Please contact a moderator.")
                    await asyncio.sleep(5)
                    await temp_channel.delete()
                except discord.errors.NotFound:
                    pass # Channel might already be deleted
                except Exception as cleanup_e:
                    print(f"JoinRole Cleanup Error: {cleanup_e}")

    async def _cleanup_and_delete_channel(self, member: discord.Member, channel: discord.TextChannel):
        """Helper to safely remove active channel tracking and delete the channel."""
        if member.id in self.active_channels:
            del self.active_channels[member.id]
        try:
            await channel.delete()
            print(f"JoinRole: Deleted temporary channel {channel.name} for {member.name}.")
        except discord.errors.NotFound:
            print(f"JoinRole: Temporary channel {channel.name} for {member.name} already deleted.")
        except Exception as e:
            print(f"JoinRole Error deleting channel {channel.name} for {member.name}: {e}")