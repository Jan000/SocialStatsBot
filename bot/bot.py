"""SocialStatsBot – main Bot class."""

from __future__ import annotations

import logging
from typing import Optional

import discord
from discord.ext import commands

from bot.database import Database
from bot.services.youtube import YouTubeService
from bot.services.twitch import TwitchService

log = logging.getLogger(__name__)


class SocialStatsBot(commands.Bot):
    """Discord bot that tracks YouTube subscribers and Twitch followers."""

    db: Database
    youtube: YouTubeService
    twitch: TwitchService

    def __init__(
        self,
        *,
        youtube_api_key: str,
        twitch_client_id: str,
        twitch_client_secret: str,
    ) -> None:
        intents = discord.Intents.default()
        intents.members = True
        super().__init__(command_prefix="!", intents=intents)

        self.db = Database()
        self.youtube = YouTubeService(youtube_api_key)
        self.twitch = TwitchService(twitch_client_id, twitch_client_secret)

    async def setup_hook(self) -> None:
        log.info("Connecting to database …")
        await self.db.connect()

        log.info("Loading cogs …")
        await self.load_extension("bot.cogs.admin")
        await self.load_extension("bot.cogs.settings")
        await self.load_extension("bot.cogs.refresh")

        log.info("Syncing slash commands …")
        await self.tree.sync()
        log.info("Bot is ready.")

    async def close(self) -> None:
        await self.youtube.close()
        await self.twitch.close()
        await self.db.close()
        await super().close()

    async def on_ready(self) -> None:
        log.info("Logged in as %s (ID: %s)", self.user, self.user.id if self.user else "?")
