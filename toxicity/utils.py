from typing import TypedDict, Literal, Optional # Added Optional for clarity
from redbot.core import commands
import discord


class GuildSettings(TypedDict):
    """
    Type dictionary for the guild-specific settings stored in Red's Config.
    """
    timeout: int
    game_roles: list[int]
    votes_needed: int
    anon_votes: bool
    ignore_hierarchy: bool
    action: Literal["kick", "ban"]
    button: dict[str, Union[str, int]] # button can have string (label, emoji) or int (style)


class EmojiConverter(commands.EmojiConverter):
    """
    Custom converter for Discord emojis, supporting both custom and unicode emojis.
    """
    async def convert(
        self, ctx: commands.Context, argument: str
    ) -> Union[discord.Emoji, discord.PartialEmoji]: # Return type can be Emoji or PartialEmoji
        try:
            # Try converting as a custom Discord emoji (from any server the bot is in)
            return await super().convert(ctx, argument)
        except commands.EmojiNotFound:
            # If not a custom emoji, try to convert as a unicode emoji or partial emoji string.
            # This handles cases like "👍" or "<:name:ID>" for emojis not in bot's guilds.
            try:
                return discord.PartialEmoji.from_str(argument)
            except ValueError:
                # If it's not a valid emoji string at all.
                raise commands.BadArgument(f"'{argument}' is not a valid emoji or custom emoji.")