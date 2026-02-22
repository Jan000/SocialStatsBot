"""Scoreboard embed creation and message updates.

All linked accounts are displayed (no limit).  When the embed
description would exceed Discord's 4096-char cap the ranking is
automatically split across two messages.  The last embed carries
a footer with the next-update countdown, the interval and a native
Discord timestamp for the last update.
"""

from __future__ import annotations

import datetime
import logging
import time

import discord

from bot.cogs import PLATFORM_COUNT_LABEL
from bot.database import Database
from bot.roles import format_count

log = logging.getLogger(__name__)

PLATFORM_LABELS = {
    "youtube": ("YouTube Abonnenten", "📺"),
    "twitch": ("Twitch Follower", "🎮"),
    "instagram": ("Instagram Follower", "📷"),
    "tiktok": ("TikTok Follower", "🎵"),
}

# Local PNG paths (bundled in Docker image, no external URL needed).
# Embeds use  attachment://platform_icon.png  so Discord hosts the file.
PLATFORM_ICON_PATH = {
    "youtube": "assets/icons/youtube.png",
    "twitch": "assets/icons/twitch.png",
    "instagram": "assets/icons/instagram.png",
    "tiktok": "assets/icons/tiktok.png",
}
_ICON_ATTACHMENT_NAME = "platform_icon.png"

PLATFORM_COLOUR = {
    "youtube": discord.Colour(0xFF0000),
    "twitch": discord.Colour(0x6441A4),
    "instagram": discord.Colour(0xDB4A76),
    "tiktok": discord.Colour(0x000000),
}

# Import the settings-prefix mapping from roles.
from bot.roles import PLATFORM_SETTINGS_PREFIX

# Discord hard-limit for a single embed description.
_MAX_DESCRIPTION = 4096

# Discord allows only 2 channel-renames per 10 minutes.  We enforce a
# per-channel cooldown to prevent 429 storms.
_CHANNEL_RENAME_COOLDOWN = 600  # seconds (10 min)
_last_rename: dict[int, float] = {}  # channel_id -> monotonic timestamp


def _format_interval(seconds: int) -> str:
    """Format an interval in seconds into a human-readable German string."""
    if seconds >= 3600 and seconds % 3600 == 0:
        h = seconds // 3600
        return f"{h} Stunde" if h == 1 else f"{h} Stunden"
    if seconds >= 60 and seconds % 60 == 0:
        m = seconds // 60
        return f"{m} Minute" if m == 1 else f"{m} Minuten"
    return f"{seconds} Sekunde" if seconds == 1 else f"{seconds} Sekunden"


def _timestamp_block(now_ts: int, next_ts: int, interval: int) -> str:
    """Return the update-info block to append to an embed description."""
    interval_label = _format_interval(interval)
    return (
        "\n\n─────────────────────────\n"
        f"🕐 Aktualisiert: <t:{now_ts}:f>\n"
        f"⏭️ Nächste Aktualisierung: <t:{next_ts}:R> ({interval_label})"
    )


def _apply_embed_chrome(
    embed: discord.Embed,
    platform: str,
    now_ts: int,
    next_ts: int,
    interval: int,
) -> None:
    """Set thumbnail reference and append timestamp block on *embed* (mutates in-place).

    The thumbnail uses ``attachment://platform_icon.png``.  Callers must
    pass the actual file object when sending/editing the Discord message.
    """
    if platform in PLATFORM_ICON_PATH:
        embed.set_thumbnail(url=f"attachment://{_ICON_ATTACHMENT_NAME}")
    # Append timestamp block to description (footer can't render <t:…:R>)
    embed.description = (embed.description or "") + _timestamp_block(now_ts, next_ts, interval)


