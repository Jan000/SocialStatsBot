"""Cogs package for the bot – shared constants, helpers, and exceptions."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from discord import app_commands

if TYPE_CHECKING:
    from bot.bot import SocialStatsBot


# ── Exceptions ────────────────────────────────────────────────────────


class PlatformRateLimitError(Exception):
    """Raised when a platform API keeps returning 429 after all retries."""

    def __init__(self, platform: str, identifier: str) -> None:
        self.platform = platform
        self.identifier = identifier
        super().__init__(
            f"{platform} rate-limited for {identifier}"
        )


# ── Platform choices (reused across all cogs) ────────────────────────
PLATFORM_CHOICES = [
    app_commands.Choice(name="YouTube", value="youtube"),
    app_commands.Choice(name="Twitch", value="twitch"),
    app_commands.Choice(name="Instagram", value="instagram"),
    app_commands.Choice(name="TikTok", value="tiktok"),
]

# ── Platform display metadata ────────────────────────────────────────
PLATFORM_EMOJI = {
    "youtube": "📺",
    "twitch": "🎮",
    "instagram": "📷",
    "tiktok": "🎵",
}

PLATFORM_COUNT_LABEL = {
    "youtube": "Abos",
    "twitch": "Follower",
    "instagram": "Follower",
    "tiktok": "Follower",
}

PLATFORM_COLOUR_INT = {
    "youtube": 0xFF0000,
    "twitch": 0x6441A4,
    "instagram": 0xDB4A76,
    "tiktok": 0x000000,
}

PLATFORM_DISPLAY_NAME = {
    "youtube": "YouTube",
    "twitch": "Twitch",
    "instagram": "Instagram",
    "tiktok": "TikTok",
}

# ── URL → platform detection ─────────────────────────────────────────
_URL_PLATFORM_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"(?:https?://)?(?:[\w-]+\.)*youtube\.com/", re.I), "youtube"),
    (re.compile(r"(?:https?://)?(?:[\w-]+\.)*youtu\.be/", re.I), "youtube"),
    (re.compile(r"(?:https?://)?(?:[\w-]+\.)*twitch\.tv/", re.I), "twitch"),
    (re.compile(r"(?:https?://)?(?:[\w-]+\.)*instagram\.com/", re.I), "instagram"),
    (re.compile(r"(?:https?://)?(?:[\w-]+\.)*tiktok\.com/", re.I), "tiktok"),
]


def detect_platform_from_url(url: str) -> str | None:
    """Return the platform name if *url* matches a known platform URL, else None."""
    url = url.strip()
    for pattern, platform in _URL_PLATFORM_PATTERNS:
        if pattern.match(url):
            return platform
    return None


# ── Shared API helpers (used by admin, request, refresh cogs) ────────


async def resolve_platform(bot: SocialStatsBot, platform: str, user_input: str) -> dict | None:
    """Resolve user input into a normalised info dict for the given platform.

    Returns dict with keys ``id``, ``display_name``, ``follower_count``
    (and additionally ``subscriber_count`` for YouTube), or *None* on error.
    """
    if platform == "youtube":
        info = await bot.youtube.resolve_channel(user_input)
        if info is None:
            return None
        return {
            "id": info["id"],
            "display_name": info["title"],
            "subscriber_count": info["subscriber_count"],
            "follower_count": info["subscriber_count"],
        }
    elif platform == "twitch":
        info = await bot.twitch.get_channel_info(user_input)
        if info is None:
            return None
        return {
            "id": info["id"],
            "display_name": info["display_name"],
            "follower_count": info["follower_count"],
        }
    elif platform == "instagram":
        return await bot.instagram.get_channel_info(user_input)
    elif platform == "tiktok":
        return await bot.tiktok.get_channel_info(user_input)
    return None


async def fetch_count(bot: SocialStatsBot, platform: str, account: dict) -> int | None:
    """Fetch the current subscriber/follower count for an account."""
    if platform == "youtube":
        return await bot.youtube.get_subscriber_count(account["platform_id"])
    elif platform == "twitch":
        return await bot.twitch.get_follower_count(account["platform_id"])
    elif platform == "instagram":
        return await bot.instagram.get_follower_count(account["platform_id"])
    elif platform == "tiktok":
        return await bot.tiktok.get_follower_count(account["platform_id"])
    return None
