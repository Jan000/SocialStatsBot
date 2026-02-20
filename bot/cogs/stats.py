"""
Stats cog – statistics and growth visualisation commands.

Provides growth analysis over configurable time periods (7/30/90 days).
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from bot.bot import SocialStatsBot
from bot.roles import format_count

log = logging.getLogger(__name__)

PERIOD_CHOICES = [
    app_commands.Choice(name="7 Tage", value=7),
    app_commands.Choice(name="30 Tage", value=30),
    app_commands.Choice(name="90 Tage", value=90),
]


class StatsCog(commands.GroupCog, group_name="stats"):
    """Statistics and growth visualisation commands."""

    def __init__(self, bot: SocialStatsBot) -> None:
        self.bot = bot

    # ── Autocomplete helpers ─────────────────────────────────────────

    async def _account_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete for account_name parameters."""
        guild_id = interaction.guild_id
        if not guild_id:
            return []

        user = getattr(interaction.namespace, "user", None)
        platform = getattr(interaction.namespace, "platform", None)
        if not user or not platform:
            return []

        user_id = user.id if hasattr(user, "id") else int(user)
        plat = platform.value if hasattr(platform, "value") else str(platform)

        accounts = await self.bot.db.get_linked_accounts_for_user(guild_id, user_id, plat)
        return [
            app_commands.Choice(name=a["platform_name"], value=a["platform_name"])
            for a in accounts
            if a["platform_name"] and current.lower() in a["platform_name"].lower()
        ][:25]

    # ── /stats growth ────────────────────────────────────────────────

    @app_commands.command(
        name="growth",
        description="Zeigt das Wachstum eines Accounts über einen Zeitraum.",
    )
    @app_commands.describe(
        user="Discord-User",
        platform="Plattform",
        account_name="Account-Name",
        period="Zeitraum",
    )
    @app_commands.choices(
        platform=[
            app_commands.Choice(name="YouTube", value="youtube"),
            app_commands.Choice(name="Twitch", value="twitch"),
        ],
        period=PERIOD_CHOICES,
    )
    async def growth(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        platform: app_commands.Choice[str],
        account_name: str,
        period: app_commands.Choice[int] = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        account = await self.bot.db.find_linked_account_by_name(
            interaction.guild_id, user.id, platform.value, account_name
        )
        if account is None:
            await interaction.followup.send(
                f"❌ Kein {platform.name}-Account **{account_name}** für {user.mention} gefunden.",
                ephemeral=True,
            )
            return

        days = period.value if period else 30
        since = time.time() - (days * 86400)

        history = await self.bot.db.get_history_since(
            interaction.guild_id, user.id, platform.value,
            account["platform_id"], since
        )
        if not history:
            await interaction.followup.send(
                f"Keine Daten für die letzten **{days} Tage** vorhanden.",
                ephemeral=True,
            )
            return

        current = account["current_count"]
        oldest = history[-1]  # oldest entry in the period (sorted DESC, so last)
        oldest_count = oldest["count"]
        diff = current - oldest_count

        if oldest_count > 0:
            pct = (diff / oldest_count) * 100
            pct_str = f"{pct:+.2f}%"
        else:
            pct_str = "n/a"

        label = "Abos" if platform.value == "youtube" else "Follower"
        emoji = "📺" if platform.value == "youtube" else "🎮"
        sign = "+" if diff >= 0 else ""

        oldest_ts = datetime.fromtimestamp(oldest["recorded_at"], tz=timezone.utc)

        embed = discord.Embed(
            title=f"{emoji} Wachstum – {account['platform_name']} ({platform.name})",
            colour=discord.Colour(0xFF0000) if platform.value == "youtube" else discord.Colour(0x6441A4),
        )
        embed.add_field(name="Zeitraum", value=f"Letzte **{days} Tage**", inline=True)
        embed.add_field(name=f"Aktuell", value=f"**{format_count(current)}** {label}", inline=True)
        embed.add_field(name=f"Vor {days} Tagen", value=f"**{format_count(oldest_count)}** {label}", inline=True)
        embed.add_field(name="Differenz", value=f"**{sign}{format_count(diff)}** ({pct_str})", inline=True)
        embed.add_field(name="Datenpunkte", value=str(len(history)), inline=True)
        embed.set_footer(text=f"Ältester Datenpunkt: {oldest_ts:%d.%m.%Y %H:%M} UTC")

        await interaction.followup.send(embed=embed, ephemeral=True)

    @growth.autocomplete("account_name")
    async def _growth_account_ac(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return await self._account_autocomplete(interaction, current)

    # ── /stats overview ──────────────────────────────────────────────

    @app_commands.command(
        name="overview",
        description="Zeigt eine Übersicht aller Accounts mit Wachstum.",
    )
    @app_commands.describe(
        platform="Plattform",
        period="Zeitraum",
    )
    @app_commands.choices(
        platform=[
            app_commands.Choice(name="YouTube", value="youtube"),
            app_commands.Choice(name="Twitch", value="twitch"),
        ],
        period=PERIOD_CHOICES,
    )
    async def overview(
        self,
        interaction: discord.Interaction,
        platform: app_commands.Choice[str],
        period: app_commands.Choice[int] = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        days = period.value if period else 30
        since = time.time() - (days * 86400)
        label = "Abos" if platform.value == "youtube" else "Follower"
        emoji = "📺" if platform.value == "youtube" else "🎮"

        accounts = await self.bot.db.get_all_linked(interaction.guild_id, platform.value)
        if not accounts:
            await interaction.followup.send(
                f"Keine {platform.name}-Accounts verknüpft.", ephemeral=True
            )
            return

        lines: list[str] = []
        for acc in accounts:
            member = interaction.guild.get_member(acc["discord_user_id"])
            name = member.display_name if member else f"User {acc['discord_user_id']}"
            pname = acc.get("platform_name", "")

            history = await self.bot.db.get_history_since(
                interaction.guild_id, acc["discord_user_id"], platform.value,
                acc["platform_id"], since
            )
            current = acc["current_count"]
            if history:
                oldest_count = history[-1]["count"]
                diff = current - oldest_count
                sign = "+" if diff >= 0 else ""
                diff_str = f" ({sign}{format_count(diff)})"
            else:
                diff_str = ""

            account_info = f" ({pname})" if pname else ""
            lines.append(
                f"• {name}{account_info} – **{format_count(current)}** {label}{diff_str}"
            )

        embed = discord.Embed(
            title=f"{emoji} {platform.name} Übersicht – Letzte {days} Tage",
            description="\n".join(lines),
            colour=discord.Colour(0xFF0000) if platform.value == "youtube" else discord.Colour(0x6441A4),
        )
        embed.set_footer(text=f"{len(accounts)} Account(s)")

        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── Error handler ────────────────────────────────────────────────

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        if isinstance(error, (app_commands.MissingPermissions, app_commands.CheckFailure)):
            msg = "❌ Du hast keine Berechtigung für diesen Befehl."
        else:
            log.error("Error in stats cog: %s", error, exc_info=error)
            msg = "❌ Ein unerwarteter Fehler ist aufgetreten."

        if not interaction.response.is_done():
            await interaction.response.send_message(msg, ephemeral=True)
        else:
            await interaction.followup.send(msg, ephemeral=True)


async def setup(bot: SocialStatsBot) -> None:
    await bot.add_cog(StatsCog(bot))
