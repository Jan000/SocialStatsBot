"""Scoreboard embed creation and message updates."""

from __future__ import annotations

import logging
from typing import Optional

import discord
from bot.database import Database
from bot.roles import format_count

log = logging.getLogger(__name__)

PLATFORM_LABELS = {
    "youtube": ("YouTube Abonnenten", "📺"),
    "twitch": ("Twitch Follower", "🎮"),
}

COUNT_LABEL = {
    "youtube": "Abos",
    "twitch": "Follower",
}


async def build_scoreboard_embed(
    db: Database,
    guild: discord.Guild,
    platform: str,
    settings: dict,
) -> discord.Embed:
    """Build the scoreboard embed for a platform in a guild."""
    label, emoji = PLATFORM_LABELS.get(platform, (platform, "📊"))
    prefix = "yt" if platform == "youtube" else "tw"
    max_entries = settings.get(f"{prefix}_scoreboard_size", 10)

    accounts = await db.get_all_linked(guild.id, platform)

    embed = discord.Embed(
        title=f"{emoji}  {label} Scoreboard",
        colour=discord.Colour(0xFF0000) if platform == "youtube" else discord.Colour(0x6441A4),
    )

    if not accounts:
        embed.description = "Noch keine Accounts verknüpft."
        return embed

    lines: list[str] = []
    medal = ["🥇", "🥈", "🥉"]
    for i, acc in enumerate(accounts[:max_entries]):
        rank = medal[i] if i < len(medal) else f"**{i+1}.**"
        member = guild.get_member(acc["discord_user_id"])
        display_name = member.display_name if member else f"User {acc['discord_user_id']}"
        count_str = format_count(acc["current_count"])
        c_label = COUNT_LABEL.get(platform, "")
        pname = acc.get("platform_name", "")
        account_info = f" ({pname})" if pname else ""
        lines.append(f"{rank} {display_name}{account_info} – **{count_str}** {c_label}")

    embed.description = "\n".join(lines)
    embed.set_footer(text="Automatisch aktualisiert")
    return embed


async def update_scoreboard(
    bot,
    guild: discord.Guild,
    platform: str,
    settings: dict,
) -> None:
    """Update or send the scoreboard message for a guild+platform."""
    prefix = "yt" if platform == "youtube" else "tw"
    channel_id = settings.get(f"{prefix}_scoreboard_channel_id", 0)
    if not channel_id:
        return

    channel = guild.get_channel(channel_id)
    if channel is None:
        return

    embed = await build_scoreboard_embed(bot.db, guild, platform, settings)

    msg_data = await bot.db.get_scoreboard_message(guild.id, platform)
    if msg_data:
        try:
            msg = await channel.fetch_message(msg_data["message_id"])
            await msg.edit(embed=embed)
            return
        except (discord.NotFound, discord.HTTPException):
            pass  # message gone, send a new one
    try:
        msg = await channel.send(embed=embed)
        await bot.db.set_scoreboard_message(guild.id, platform, channel.id, msg.id)
    except discord.Forbidden:
        log.error("Cannot send scoreboard to channel %s in guild %s", channel_id, guild.id)
