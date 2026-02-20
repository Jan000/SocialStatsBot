"""
Role management – create, assign, and cleanup bot-managed roles.

Role prefixes:
  [YouTube]  for YouTube accounts
  [Twitch]   for Twitch accounts

Role name format: "[Platform] {pattern}" where pattern uses {name} and {count}.
"""

from __future__ import annotations

import logging
from typing import Optional

import discord

from bot.database import Database

log = logging.getLogger(__name__)

PLATFORM_PREFIX = {
    "youtube": "[YouTube] ",
    "twitch": "[Twitch] ",
}


def format_count(count: int) -> str:
    """Format a subscriber/follower count with dot separators."""
    return f"{count:,}".replace(",", ".")


def build_role_name(
    platform: str, pattern: str, count: int, name: str = ""
) -> str:
    """Build full role name including prefix.

    Pattern may contain {count} and {name} placeholders.
    """
    prefix = PLATFORM_PREFIX.get(platform, "")
    formatted = pattern.replace("{count}", format_count(count)).replace("{name}", name)
    return f"{prefix}{formatted}"


async def compute_role_name_and_color(
    db: Database,
    guild_id: int,
    platform: str,
    count: int,
    settings: dict,
    platform_name: str = "",
) -> tuple[str, int]:
    """Determine role name and colour for a given subscriber/follower count.

    Priority: exact match design > range match design > guild default pattern.
    """
    design = await db.get_role_design_for_count(guild_id, platform, count)
    if design:
        return (
            build_role_name(platform, design["role_pattern"], count, platform_name),
            design["role_color"],
        )

    prefix = "yt" if platform == "youtube" else "tw"
    pattern = settings.get(f"{prefix}_default_role_pattern", "{name} - {count}")
    color = settings.get(f"{prefix}_default_role_color", 0)
    return build_role_name(platform, pattern, count, platform_name), color


def _is_bot_role(role: discord.Role, platform: str) -> bool:
    """Check if a role is managed by this bot for the given platform."""
    prefix = PLATFORM_PREFIX.get(platform, "")
    return role.name.startswith(prefix)


async def update_member_role(
    guild: discord.Guild,
    member: discord.Member,
    platform: str,
    platform_name: str,
    role_name: str,
    role_color: int,
) -> None:
    """Ensure *member* has the given role and remove old roles for the same account.

    Only removes roles whose name starts with the account-specific prefix,
    e.g. '[YouTube] Niruki -'.
    """
    prefix = PLATFORM_PREFIX.get(platform, "")
    # Account-specific prefix to match: "[YouTube] Niruki - "
    account_prefix = f"{prefix}{platform_name} - " if platform_name else prefix

    # Find roles to remove (belonging to the same account, but not the target)
    roles_to_remove = [
        r for r in member.roles
        if r.name.startswith(account_prefix) and r.name != role_name
    ]

    # Check if the target role already exists
    target_role = discord.utils.get(guild.roles, name=role_name)
    if target_role is None:
        try:
            target_role = await guild.create_role(
                name=role_name,
                colour=discord.Colour(role_color),
                reason="SocialStatsBot: Rollen-Update",
            )
            log.info("Created role '%s' in guild %s", role_name, guild.id)
        except discord.Forbidden:
            log.error("Missing permissions to create role '%s' in guild %s", role_name, guild.id)
            return

    # Update colour if it changed
    if target_role.colour.value != role_color:
        try:
            await target_role.edit(colour=discord.Colour(role_color))
        except discord.Forbidden:
            log.warning("Cannot edit colour of role '%s'", role_name)

    # Remove stale roles
    for role in roles_to_remove:
        try:
            await member.remove_roles(role, reason="SocialStatsBot: Rollen-Update")
        except discord.Forbidden:
            log.warning("Cannot remove role '%s' from %s", role.name, member)

    # Assign target role
    if target_role not in member.roles:
        try:
            await member.add_roles(target_role, reason="SocialStatsBot: Rollen-Update")
            log.info("Assigned role '%s' to %s", role_name, member)
        except discord.Forbidden:
            log.error("Cannot assign role '%s' to %s", role_name, member)


async def remove_account_roles(
    guild: discord.Guild,
    member: discord.Member,
    platform: str,
    platform_name: str,
) -> None:
    """Remove all bot-managed roles for a specific account from a member."""
    prefix = PLATFORM_PREFIX.get(platform, "")
    account_prefix = f"{prefix}{platform_name} - " if platform_name else prefix
    roles_to_remove = [r for r in member.roles if r.name.startswith(account_prefix)]
    for role in roles_to_remove:
        try:
            await member.remove_roles(role, reason="SocialStatsBot: Account entfernt")
        except discord.Forbidden:
            log.warning("Cannot remove role '%s' from %s", role.name, member)


async def cleanup_unused_roles(guild: discord.Guild, platform: str) -> int:
    """Delete bot-managed roles that no member has.  Returns number of deleted roles."""
    prefix = PLATFORM_PREFIX.get(platform, "")
    deleted = 0
    for role in list(guild.roles):
        if role.name.startswith(prefix) and len(role.members) == 0:
            try:
                await role.delete(reason="SocialStatsBot: Unbenutzte Rolle")
                deleted += 1
                log.info("Deleted unused role '%s'", role.name)
            except discord.Forbidden:
                log.warning("Cannot delete role '%s'", role.name)
    return deleted
