"""
Core bot class that loads config, database, services, and cogs.
"""

from __future__ import annotations

import discord
from discord.ext import commands
from pathlib import Path
from typing import Any

import toml

from bot.database import Database
from bot.services.youtube import YouTubeService
from bot.services.twitch import TwitchService

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.toml"


def load_config(path: Path | None = None) -> dict[str, Any]:
    p = path or CONFIG_PATH
    if not p.exists():
        raise FileNotFoundError(
            f"config.toml not found at {p}. Copy config.toml.example to config.toml and fill in your values."
        )
    return toml.load(p)


class SocialStatsBot(commands.Bot):
    """Main bot subclass carrying shared state."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.admin_user_id: int = config["admin"]["user_id"]

        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True

        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None,
        )

        # Shared resources
        self.db = Database()
        self.youtube = YouTubeService(config["api_keys"]["youtube_api_key"])
        self.twitch = TwitchService(
            config["api_keys"]["twitch_client_id"],
            config["api_keys"]["twitch_client_secret"],
        )

    def is_admin(self, user_id: int) -> bool:
        return user_id == self.admin_user_id

    async def setup_hook(self) -> None:
        """Called once before the bot connects. Load DB + cogs."""
        await self.db.connect()

        # Load cogs
        await self.load_extension("bot.cogs.admin")
        await self.load_extension("bot.cogs.settings")
        await self.load_extension("bot.cogs.refresh")

        # Sync slash commands
        await self.tree.sync()
        print("[Bot] Slash commands synced.")

    async def close(self) -> None:
        await self.youtube.close()
        await self.twitch.close()
        await self.db.close()
        await super().close()

    async def on_ready(self) -> None:
        print(f"[Bot] Logged in as {self.user} (ID: {self.user.id})")
        print(f"[Bot] Admin user ID: {self.admin_user_id}")
        print(f"[Bot] Guilds: {len(self.guilds)}")