def _icon_file(platform: str) -> discord.File | None:
    """Return a fresh :class:`discord.File` for the platform icon, or None."""
    import os
    path = PLATFORM_ICON_PATH.get(platform)
    if path and os.path.exists(path):
        return discord.File(path, filename=_ICON_ATTACHMENT_NAME)
    return None


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
    prefix = PLATFORM_SETTINGS_PREFIX.get(platform, platform[:2])
    interval = settings.get(f"{prefix}_refresh_interval", 600)
    colour = PLATFORM_COLOUR.get(platform, discord.Colour.default())

    now = datetime.datetime.now(datetime.timezone.utc)
    now_ts = int(now.timestamp())
    next_ts = now_ts + interval

    accounts = await db.get_all_linked(guild.id, platform)

    if not accounts:
        embed = discord.Embed(
            title=f"{emoji}  {label} Scoreboard",
            colour=colour,
            description="Noch keine Accounts verknüpft.",
        )
        _apply_embed_chrome(embed, platform, now_ts, next_ts, interval)
        return [embed]


    # ── Summary line ─────────────────────────────────────────────
    c_label = PLATFORM_COUNT_LABEL.get(platform, "")
    total = sum(a["current_count"] for a in accounts)
    summary = f"**{len(accounts)}** Accounts • Gesamt: **{format_count(total)}** {c_label}\n"

    # ── Build ranking lines ──────────────────────────────────────
    lines: list[str] = []
    medal = ["🥇", "🥈", "🥉"]
    for i, acc in enumerate(accounts):
        rank = medal[i] if i < len(medal) else f"**{i+1}.**"
        member = guild.get_member(acc["discord_user_id"])
        display_name = member.display_name if member else f"User {acc['discord_user_id']}"
        count_str = format_count(acc["current_count"])
        pname = acc.get("platform_name", "")
        account_info = f" ({pname})" if pname else ""
        lines.append(f"{rank} {display_name}{account_info} – **{count_str}** {c_label}")

    # ── Timestamp block ──────────────────────────────────────────
    ts_block = _timestamp_block(now_ts, next_ts, interval)

    # ── Try to fit everything into a single embed ────────────────
    ranking_text = "\n".join(lines)
    full_desc = f"{summary}\n{ranking_text}{ts_block}"
    if len(full_desc) <= _MAX_DESCRIPTION:
        embed = discord.Embed(
            title=f"{emoji}  {label} Scoreboard",
            colour=colour,
            description=full_desc,
        )
        if platform in PLATFORM_ICON_PATH:
            embed.set_thumbnail(url=f"attachment://{_ICON_ATTACHMENT_NAME}")
        return [embed]

    # ── Split into two embeds ────────────────────────────────────
    mid = len(lines) // 2
    desc1 = f"{summary}\n" + "\n".join(lines[:mid])
    desc2 = "\n".join(lines[mid:]) + ts_block

    # Safety: if even the second half exceeds the limit, truncate
    if len(desc2) > _MAX_DESCRIPTION:
        desc2 = desc2[:_MAX_DESCRIPTION]

    embed1 = discord.Embed(
        title=f"{emoji}  {label} Scoreboard (1/2)",
        colour=colour,
        description=desc1,
    )
    if platform in PLATFORM_ICON_PATH:
        embed1.set_thumbnail(url=f"attachment://{_ICON_ATTACHMENT_NAME}")
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
    scoreboard shrinks back to a single message.  The last message
    carries a "Link-Request" button so users can submit requests.
    """
    from bot.cogs.request import ScoreboardRequestView

    prefix = PLATFORM_SETTINGS_PREFIX.get(platform, platform[:2])
    channel_id = settings.get(f"{prefix}_scoreboard_channel_id", 0)
    if not channel_id:
        return

    channel = guild.get_channel(channel_id)
    if channel is None:
        return

    embeds = await build_scoreboard_embeds(bot.db, guild, platform, settings)

    # The link-request button is attached to the LAST scoreboard message.
    link_view = ScoreboardRequestView(platform)

    # Retrieve previously stored message IDs (may be 0, 1 or 2)
    old_ids = await bot.db.get_scoreboard_message_ids(guild.id, platform)
    new_ids: list[int] = []

    last_idx = len(embeds) - 1
    # Empty view removes components; None would leave them unchanged on edit.
    empty_view = discord.ui.View()
    for i, embed in enumerate(embeds):
        is_last = i == last_idx
        view = link_view if is_last else empty_view
        # Only the first embed in each scoreboard gets the icon attachment.
        icon = _icon_file(platform) if i == 0 else None
        sent = False

        if i < len(old_ids):
            try:
                msg = await channel.fetch_message(old_ids[i])
                attachments = [icon] if icon else []
                await msg.edit(embed=embed, view=view, attachments=attachments)
                new_ids.append(msg.id)
                sent = True
            except (discord.NotFound, discord.HTTPException):
                pass
        if not sent:
            try:
                if icon:
                    msg = await channel.send(embed=embed, view=view, file=icon)
                else:
                    msg = await channel.send(embed=embed, view=view)
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


async def update_count_channel(
    bot,
    guild: discord.Guild,
    platform: str,
    settings: dict,
) -> None:
    """Rename the count-display channel to reflect the current total.

    The channel name is built from the guild's count_channel_pattern
    with ``{count}`` replaced by the formatted total.
    """
    prefix = PLATFORM_SETTINGS_PREFIX.get(platform, platform[:2])
    channel_id = settings.get(f"{prefix}_count_channel_id", 0)
    if not channel_id:
        return

    channel = guild.get_channel(channel_id)
    if channel is None:
        return

    accounts = await bot.db.get_all_linked(guild.id, platform)
    total = sum(a["current_count"] for a in accounts)

    default_label = PLATFORM_LABELS.get(platform, (platform, ""))
    default_pattern = f"{default_label[1]} {{count}} {default_label[0]}"
    pattern = settings.get(f"{prefix}_count_channel_pattern", default_pattern)
    new_name = pattern.replace("{count}", format_count(total))

    if channel.name != new_name:
        # Respect Discord's 2-per-10-min channel-rename rate limit.
        last = _last_rename.get(channel_id, 0.0)
        elapsed = time.monotonic() - last
        if elapsed < _CHANNEL_RENAME_COOLDOWN:
            log.debug(
                "Skipping count-channel rename for %s (cooldown: %.0fs remaining)",
                channel_id, _CHANNEL_RENAME_COOLDOWN - elapsed,
            )
            return
        try:
            await channel.edit(name=new_name)
            _last_rename[channel_id] = time.monotonic()
        except (discord.Forbidden, discord.HTTPException) as exc:
            log.error(
                "Cannot rename count channel %s in guild %s: %s",
                channel_id, guild.id, exc,
            )
