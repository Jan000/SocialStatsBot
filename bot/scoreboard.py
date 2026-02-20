"""Scoreboard embed creation and message updates.

All linked accounts are displayed (no limit).  When the embed
description would exceed Discord's 4096-char cap the ranking is
automatically split across two messages.  The last embed always
contains a timestamp footer showing when the list was updated,
when the next update is scheduled and the refresh interval.
"""

from __future__ import annotations

import datetime
import logging

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

# Discord hard-limit for a single embed description.
_MAX_DESCRIPTION = 4096


async def build_scoreboard_embeds(
    db: Database,
    guild: discord.Guild,
    platform: str,
    settings: dict,
) -> list[discord.Embed]:
    """Build 1-2 scoreboard embeds showing **all** linked accounts.

    Returns a list of embeds; callers must send each as a separate
    Discord message.
    """
    label, emoji = PLATFORM_LABELS.get(platform, (platform, "📊"))
    prefix = "yt" if platform == "youtube" else "tw"
    interval = settings.get(f"{prefix}_refresh_interval", 600)
    colour = (
        discord.Colour(0xFF0000) if platform == "youtube"
        else discord.Colour(0x6441A4)
    )

    accounts = await db.get_all_linked(guild.id, platform)

    if not accounts:
        embed = discord.Embed(
            title=f"{emoji}  {label} Scoreboard",
            colour=colour,
            description="Noch keine Accounts verknüpft.",
        )
        return [embed]

    # ── Build ranking lines ──────────────────────────────────────
    lines: list[str] = []
    medal = ["🥇", "🥈", "🥉"]
    for i, acc in enumerate(accounts):
        rank = medal[i] if i < len(medal) else f"**{i+1}.**"
        member = guild.get_member(acc["discord_user_id"])
        display_name = member.display_name if member else f"User {acc['discord_user_id']}"
        count_str = format_count(acc["current_count"])
        c_label = COUNT_LABEL.get(platform, "")
        pname = acc.get("platform_name", "")
        account_info = f" ({pname})" if pname else ""
        lines.append(f"{rank} {display_name}{account_info} – **{count_str}** {c_label}")

    # ── Timestamp / interval block (appended to last embed) ──────
    now_ts = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
    next_ts = now_ts + interval
    interval_min = max(1, interval // 60)
    timestamp_block = (
        "\n\n─────────────────────────\n"
        f"🕐 Aktualisiert: <t:{now_ts}:R>\n"
        f"⏭️ Nächste Aktualisierung: <t:{next_ts}:R>\n"
        f"🔄 Intervall: **{interval_min} Minuten**"
    )

    # ── Try to fit everything into a single embed ────────────────
    full_desc = "\n".join(lines) + timestamp_block
    if len(full_desc) <= _MAX_DESCRIPTION:
        return [
            discord.Embed(
                title=f"{emoji}  {label} Scoreboard",
                colour=colour,
                description=full_desc,
            )
        ]

    # ── Split into two embeds ────────────────────────────────────
    mid = len(lines) // 2
    desc1 = "\n".join(lines[:mid])
    desc2 = "\n".join(lines[mid:]) + timestamp_block

    # Safety: if even the second half exceeds the limit, truncate
    if len(desc2) > _MAX_DESCRIPTION:
        desc2 = desc2[:_MAX_DESCRIPTION]

    embed1 = discord.Embed(
        title=f"{emoji}  {label} Scoreboard (1/2)",
        colour=colour,
        description=desc1,
    )
    embed2 = discord.Embed(
        title=f"{emoji}  {label} Scoreboard (2/2)",
        colour=colour,
        description=desc2,
    )
    return [embed1, embed2]


async def update_scoreboard(
    bot,
    guild: discord.Guild,
    platform: str,
    settings: dict,
) -> None:
    """Update or send the scoreboard message(s) for a guild+platform.

    Handles 1-2 messages and cleans up surplus old messages when the
    scoreboard shrinks back to a single message.
    """
    prefix = "yt" if platform == "youtube" else "tw"
    channel_id = settings.get(f"{prefix}_scoreboard_channel_id", 0)
    if not channel_id:
        return

    channel = guild.get_channel(channel_id)
    if channel is None:
        return

    embeds = await build_scoreboard_embeds(bot.db, guild, platform, settings)

    # Retrieve previously stored message IDs (may be 0, 1 or 2)
    old_ids = await bot.db.get_scoreboard_message_ids(guild.id, platform)
    new_ids: list[int] = []

    for i, embed in enumerate(embeds):
        sent = False
        if i < len(old_ids):
            try:
                msg = await channel.fetch_message(old_ids[i])
                await msg.edit(embed=embed)
                new_ids.append(msg.id)
                sent = True
            except (discord.NotFound, discord.HTTPException):
                pass
        if not sent:
            try:
                msg = await channel.send(embed=embed)
                new_ids.append(msg.id)
            except discord.Forbidden:
                log.error(
                    "Cannot send scoreboard to channel %s in guild %s",
                    channel_id, guild.id,
                )
                return

    # Delete surplus old messages (e.g. scoreboard shrank from 2 → 1)
    for old_id in old_ids[len(embeds):]:
        try:
            old_msg = await channel.fetch_message(old_id)
            await old_msg.delete()
        except (discord.NotFound, discord.HTTPException):
            pass

    # Persist new message IDs
    await bot.db.set_scoreboard_message_ids(
        guild.id, platform, channel_id, new_ids
    )
