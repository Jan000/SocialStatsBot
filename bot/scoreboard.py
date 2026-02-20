"""
Scoreboard – builds and updates the top-N embed in the configured channel.
"""

from __future__ import annotations

import discord
from datetime import datetime, timezone
from typing import Optional

from bot.database import Database


def _platform_label(platform: str) -> str:
    return "YouTube Abos" if platform == "youtube" else "Twitch Follower"


def _platform_color(platform: str) -> int:
    return 0xFF0000 if platform == "youtube" else 0x6441A4


async def build_scoreboard_embed(
    db: Database,
    guild: discord.Guild,
    platform: str,
    limit: int = 10,
) -> discord.Embed:
    """Build a Discord Embed showing the top-N users by sub/follower count."""
    accounts = await db.get_all_linked(guild.id, platform)
    top = accounts[:limit]

    label = _platform_label(platform)
    embed = discord.Embed(
        title=f"🏆 {label} Scoreboard",
        color=discord.Color(_platform_color(platform)),
        timestamp=datetime.now(timezone.utc),
    )

    if not top:
        embed.description = "Noch keine Accounts verknüpft."
        return embed

    lines: list[str] = []
    medals = ["🥇", "🥈", "🥉"]
    for i, acc in enumerate(top):
        medal = medals[i] if i < len(medals) else f"**#{i + 1}**"
        member = guild.get_member(acc["discord_user_id"])
        name = member.display_name if member else f"User {acc['discord_user_id']}"
        platform_name = acc.get("platform_name") or acc["platform_id"]
        count = acc["current_count"]
        lines.append(f"{medal}  **{name}** – {count:,} ({platform_name})")

    embed.description = "\n".join(lines)
    embed.set_footer(text="Aktualisiert")
    return embed


async def update_scoreboard(
    bot: discord.Client,
    db: Database,
    guild: discord.Guild,
    platform: str,
    settings: dict,
) -> None:
    """
    Update (or create) the scoreboard message in the configured channel.
    """
    channel_key = (
        "yt_scoreboard_channel_id" if platform == "youtube" else "tw_scoreboard_channel_id"
    )
    size_key = (
        "yt_scoreboard_size" if platform == "youtube" else "tw_scoreboard_size"
    )
    channel_id = settings.get(channel_key, 0)
    if not channel_id:
        return

    channel = guild.get_channel(channel_id)
    if channel is None:
        return

    limit = settings.get(size_key, 10)
    embed = await build_scoreboard_embed(db, guild, platform, limit)

    # Try to edit existing message
    sb = await db.get_scoreboard_message(guild.id, platform)
    if sb:
        try:
            msg = await channel.fetch_message(sb["message_id"])
            await msg.edit(embed=embed)
            return
        except (discord.NotFound, discord.Forbidden):
            pass  # will send new message below

    # Send new message
    msg = await channel.send(embed=embed)
    await db.set_scoreboard_message(guild.id, platform, channel.id, msg.id)
