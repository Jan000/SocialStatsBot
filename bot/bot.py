"""SocialStatsBot – main Bot class."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import discord
from discord.ext import commands

from bot.database import Database
from bot.services.youtube import YouTubeService
from bot.services.twitch import TwitchService
from bot.services.eventsub import TwitchEventSub

log = logging.getLogger(__name__)

# Special exit code that signals the host wrapper to run an update.
EXIT_CODE_UPDATE = 42


class SocialStatsBot(commands.Bot):
    """Discord bot that tracks YouTube subscribers and Twitch followers."""

    db: Database
    youtube: YouTubeService
    twitch: TwitchService
    eventsub: TwitchEventSub | None
    dev_guild_id: int | None
    exit_code: int  # set to EXIT_CODE_UPDATE for update-then-restart

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
        self.exit_code = 0

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
        await self._report_update_result()

    # ── Update result reporting ──────────────────────────────────────

    async def _report_update_result(self) -> None:
        """If a pending update exists, report success/failure to Discord."""
        pending_path = Path("data/pending_update.json")
        if not pending_path.exists():
            return

        try:
            pending = json.loads(pending_path.read_text(encoding="utf-8"))
            channel_id: int = pending["channel_id"]
            user_id: int = pending["user_id"]
            requested_at: str = pending.get("requested_at", "?")
        except (json.JSONDecodeError, KeyError, OSError) as exc:
            log.warning("Could not read pending_update.json: %s", exc)
            pending_path.unlink(missing_ok=True)
            return

        # Read the update log written by the host wrapper script.
        log_path = Path("data/update.log")
        log_text = ""
        has_error = False
        if log_path.exists():
            try:
                log_text = log_path.read_text(encoding="utf-8", errors="replace")
                has_error = "EXIT=error" in log_text
                # Remove the internal marker from the display text.
                log_text = log_text.replace("EXIT=error\n", "").replace("EXIT=error", "")
            except OSError as exc:
                log_text = f"(Log konnte nicht gelesen werden: {exc})"
                has_error = True

        # Build the embed.
        if has_error:
            colour = discord.Colour.red()
            title = "❌ Update mit Fehlern abgeschlossen"
        else:
            colour = discord.Colour.green()
            title = "✅ Update erfolgreich"

        embed = discord.Embed(title=title, colour=colour)
        embed.add_field(
            name="Angefordert von",
            value=f"<@{user_id}> um {requested_at}",
            inline=False,
        )

        if log_text.strip():
            # Discord embed field limit is 1024, description limit is 4096.
            # Put the log into the description for more room.
            truncated = log_text.strip()
            if len(truncated) > 3900:
                truncated = truncated[:3900] + "\n… (gekürzt)"
            embed.description = f"```\n{truncated}\n```"

        try:
            channel = self.get_channel(channel_id) or await self.fetch_channel(channel_id)
            await channel.send(embed=embed)  # type: ignore[union-attr]
            log.info("Posted update result to channel %s.", channel_id)
        except Exception as exc:
            log.warning("Could not post update result to channel %s: %s", channel_id, exc)

        # Clean up both files.
        pending_path.unlink(missing_ok=True)
        log_path.unlink(missing_ok=True)
