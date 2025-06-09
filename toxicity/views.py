"""
Discord UI Views for the Toxicity cog.
"""
import discord
from discord.ui import View, Button, Select
from typing import Optional, Callable, List, Dict, Any

class ConfirmationView(View):
    """A simple confirmation view with Yes/No buttons."""
    
    def __init__(self, *, timeout: int = 180):
        super().__init__(timeout=timeout)
        self.value = None
        self.interaction = None
    
    @discord.ui.button(label="Yes", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: Button):
        self.value = True
        self.interaction = interaction
        await interaction.response.defer()
        self.stop()
    
    @discord.ui.button(label="No", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: Button):
        self.value = False
        self.interaction = interaction
        await interaction.response.defer()
        self.stop()

class VoteView(View):
    """A view for voting with customizable emojis."""
    
    def __init__(self, *, emojis: List[str] = ["👍", "👎", "🤷"], timeout: int = 300):
        super().__init__(timeout=timeout)
        self.votes = {"yes": 0, "no": 0, "abstain": 0}
        self.voters = set()
        
        # Create buttons based on provided emojis
        self.add_item(Button(emoji=emojis[0], custom_id="vote_yes", style=discord.ButtonStyle.green))
        self.add_item(Button(emoji=emojis[1], custom_id="vote_no", style=discord.ButtonStyle.red))
        self.add_item(Button(emoji=emojis[2], custom_id="vote_abstain", style=discord.ButtonStyle.gray))
    
    @discord.ui.button(custom_id="vote_yes")
    async def vote_yes(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id in self.voters:
            await interaction.response.send_message("You have already voted!", ephemeral=True)
            return
        
        self.votes["yes"] += 1
        self.voters.add(interaction.user.id)
        await interaction.response.send_message("You voted: Yes", ephemeral=True)
    
    @discord.ui.button(custom_id="vote_no")
    async def vote_no(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id in self.voters:
            await interaction.response.send_message("You have already voted!", ephemeral=True)
            return
        
        self.votes["no"] += 1
        self.voters.add(interaction.user.id)
        await interaction.response.send_message("You voted: No", ephemeral=True)
    
    @discord.ui.button(custom_id="vote_abstain")
    async def vote_abstain(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id in self.voters:
            await interaction.response.send_message("You have already voted!", ephemeral=True)
            return
        
        self.votes["abstain"] += 1
        self.voters.add(interaction.user.id)
        await interaction.response.send_message("You voted: Abstain", ephemeral=True)

class ConfigView(View):
    """A view for configuring the toxicity cog."""
    
    def __init__(self, *, timeout: int = 180):
        super().__init__(timeout=timeout)
        self.value = None
        self.interaction = None
    
    @discord.ui.button(label="Duration", style=discord.ButtonStyle.primary)
    async def set_duration(self, interaction: discord.Interaction, button: Button):
        self.value = "duration"
        self.interaction = interaction
        await interaction.response.defer()
        self.stop()
    
    @discord.ui.button(label="Votes Needed", style=discord.ButtonStyle.primary)
    async def set_votes(self, interaction: discord.Interaction, button: Button):
        self.value = "votes"
        self.interaction = interaction
        await interaction.response.defer()
        self.stop()
    
    @discord.ui.button(label="Mode", style=discord.ButtonStyle.primary)
    async def set_mode(self, interaction: discord.Interaction, button: Button):
        self.value = "mode"
        self.interaction = interaction
        await interaction.response.defer()
        self.stop()
    
    @discord.ui.button(label="Toggle", style=discord.ButtonStyle.secondary)
    async def toggle_system(self, interaction: discord.Interaction, button: Button):
        self.value = "toggle"
        self.interaction = interaction
        await interaction.response.defer()
        self.stop()
    
    @discord.ui.button(label="Log Channel", style=discord.ButtonStyle.secondary)
    async def set_log_channel(self, interaction: discord.Interaction, button: Button):
        self.value = "log_channel"
        self.interaction = interaction
        await interaction.response.defer()
        self.stop()