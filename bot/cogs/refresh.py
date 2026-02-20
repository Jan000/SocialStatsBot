"""
Refresh cog – periodic background tasks for updating counts, roles, and scoreboards.
"""

from __future__ import annotations

import logging

import discord
from discord.ext import commands, tasks

from bot.bot import SocialStatsBot
from bot.roles import (
    compute_role_name_and_color,
    update_member_role,
    cleanup_unused_roles,
)
from bot.scoreboard import update_scoreboard

log = logging.getLogger(__name__)


class RefreshCog(commands.Cog):
    """Background loop that periodically refreshes subscriber/follower counts."""

    def __init__(self, bot: SocialStatsBot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        self.refresh_loop.start()

    async def cog_unload(self) -> None:
        self.refresh_loop.cancel()

    @tasks.loop(seconds=30)
    async def refresh_loop(self) -> None:
        """Check all guilds for accounts that are due a refresh."""
        for guild in self.bot.guilds:
            try:
                await self._refresh_guild(guild)
            except Exception:
                log.exception("Error refreshing guild %s", guild.id)

    @refresh_loop.before_loop
    async def before_refresh(self) -> None:
        await self.bot.wait_until_ready()

    async def _refresh_guild(self, guild: discord.Guild) -> None:
        settings = await self.bot.db.get_guild_settings(guild.id)

        for platform in ("youtube", "twitch"):
            prefix = "yt" if platform == "youtube" else "tw"
            interval = settings.get(f"{prefix}_refresh_interval", 600)

            accounts = await self.bot.db.get_accounts_due_refresh(
                guild.id, platform, interval
            )
            if not accounts:
                continue

            any_updated = False
            for acc in accounts:
                count = await self._fetch_count(platform, acc)
                if count is None:
                    await self.bot.db.set_account_status(
                        guild.id, acc["discord_user_id"], platform,
                        acc["platform_id"], "error"
                    )
                    continue

                await self.bot.db.update_account_count(
                    guild.id, acc["discord_user_id"], platform,
                    acc["platform_id"], count
                )
                any_updated = True

                member = guild.get_member(acc["discord_user_id"])
                if member:
                    role_name, role_color = await compute_role_name_and_color(
                        self.bot.db, guild.id, platform, count,
                        settings, acc["platform_name"]
                    )
                    await update_member_role(
                        guild, member, platform,
                        acc["platform_name"], role_name, role_color
                    )

            if any_updated:
                await cleanup_unused_roles(guild, platform)
                await update_scoreboard(self.bot, guild, platform, settings)

    async def _fetch_count(self, platform: str, account: dict) -> int | None:
        if platform == "youtube":
            return await self.bot.youtube.get_subscriber_count(account["platform_id"])
        else:
            return await self.bot.twitch.get_follower_count(account["platform_id"])


async def setup(bot: SocialStatsBot) -> None:
    await bot.add_cog(RefreshCog(bot))
