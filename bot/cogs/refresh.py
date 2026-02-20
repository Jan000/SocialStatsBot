"""
Refresh cog – periodic background tasks that:
  1. Refresh YouTube subscriber / Twitch follower counts
  2. Update Discord roles accordingly
  3. Update scoreboard messages
"""

from __future__ import annotations

import asyncio
import traceback

import discord
from discord.ext import commands, tasks

from bot.bot import SocialStatsBot
from bot.roles import compute_role_name_and_color, update_member_role, cleanup_unused_roles
from bot.scoreboard import update_scoreboard


class RefreshCog(commands.Cog, name="Refresh"):
    """Background refresh loop for subscriber/follower counts."""

    def __init__(self, bot: SocialStatsBot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        self.refresh_loop.start()

    async def cog_unload(self) -> None:
        self.refresh_loop.cancel()

    @tasks.loop(seconds=30)
    async def refresh_loop(self) -> None:
        """
        Runs every 30 seconds.  For each guild, checks which accounts are
        due for a refresh (based on the per-guild interval) and updates them.
        """
        await self.bot.wait_until_ready()

        for guild in self.bot.guilds:
            try:
                await self._refresh_guild(guild)
            except Exception:
                traceback.print_exc()

    async def _refresh_guild(self, guild: discord.Guild) -> None:
        settings = await self.bot.db.get_guild_settings(guild.id)

        for platform in ("youtube", "twitch"):
            interval_key = f"{'yt' if platform == 'youtube' else 'tw'}_refresh_interval"
            interval = settings.get(interval_key, 600)

            due = await self.bot.db.get_accounts_due_refresh(guild.id, platform, interval)
            if not due:
                continue

            any_changed = False
            for acc in due:
                changed = await self._refresh_account(guild, acc, platform, settings)
                if changed:
                    any_changed = True
                # Small delay to avoid rate limits
                await asyncio.sleep(0.5)

            if any_changed:
                await cleanup_unused_roles(guild, platform)
                await update_scoreboard(self.bot, self.bot.db, guild, platform, settings)

    async def _refresh_account(
        self,
        guild: discord.Guild,
        acc: dict,
        platform: str,
        settings: dict,
    ) -> bool:
        """Refresh a single account. Returns True if the count changed."""
        platform_id = acc["platform_id"]
        discord_user_id = acc["discord_user_id"]
        old_count = acc["current_count"]

        # Fetch new count
        if platform == "youtube":
            count = await self.bot.youtube.get_subscriber_count(platform_id)
        else:
            count = await self.bot.twitch.get_follower_count(platform_id)

        if count is None:
            await self.bot.db.set_account_status(
                guild.id, discord_user_id, platform, "error"
            )
            return False

        # Store new count + history entry
        await self.bot.db.update_account_count(
            guild.id, discord_user_id, platform, count, "ok"
        )

        # Update role if count changed
        if count != old_count:
            member = guild.get_member(discord_user_id)
            if member:
                role_name, role_color = await compute_role_name_and_color(
                    self.bot.db, guild.id, platform, count, settings
                )
                await update_member_role(guild, member, platform, role_name, role_color)
            return True

        return False


async def setup(bot: SocialStatsBot) -> None:
    await bot.add_cog(RefreshCog(bot))
