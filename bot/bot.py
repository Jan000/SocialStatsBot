"""SocialStatsBot – main Bot class."""

from __future__ import annotations

import logging
from typing import Optional

import discord
from discord.ext import commands

from bot.database import Database
from bot.services.youtube import YouTubeService
from bot.services.twitch import TwitchService
from bot.services.eventsub import TwitchEventSub

log = logging.getLogger(__name__)


class SocialStatsBot(commands.Bot):
    """Discord bot that tracks YouTube subscribers and Twitch followers."""

    db: Database
    youtube: YouTubeService
    twitch: TwitchService
    eventsub: TwitchEventSub | None
    dev_guild_id: int | None

    def __init__(
        self,
        *,
        youtube_api_key: str,
        twitch_client_id: str,
        twitch_client_secret: str,
        dev_guild_id: int | None = None,
        enable_eventsub: bool = False,
    ) -> None:
        intents = discord.Intents.default()
        intents.members = True
        super().__init__(command_prefix="!", intents=intents)

        self.db = Database()
        self.youtube = YouTubeService(youtube_api_key)
        self.twitch = TwitchService(twitch_client_id, twitch_client_secret)
        self.dev_guild_id = dev_guild_id
        self._enable_eventsub = enable_eventsub
        self.eventsub = None

    async def setup_hook(self) -> None:
        log.info("Connecting to database …")
        await self.db.connect()

        log.info("Loading cogs …")
        await self.load_extension("bot.cogs.admin")
        await self.load_extension("bot.cogs.settings")
        await self.load_extension("bot.cogs.stats")
        await self.load_extension("bot.cogs.refresh")

        if self.dev_guild_id:
            guild = discord.Object(id=self.dev_guild_id)
            self.tree.copy_global_to(guild=guild)
            log.info("Syncing slash commands to dev guild %s …", self.dev_guild_id)
            await self.tree.sync(guild=guild)
        else:
            log.info("Syncing slash commands globally …")
            await self.tree.sync()

        # Start Twitch EventSub WebSocket (optional)
        if self._enable_eventsub:
            self.eventsub = TwitchEventSub(
                self.twitch,
                on_channel_update=self._on_twitch_channel_update,
            )
            await self.eventsub.start()
            log.info("Twitch EventSub WebSocket enabled.")

        log.info("Bot is ready.")

    async def _on_twitch_channel_update(self, broadcaster_id: str) -> None:
        """Callback from EventSub – refresh the Twitch account across all guilds."""
        for guild in self.guilds:
            accounts = await self.db.get_all_linked(guild.id, "twitch")
            for acc in accounts:
                if acc["platform_id"] == broadcaster_id:
                    count = await self.twitch.get_follower_count(broadcaster_id)
                    if count is not None:
                        await self.db.update_account_count(
                            guild.id, acc["discord_user_id"], "twitch",
                            broadcaster_id, count,
                        )
                        member = guild.get_member(acc["discord_user_id"])
                        if member:
                            from bot.roles import compute_role_name_and_color, update_member_role, cleanup_unused_roles
                            settings = await self.db.get_guild_settings(guild.id)
                            role_name, role_color = await compute_role_name_and_color(
                                self.db, guild.id, "twitch", count,
                                settings, acc["platform_name"],
                            )
                            await update_member_role(
                                guild, member, "twitch",
                                acc["platform_name"], role_name, role_color,
                            )
                            await cleanup_unused_roles(guild, "twitch")
                        from bot.scoreboard import update_scoreboard
                        settings = await self.db.get_guild_settings(guild.id)
                        await update_scoreboard(self, guild, "twitch", settings)

    async def close(self) -> None:
        if self.eventsub:
            await self.eventsub.stop()
        await self.youtube.close()
        await self.twitch.close()
        await self.db.close()
        await super().close()

    async def on_ready(self) -> None:
        log.info("Logged in as %s (ID: %s)", self.user, self.user.id if self.user else "?")
