"""
Admin cog – link/unlink accounts, force refresh, view history.

All commands restricted to server administrators via Discord's
built-in permission system (default_permissions).
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from bot.bot import EXIT_CODE_UPDATE, SocialStatsBot
from bot.cogs import (
    PLATFORM_CHOICES,
    PLATFORM_COUNT_LABEL,
    PLATFORM_COLOUR_INT,
    PLATFORM_DISPLAY_NAME,
    PLATFORM_EMOJI,
    PlatformRateLimitError,
    detect_platform_from_url,
    fetch_count,
    resolve_platform,
)
from bot.roles import (
    compute_role_name_and_color,
    update_member_role,
    remove_account_roles,
    cleanup_unused_roles,
    PLATFORM_SETTINGS_PREFIX,
)
from bot.scoreboard import update_count_channel, update_scoreboard
from bot.pagination import PaginationView, paginate_lines
from bot.database import ALL_PLATFORMS

log = logging.getLogger(__name__)


class AdminCog(commands.GroupCog, group_name="admin"):
    """Admin commands for managing linked accounts."""

    def __init__(self, bot: SocialStatsBot) -> None:
        self.bot = bot

    # ── Autocomplete helpers ─────────────────────────────────────────

    async def _account_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete for account_name parameters (needs user + platform in namespace)."""
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

    # ── /admin link ────────────────────────────────────────────────

    @app_commands.command(
        name="link",
        description="Verknüpft einen Social-Media-Account mit einem Discord-User.",
    )
    @app_commands.describe(
        user="Discord-User",
        channel_input="Username oder URL des Accounts",
        platform="Plattform (optional bei URL-Eingabe)",
    )
    @app_commands.choices(platform=PLATFORM_CHOICES)
    async def link(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        channel_input: str,
        platform: app_commands.Choice[str] | None = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        # Resolve platform – explicit choice or auto-detect from URL
        if platform is not None:
            plat_key = platform.value
            plat_display = platform.name
        else:
            detected = detect_platform_from_url(channel_input)
            if detected is None:
                await interaction.followup.send(
                    "❌ Plattform konnte nicht erkannt werden.\n"
                    "Wähle die Plattform über den optionalen `plattform`-Parameter aus "
                    "(z.\u202fB. `plattform: Instagram`) oder gib eine vollständige URL an "
                    "(z.\u202fB. `https://www.instagram.com/meinkanal`).",
                    ephemeral=True,
                )
                return
            plat_key = detected
            plat_display = PLATFORM_DISPLAY_NAME[detected]

        try:
            info = await resolve_platform(self.bot, plat_key, channel_input)
        except PlatformRateLimitError:
            await interaction.followup.send(
                f"\u23f3 {plat_display} ist vor\u00fcbergehend nicht erreichbar (Rate-Limit). "
                "Bitte versuche es sp\u00e4ter erneut.",
                ephemeral=True,
            )
            return
        if info is None:
            await interaction.followup.send(
                f"❌ Konnte den {plat_display}-Kanal nicht finden. Prüfe die Eingabe.",
                ephemeral=True,
            )
            return
        platform_id = info["id"]
        platform_name = info["display_name"]
        count = info.get("subscriber_count", info.get("follower_count", 0))
        count_label = PLATFORM_COUNT_LABEL.get(plat_key, "Follower")

        await self.bot.db.link_account(
            interaction.guild_id, user.id, plat_key, platform_id, platform_name
        )
        await self.bot.db.update_account_count(
            interaction.guild_id, user.id, plat_key, platform_id, count
        )

        settings = await self.bot.db.get_guild_settings(interaction.guild_id)
        role_name, role_color = await compute_role_name_and_color(
            self.bot.db, interaction.guild_id, plat_key, count, settings, platform_name
        )
        await update_member_role(
            interaction.guild, user, plat_key, platform_name, role_name, role_color
        )
        # Update scoreboard & count-channel immediately (DB-only, no API re-fetch)
        await update_scoreboard(self.bot, interaction.guild, plat_key, settings)
        await update_count_channel(self.bot, interaction.guild, plat_key, settings)
        await interaction.followup.send(
            f"✅ **{platform_name}** ({plat_display}) mit {user.mention} verknüpft.\n"
            f"Aktuelle {count_label}: **{count:,}**".replace(",", "."),
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
    @app_commands.choices(platform=PLATFORM_CHOICES)
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
        # Update scoreboard & count-channel immediately (DB-only, no API re-fetch)
        settings = await self.bot.db.get_guild_settings(interaction.guild_id)
        await update_scoreboard(self.bot, interaction.guild, platform.value, settings)
        await update_count_channel(self.bot, interaction.guild, platform.value, settings)
        await interaction.followup.send(
            f"✅ **{platform_name}** ({platform.name}) von {user.mention} entfernt.",
            ephemeral=True,
        )

    @unlink.autocomplete("account_name")
    async def _unlink_account_ac(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return await self._account_autocomplete(interaction, current)

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

        from bot.database import ALL_PLATFORMS

        all_accounts: dict[str, list[dict]] = {}
        for plat in ALL_PLATFORMS:
            accs = await self.bot.db.get_linked_accounts_for_user(
                interaction.guild_id, user.id, plat
            )
            if accs:
                all_accounts[plat] = accs

        if not all_accounts:
            await interaction.followup.send(
                f"Keine Accounts für {user.mention} verknüpft.", ephemeral=True
            )
            return

        lines: list[str] = []
        for plat in ALL_PLATFORMS:
            accs = all_accounts.get(plat)
            if accs:
                if lines:
                    lines.append("")
                emoji = PLATFORM_EMOJI.get(plat, "")
                label = PLATFORM_DISPLAY_NAME.get(plat, plat.title())
                count_label = PLATFORM_COUNT_LABEL.get(plat, "Follower")
                lines.append(f"{emoji} **{label}:**")
                for acc in accs:
                    count = f"{acc['current_count']:,}".replace(",", ".")
                    lines.append(f"  • {acc['platform_name']} – {count} {count_label}")

        chunks = paginate_lines(lines, per_page=15)
        pages: list[discord.Embed] = []
        for i, chunk in enumerate(chunks):
            embed = discord.Embed(
                title=f"Accounts von {user.display_name}",
                description="\n".join(chunk),
            )
            embed.set_footer(text=f"Seite {i+1}/{len(chunks)}")
            pages.append(embed)

        if len(pages) == 1:
            await interaction.followup.send(embed=pages[0], ephemeral=True)
        else:
            view = PaginationView(pages, author_id=interaction.user.id)
            await interaction.followup.send(embed=pages[0], view=view, ephemeral=True)

    # ── /admin force_refresh ─────────────────────────────────────────

    @app_commands.command(
        name="force_refresh",
        description="Erzwingt eine sofortige Aktualisierung aller Accounts.",
    )
    @app_commands.describe(
        platform="Plattform (optional, sonst alle)",
    )
    @app_commands.choices(platform=PLATFORM_CHOICES)
    async def force_refresh(
        self,
        interaction: discord.Interaction,
        platform: app_commands.Choice[str] = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        platforms = [platform.value] if platform else list(ALL_PLATFORMS)
        settings = await self.bot.db.get_guild_settings(interaction.guild_id)
        total_updated = 0
        skipped_disabled: list[str] = []

        for plat in platforms:
            # Skip disabled platforms (unless explicitly requested)
            if not platform and not self.bot.db.is_platform_enabled(settings, plat):
                skipped_disabled.append(plat)
                continue

            accounts = await self.bot.db.get_all_linked(interaction.guild_id, plat)

            for acc in accounts:
                count = await fetch_count(self.bot, plat, acc)
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
            await update_count_channel(self.bot, interaction.guild, plat, settings)

        msg = f"✅ Refresh abgeschlossen. **{total_updated}** Account(s) aktualisiert."
        if skipped_disabled:
            names = ", ".join(p.title() for p in skipped_disabled)
            msg += f"\n⬛ Übersprungen (deaktiviert): {names}"
        await interaction.followup.send(msg, ephemeral=True)

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
    @app_commands.choices(platform=PLATFORM_CHOICES)
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
            interaction.guild_id, user.id, platform.value, account["platform_id"], limit=100
        )
        if not entries:
            await interaction.followup.send("Keine Historie vorhanden.", ephemeral=True)
            return

        label = PLATFORM_COUNT_LABEL.get(platform.value, "Follower")
        colour = PLATFORM_COLOUR_INT.get(platform.value, 0)
        lines: list[str] = []
        for e in entries:
            ts = datetime.fromtimestamp(e["recorded_at"], tz=timezone.utc)
            count_str = f"{e['count']:,}".replace(",", ".")
            lines.append(f"`{ts:%d.%m.%Y %H:%M}` – **{count_str}** {label}")

        chunks = paginate_lines(lines, per_page=15)
        pages: list[discord.Embed] = []
        for i, chunk in enumerate(chunks):
            embed = discord.Embed(
                title=f"📊 Historie – {account['platform_name']} ({platform.name})",
                description="\n".join(chunk),
                colour=discord.Colour(colour),
            )
            embed.set_footer(text=f"Seite {i+1}/{len(chunks)} • {len(entries)} Einträge")
            pages.append(embed)

        if len(pages) == 1:
            await interaction.followup.send(embed=pages[0], ephemeral=True)
        else:
            view = PaginationView(pages, author_id=interaction.user.id)
            await interaction.followup.send(embed=pages[0], view=view, ephemeral=True)

    @history.autocomplete("account_name")
    async def _history_account_ac(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return await self._account_autocomplete(interaction, current)

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

    # ── /admin update ────────────────────────────────────────────────

    # ── /admin setup ───────────────────────────────────────────────

    @app_commands.command(
        name="setup",
        description="Richtet alle Kanäle und Einstellungen automatisch ein.",
    )
    async def setup(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if not guild.me.guild_permissions.manage_channels:
            await interaction.response.send_message(
                "❌ Der Bot benötigt die Berechtigung **Kanäle verwalten**.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        # Create category
        category = await guild.create_category("📊 Social Stats")

        # Create channels under the category
        scoreboard_ch = await guild.create_text_channel("scoreboard", category=category)
        request_ch = await guild.create_text_channel("anfragen", category=category)
        status_ch = await guild.create_text_channel("bot-status", category=category)

        # Configure settings for each platform scoreboard → same channel
        for plat in ALL_PLATFORMS:
            prefix = PLATFORM_SETTINGS_PREFIX[plat]
            await self.bot.db.update_guild_setting(
                guild.id, f"{prefix}_scoreboard_channel_id", scoreboard_ch.id
            )

        # Configure request & status channels
        await self.bot.db.update_guild_setting(guild.id, "request_channel_id", request_ch.id)
        await self.bot.db.update_guild_setting(guild.id, "status_channel_id", status_ch.id)
        await self.bot.db.update_guild_setting(guild.id, "status_message_id", 0)

        # Trigger initial status update
        status_cog = self.bot.get_cog("StatusCog")
        if status_cog:
            await status_cog.force_update(guild)

        await interaction.followup.send(
            "✅ **Setup abgeschlossen!**\n\n"
            f"📋 **Kategorie:** {category.mention}\n"
            f"📊 **Scoreboard:** {scoreboard_ch.mention}\n"
            f"📬 **Anfragen:** {request_ch.mention}\n"
            f"🔧 **Bot-Status:** {status_ch.mention}\n\n"
            "Alle Plattform-Scoreboards werden in den Scoreboard-Kanal gepostet.\n"
            "Verknüpfe jetzt Accounts mit `/admin link`.",
            ephemeral=True,
        )

    # ── /admin update ────────────────────────────────────────────────

    @app_commands.command(
        name="update",
        description="Aktualisiert den Bot (git pull + rebuild).",
    )
    async def update(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            "🔄 Update wird gestartet … der Bot fährt jetzt herunter und wird vom Host-Skript neu gebaut.\n"
            "Nach dem Neustart wird das Ergebnis hier gepostet.",
            ephemeral=True,
        )
        log.info("Update requested by %s – shutting down with exit code %d.", interaction.user, EXIT_CODE_UPDATE)

        # Save context so the bot can report back after restart.
        # The interaction token is valid for 15 min – the host wrapper
        # and the bot use it to edit the original ephemeral response.
        pending = {
            "channel_id": interaction.channel_id,
            "user_id": interaction.user.id,
            "application_id": interaction.application_id,
            "interaction_token": interaction.token,
            "requested_at": datetime.now(timezone.utc).isoformat(),
        }
        pending_path = Path("data/pending_update.json")
        pending_path.parent.mkdir(parents=True, exist_ok=True)
        pending_path.write_text(json.dumps(pending), encoding="utf-8")

        # Set the exit code on the bot so main.py can propagate it, then shut down.
        self.bot.exit_code = EXIT_CODE_UPDATE
        await asyncio.sleep(2)
        await self.bot.close()


async def setup(bot: SocialStatsBot) -> None:
    await bot.add_cog(AdminCog(bot))
