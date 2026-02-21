"""Cogs package for the bot – shared constants and helpers."""

from __future__ import annotations

import re

from discord import app_commands

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
    (re.compile(r"(?:https?://)?(?:www\.)?youtube\.com/", re.I), "youtube"),
    (re.compile(r"(?:https?://)?(?:www\.)?youtu\.be/", re.I), "youtube"),
    (re.compile(r"(?:https?://)?(?:www\.)?twitch\.tv/", re.I), "twitch"),
    (re.compile(r"(?:https?://)?(?:www\.)?instagram\.com/", re.I), "instagram"),
    (re.compile(r"(?:https?://)?(?:www\.)?tiktok\.com/", re.I), "tiktok"),
]


def detect_platform_from_url(url: str) -> str | None:
    """Return the platform name if *url* matches a known platform URL, else None."""
    url = url.strip()
    for pattern, platform in _URL_PLATFORM_PATTERNS:
        if pattern.match(url):
            return platform
    return None
