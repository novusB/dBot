"""
Utility functions for the Toxicity cog.
"""
from datetime import timedelta
from typing import Union

def format_time_remaining(seconds: Union[int, float]) -> str:
    """
    Format seconds into a human-readable time string.
    
    Parameters
    ----------
    seconds: Union[int, float]
        The number of seconds to format
        
    Returns
    -------
    str
        A formatted string representing the time
    """
    if seconds <= 0:
        return "0 seconds"
        
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    parts = []
    if days > 0:
        parts.append(f"{int(days)} day{'s' if days != 1 else ''}")
    if hours > 0:
        parts.append(f"{int(hours)} hour{'s' if hours != 1 else ''}")
    if minutes > 0:
        parts.append(f"{int(minutes)} minute{'s' if minutes != 1 else ''}")
    if seconds > 0 and not parts:
        parts.append(f"{int(seconds)} second{'s' if seconds != 1 else ''}")
        
    return ", ".join(parts)

def has_matching_roles(member1, member2, ignore_default=True):
    """
    Check if two members have matching roles.
    
    Parameters
    ----------
    member1: discord.Member
        The first member to compare
    member2: discord.Member
        The second member to compare
    ignore_default: bool
        Whether to ignore the default @everyone role
        
    Returns
    -------
    bool
        True if the members have matching roles, False otherwise
    """
    if ignore_default:
        roles1 = set(role.id for role in member1.roles if role != member1.guild.default_role)
        roles2 = set(role.id for role in member2.roles if role != member2.guild.default_role)
    else:
        roles1 = set(role.id for role in member1.roles)
        roles2 = set(role.id for role in member2.roles)
        
    return roles1 == roles2