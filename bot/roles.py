"""
Role manager – creates, assigns, and cleans up subscriber/follower roles.
"""

from __future__ import annotations

import discord
from typing import Optional

from bot.database import Database

# Prefix used to identify bot-managed roles so we don't touch user roles.
ROLE_MANAGED_PREFIX_YT = "[YT] "
ROLE_MANAGED_PREFIX_TW = "[TW] "


def _platform_prefix(platform: str) -> str:
    return ROLE_MANAGED_PREFIX_YT if platform == "youtube" else ROLE_MANAGED_PREFIX_TW


def build_role_name(pattern: str, count: int) -> str:
    """Build a role name from the pattern, replacing {count} placeholder."""
    return pattern.replace("{count}", f"{count:,}")


async def get_or_create_role(
    guild: discord.Guild,
    role_name: str,
    role_color: int,
) -> discord.Role:
    """Find an existing role by name or create a new one."""
    for role in guild.roles:
        if role.name == role_name:
            # Update colour if changed
            if role.color.value != role_color:
                await role.edit(color=discord.Color(role_color))
            return role
    return await guild.create_role(
        name=role_name,
        color=discord.Color(role_color),
        reason="NirukiSocialStats – auto-managed role",
    )


async def compute_role_name_and_color(
    db: Database,
    guild_id: int,
    platform: str,
    count: int,
    settings: dict,
) -> tuple[str, int]:
    """Determine the role name & colour for a given count."""
    design = await db.get_role_design_for_count(guild_id, platform, count)
    prefix = _platform_prefix(platform)
    if design:
        pattern = design["role_pattern"]
        color = design["role_color"]
    else:
        if platform == "youtube":
            pattern = settings.get("yt_default_role_pattern", "{count} YouTube Abos")
            color = settings.get("yt_default_role_color", 16711680)
        else:
            pattern = settings.get("tw_default_role_pattern", "{count} Twitch Follower")
            color = settings.get("tw_default_role_color", 6570404)
    name = prefix + build_role_name(pattern, count)
    return name, color


async def update_member_role(
    guild: discord.Guild,
    member: discord.Member,
    platform: str,
    new_role_name: str,
    new_role_color: int,
) -> None:
    """
    Assign the new role to the member and remove any old bot-managed
    roles for the same platform.
    """
    prefix = _platform_prefix(platform)
    # Get or create the target role
    target_role = await get_or_create_role(guild, new_role_name, new_role_color)

    # Remove old platform roles from the member (except the new one)
    roles_to_remove = [
        r for r in member.roles
        if r.name.startswith(prefix) and r.id != target_role.id
    ]
    if roles_to_remove:
        await member.remove_roles(*roles_to_remove, reason="NirukiSocialStats – role update")

    # Add new role if not already assigned
    if target_role not in member.roles:
        await member.add_roles(target_role, reason="NirukiSocialStats – role update")


async def cleanup_unused_roles(guild: discord.Guild, platform: str) -> int:
    """
    Remove bot-managed roles for a platform that no member has assigned.
    Returns the number of roles deleted.
    """
    prefix = _platform_prefix(platform)
    deleted = 0
    for role in list(guild.roles):
        if role.name.startswith(prefix) and len(role.members) == 0:
            try:
                await role.delete(reason="NirukiSocialStats – unused role cleanup")
                deleted += 1
            except discord.Forbidden:
                pass
    return deleted
