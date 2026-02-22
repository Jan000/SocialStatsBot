"""Status cog – periodic status-message updates in a configurable admin channel."""

from __future__ import annotations

import logging
import time

import discord
from discord.ext import commands, tasks

from bot.bot import SocialStatsBot
from bot.status import build_status_embed

log = logging.getLogger(__name__)


class StatusCog(commands.Cog):
    """Background loop that periodically updates the admin status message."""

    def __init__(self, bot: SocialStatsBot) -> None:
        self.bot = bot
        # guild_id -> monotonic timestamp of last status update
        self._last_update: dict[int, float] = {}

    async def cog_load(self) -> None:
        self.status_loop.start()

    async def cog_unload(self) -> None:
        self.status_loop.cancel()

    @tasks.loop(seconds=10)
    async def status_loop(self) -> None:
        """Check all guilds and update status messages when due."""
        for guild in self.bot.guilds:
            try:
                await self._maybe_update_guild(guild)
            except Exception:
                log.exception("Error updating status for guild %s", guild.id)

    @status_loop.before_loop
    async def before_status(self) -> None:
        await self.bot.wait_until_ready()

    async def _maybe_update_guild(self, guild: discord.Guild) -> None:
        settings = await self.bot.db.get_guild_settings(guild.id)
        channel_id = settings.get("status_channel_id", 0)
        if not channel_id:
            return

        # Respect per-guild status refresh interval
        interval = settings.get("status_refresh_interval", 30)
        now = time.monotonic()
        last = self._last_update.get(guild.id, 0.0)
        if now - last < interval:
            return
        self._last_update[guild.id] = now

        channel = guild.get_channel(channel_id)
        if channel is None:
            return

        embed = await build_status_embed(self.bot, guild)
        message_id = settings.get("status_message_id", 0)

        if message_id:
            try:
                msg = await channel.fetch_message(message_id)
                await msg.edit(embed=embed)
                return
            except (discord.NotFound, discord.HTTPException):
                pass

        # Send new message and persist its ID
        try:
            msg = await channel.send(embed=embed)
            await self.bot.db.update_guild_setting(
                guild.id, "status_message_id", msg.id
            )
        except discord.Forbidden:
            log.error(
                "Cannot send status to channel %s in guild %s",
                channel_id, guild.id,
            )

    async def force_update(self, guild: discord.Guild) -> None:
        """Force an immediate status update (called from settings commands)."""
        self._last_update.pop(guild.id, None)
        await self._maybe_update_guild(guild)


async def setup(bot: SocialStatsBot) -> None:
    await bot.add_cog(StatusCog(bot))
