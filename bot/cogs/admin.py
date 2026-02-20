"""
Admin cog – link/unlink accounts, force refresh, view history.

All commands restricted to server administrators via Discord's
built-in permission system (default_permissions).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from bot.bot import SocialStatsBot
from bot.roles import (
    compute_role_name_and_color,
    update_member_role,
    remove_account_roles,
    cleanup_unused_roles,
)
from bot.scoreboard import update_scoreboard

log = logging.getLogger(__name__)


@app_commands.default_permissions(administrator=True)
class AdminCog(commands.GroupCog, group_name="admin"):
    """Admin commands for managing linked accounts."""

    def __init__(self, bot: SocialStatsBot) -> None:
        self.bot = bot

    # ── /admin link_youtube ──────────────────────────────────────────

    @app_commands.command(
        name="link_youtube",
        description="Verknüpft einen YouTube-Kanal mit einem Discord-User.",
    )
    @app_commands.describe(
        user="Discord-User",
        channel_input="YouTube-Kanal (URL, @Handle oder Channel-ID)",
    )
    async def link_youtube(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        channel_input: str,
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        info = await self.bot.youtube.resolve_channel(channel_input)
        if info is None:
            await interaction.followup.send(
                "❌ Konnte den YouTube-Kanal nicht finden. Prüfe die Eingabe.",
                ephemeral=True,
            )
            return

        channel_id = info["id"]
        channel_name = info["title"]
        sub_count = info["subscriber_count"]

        await self.bot.db.link_account(
            interaction.guild_id, user.id, "youtube", channel_id, channel_name
        )
        await self.bot.db.update_account_count(
            interaction.guild_id, user.id, "youtube", channel_id, sub_count
        )

        # Assign role
        settings = await self.bot.db.get_guild_settings(interaction.guild_id)
        role_name, role_color = await compute_role_name_and_color(
            self.bot.db, interaction.guild_id, "youtube", sub_count, settings, channel_name
        )
        await update_member_role(
            interaction.guild, user, "youtube", channel_name, role_name, role_color
        )

        await interaction.followup.send(
            f"✅ **{channel_name}** (YouTube) mit {user.mention} verknüpft.\n"
            f"Aktuelle Abos: **{sub_count:,}**".replace(",", "."),
            ephemeral=True,
        )

    # ── /admin link_twitch ───────────────────────────────────────────

    @app_commands.command(
        name="link_twitch",
        description="Verknüpft einen Twitch-Kanal mit einem Discord-User.",
    )
    @app_commands.describe(
        user="Discord-User",
        channel_input="Twitch-Kanal (URL oder Login-Name)",
    )
    async def link_twitch(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        channel_input: str,
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        info = await self.bot.twitch.get_channel_info(channel_input)
        if info is None:
            await interaction.followup.send(
                "❌ Konnte den Twitch-Kanal nicht finden. Prüfe die Eingabe.",
                ephemeral=True,
            )
            return

        twitch_id = info["id"]
        display_name = info["display_name"]
        follower_count = info["follower_count"]

        await self.bot.db.link_account(
            interaction.guild_id, user.id, "twitch", twitch_id, display_name
        )
        await self.bot.db.update_account_count(
            interaction.guild_id, user.id, "twitch", twitch_id, follower_count
        )

        settings = await self.bot.db.get_guild_settings(interaction.guild_id)
        role_name, role_color = await compute_role_name_and_color(
            self.bot.db, interaction.guild_id, "twitch", follower_count, settings, display_name
        )
        await update_member_role(
            interaction.guild, user, "twitch", display_name, role_name, role_color
        )

        await interaction.followup.send(
            f"✅ **{display_name}** (Twitch) mit {user.mention} verknüpft.\n"
            f"Aktuelle Follower: **{follower_count:,}**".replace(",", "."),
            ephemeral=True,
        )

    # ── /admin unlink ────────────────────────────────────────────────

    @app_commands.command(
        name="unlink",
        description="Entfernt die Verknüpfung eines Accounts von einem Discord-User.",
    )
    @app_commands.describe(
        user="Discord-User",
        platform="Plattform",
        account_name="Name des Accounts (z.B. Niruki)",
    )
    @app_commands.choices(
        platform=[
            app_commands.Choice(name="YouTube", value="youtube"),
            app_commands.Choice(name="Twitch", value="twitch"),
        ]
    )
    async def unlink(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        platform: app_commands.Choice[str],
        account_name: str,
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        account = await self.bot.db.find_linked_account_by_name(
            interaction.guild_id, user.id, platform.value, account_name
        )
        if account is None:
            await interaction.followup.send(
                f"❌ Kein {platform.name}-Account mit dem Namen **{account_name}** "
                f"für {user.mention} gefunden.",
                ephemeral=True,
            )
            return

        platform_name = account["platform_name"]
        await self.bot.db.unlink_account(
            interaction.guild_id, user.id, platform.value, account["platform_id"]
        )

        # Remove account-specific roles
        await remove_account_roles(interaction.guild, user, platform.value, platform_name)
        await cleanup_unused_roles(interaction.guild, platform.value)

        await interaction.followup.send(
            f"✅ **{platform_name}** ({platform.name}) von {user.mention} entfernt.",
            ephemeral=True,
        )

    # ── /admin accounts ──────────────────────────────────────────────

    @app_commands.command(
        name="accounts",
        description="Zeigt alle verknüpften Accounts eines Users.",
    )
    @app_commands.describe(user="Discord-User")
    async def accounts(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        yt_accounts = await self.bot.db.get_linked_accounts_for_user(
            interaction.guild_id, user.id, "youtube"
        )
        tw_accounts = await self.bot.db.get_linked_accounts_for_user(
            interaction.guild_id, user.id, "twitch"
        )

        if not yt_accounts and not tw_accounts:
            await interaction.followup.send(
                f"Keine Accounts für {user.mention} verknüpft.", ephemeral=True
            )
            return

        lines: list[str] = [f"**Accounts von {user.display_name}:**\n"]
        if yt_accounts:
            lines.append("📺 **YouTube:**")
            for acc in yt_accounts:
                count = f"{acc['current_count']:,}".replace(",", ".")
                lines.append(f"  • {acc['platform_name']} – {count} Abos")
        if tw_accounts:
            lines.append("🎮 **Twitch:**")
            for acc in tw_accounts:
                count = f"{acc['current_count']:,}".replace(",", ".")
                lines.append(f"  • {acc['platform_name']} – {count} Follower")

        await interaction.followup.send("\n".join(lines), ephemeral=True)

    # ── /admin force_refresh ─────────────────────────────────────────

    @app_commands.command(
        name="force_refresh",
        description="Erzwingt eine sofortige Aktualisierung aller Accounts.",
    )
    @app_commands.describe(
        platform="Plattform (optional, sonst beide)",
    )
    @app_commands.choices(
        platform=[
            app_commands.Choice(name="YouTube", value="youtube"),
            app_commands.Choice(name="Twitch", value="twitch"),
        ]
    )
    async def force_refresh(
        self,
        interaction: discord.Interaction,
        platform: app_commands.Choice[str] = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        platforms = [platform.value] if platform else ["youtube", "twitch"]
        total_updated = 0

        for plat in platforms:
            accounts = await self.bot.db.get_all_linked(interaction.guild_id, plat)
            settings = await self.bot.db.get_guild_settings(interaction.guild_id)

            for acc in accounts:
                count = await self._fetch_count(plat, acc)
                if count is None:
                    await self.bot.db.set_account_status(
                        interaction.guild_id, acc["discord_user_id"], plat,
                        acc["platform_id"], "error"
                    )
                    continue

                await self.bot.db.update_account_count(
                    interaction.guild_id, acc["discord_user_id"], plat,
                    acc["platform_id"], count
                )
                total_updated += 1

                member = interaction.guild.get_member(acc["discord_user_id"])
                if member:
                    role_name, role_color = await compute_role_name_and_color(
                        self.bot.db, interaction.guild_id, plat, count,
                        settings, acc["platform_name"]
                    )
                    await update_member_role(
                        interaction.guild, member, plat,
                        acc["platform_name"], role_name, role_color
                    )

            await cleanup_unused_roles(interaction.guild, plat)
            await update_scoreboard(self.bot, interaction.guild, plat, settings)

        await interaction.followup.send(
            f"✅ Refresh abgeschlossen. **{total_updated}** Account(s) aktualisiert.",
            ephemeral=True,
        )

    # ── /admin history ───────────────────────────────────────────────

    @app_commands.command(
        name="history",
        description="Zeigt die Zähler-Historie eines Accounts.",
    )
    @app_commands.describe(
        user="Discord-User",
        platform="Plattform",
        account_name="Account-Name",
    )
    @app_commands.choices(
        platform=[
            app_commands.Choice(name="YouTube", value="youtube"),
            app_commands.Choice(name="Twitch", value="twitch"),
        ]
    )
    async def history(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        platform: app_commands.Choice[str],
        account_name: str,
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

        entries = await self.bot.db.get_history(
            interaction.guild_id, user.id, platform.value, account["platform_id"], limit=20
        )
        if not entries:
            await interaction.followup.send("Keine Historie vorhanden.", ephemeral=True)
            return

        label = "Abos" if platform.value == "youtube" else "Follower"
        lines = [f"📊 **Historie für {account['platform_name']} ({platform.name}):**\n"]
        for e in entries:
            ts = datetime.fromtimestamp(e["recorded_at"], tz=timezone.utc)
            count_str = f"{e['count']:,}".replace(",", ".")
            lines.append(f"`{ts:%d.%m.%Y %H:%M}` – **{count_str}** {label}")

        await interaction.followup.send("\n".join(lines), ephemeral=True)

    # ── Helpers ──────────────────────────────────────────────────────

    async def _fetch_count(self, platform: str, account: dict) -> int | None:
        """Fetch the current count for an account."""
        if platform == "youtube":
            return await self.bot.youtube.get_subscriber_count(account["platform_id"])
        else:
            return await self.bot.twitch.get_follower_count(account["platform_id"])

    # ── Error handler ────────────────────────────────────────────────

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        if isinstance(error, app_commands.MissingPermissions) or isinstance(
            error, app_commands.CheckFailure
        ):
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ Du hast keine Berechtigung für diesen Befehl.",
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(
                    "❌ Du hast keine Berechtigung für diesen Befehl.",
                    ephemeral=True,
                )
        elif isinstance(error, app_commands.CommandInvokeError) and isinstance(
            error.original, discord.Forbidden
        ):
            msg = (
                "❌ Dem Bot fehlen Berechtigungen (z.B. Rollen verwalten). "
                "Bitte prüfe die Servereinstellungen."
            )
            if not interaction.response.is_done():
                await interaction.response.send_message(msg, ephemeral=True)
            else:
                await interaction.followup.send(msg, ephemeral=True)
        else:
            log.error("Unhandled error in admin cog: %s", error, exc_info=error)
            msg = "❌ Ein unerwarteter Fehler ist aufgetreten."
            if not interaction.response.is_done():
                await interaction.response.send_message(msg, ephemeral=True)
            else:
                await interaction.followup.send(msg, ephemeral=True)


async def setup(bot: SocialStatsBot) -> None:
    await bot.add_cog(AdminCog(bot))
