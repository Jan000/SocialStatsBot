"""Cogs package for the bot – shared constants and helpers."""

from __future__ import annotations

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
