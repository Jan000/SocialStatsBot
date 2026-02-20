"""
Admin cog – account linking/unlinking and status commands.
Only the admin user (from config.toml) can use these.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from bot.bot import SocialStatsBot
from bot.roles import compute_role_name_and_color, update_member_role, cleanup_unused_roles


def admin_only():
    """Decorator: restrict to the configured admin user."""

    async def predicate(interaction: discord.Interaction) -> bool:
        bot: SocialStatsBot = interaction.client  # type: ignore
        if not bot.is_admin(interaction.user.id):
            await interaction.response.send_message(
                "❌ Nur der Bot-Admin darf diesen Befehl verwenden.", ephemeral=True
            )
            return False
        return True

    return app_commands.check(predicate)


class AdminCog(commands.Cog, name="Admin"):
    """Admin-only commands for managing linked accounts."""

    def __init__(self, bot: SocialStatsBot) -> None:
        self.bot = bot

    # ── Link YouTube ─────────────────────────────────────────────────

    @app_commands.command(name="link_youtube", description="Verknüpfe einen Discord-User mit einem YouTube-Kanal.")
    @app_commands.describe(
        user="Der Discord-User",
        channel_id="Die YouTube-Channel-ID",
    )
    @admin_only()
    async def link_youtube(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        channel_id: str,
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        # Validate channel
        info = await self.bot.youtube.get_channel_info(channel_id)
        if info is None:
            await interaction.followup.send("❌ YouTube-Kanal nicht gefunden.", ephemeral=True)
            return

        await self.bot.db.link_account(
            guild_id=interaction.guild.id,
            discord_user_id=user.id,
            platform="youtube",
            platform_id=channel_id,
            platform_name=info["title"],
        )

        # Immediately fetch count
        count = info.get("subscriber_count", 0)
        await self.bot.db.update_account_count(
            interaction.guild.id, user.id, "youtube", count, "ok"
        )

        # Assign role
        settings = await self.bot.db.get_guild_settings(interaction.guild.id)
        role_name, role_color = await compute_role_name_and_color(
            self.bot.db, interaction.guild.id, "youtube", count, settings
        )
        await update_member_role(interaction.guild, user, "youtube", role_name, role_color)
        await cleanup_unused_roles(interaction.guild, "youtube")

        await interaction.followup.send(
            f"✅ **{user.display_name}** ↔ YouTube **{info['title']}** ({count:,} Abos) verknüpft.",
            ephemeral=True,
        )

    # ── Link Twitch ──────────────────────────────────────────────────

    @app_commands.command(name="link_twitch", description="Verknüpfe einen Discord-User mit einem Twitch-Account.")
    @app_commands.describe(
        user="Der Discord-User",
        twitch_login="Der Twitch-Loginname",
    )
    @admin_only()
    async def link_twitch(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        twitch_login: str,
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        tw_user = await self.bot.twitch.get_user(twitch_login)
        if tw_user is None:
            await interaction.followup.send("❌ Twitch-User nicht gefunden.", ephemeral=True)
            return

        broadcaster_id = tw_user["id"]
        display_name = tw_user.get("display_name", twitch_login)

        await self.bot.db.link_account(
            guild_id=interaction.guild.id,
            discord_user_id=user.id,
            platform="twitch",
            platform_id=broadcaster_id,
            platform_name=display_name,
        )

        count = await self.bot.twitch.get_follower_count(broadcaster_id) or 0
        await self.bot.db.update_account_count(
            interaction.guild.id, user.id, "twitch", count, "ok"
        )

        settings = await self.bot.db.get_guild_settings(interaction.guild.id)
        role_name, role_color = await compute_role_name_and_color(
            self.bot.db, interaction.guild.id, "twitch", count, settings
        )
        await update_member_role(interaction.guild, user, "twitch", role_name, role_color)
        await cleanup_unused_roles(interaction.guild, "twitch")

        await interaction.followup.send(
            f"✅ **{user.display_name}** ↔ Twitch **{display_name}** ({count:,} Follower) verknüpft.",
            ephemeral=True,
        )

    # ── Unlink ───────────────────────────────────────────────────────

    @app_commands.command(name="unlink", description="Entferne die Verknüpfung eines Users mit YouTube oder Twitch.")
    @app_commands.describe(
        user="Der Discord-User",
        platform="youtube oder twitch",
    )
    @app_commands.choices(platform=[
        app_commands.Choice(name="YouTube", value="youtube"),
        app_commands.Choice(name="Twitch", value="twitch"),
    ])
    @admin_only()
    async def unlink(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        platform: app_commands.Choice[str],
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        removed = await self.bot.db.unlink_account(
            interaction.guild.id, user.id, platform.value
        )
        if not removed:
            await interaction.followup.send(
                f"❌ Keine {platform.name}-Verknüpfung für **{user.display_name}** gefunden.",
                ephemeral=True,
            )
            return

        # Remove platform roles
        prefix = "[YT] " if platform.value == "youtube" else "[TW] "
        roles_to_remove = [r for r in user.roles if r.name.startswith(prefix)]
        if roles_to_remove:
            await user.remove_roles(*roles_to_remove, reason="NirukiSocialStats – unlink")
        await cleanup_unused_roles(interaction.guild, platform.value)

        await interaction.followup.send(
            f"✅ {platform.name}-Verknüpfung für **{user.display_name}** entfernt.",
            ephemeral=True,
        )

    # ── List linked accounts ─────────────────────────────────────────

    @app_commands.command(name="list_accounts", description="Zeige alle verknüpften Accounts auf diesem Server.")
    @app_commands.describe(platform="youtube oder twitch")
    @app_commands.choices(platform=[
        app_commands.Choice(name="YouTube", value="youtube"),
        app_commands.Choice(name="Twitch", value="twitch"),
    ])
    @admin_only()
    async def list_accounts(
        self,
        interaction: discord.Interaction,
        platform: app_commands.Choice[str],
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        accounts = await self.bot.db.get_all_linked(interaction.guild.id, platform.value)
        if not accounts:
            await interaction.followup.send(
                f"Keine {platform.name}-Accounts verknüpft.", ephemeral=True
            )
            return

        lines: list[str] = []
        for acc in accounts:
            member = interaction.guild.get_member(acc["discord_user_id"])
            name = member.display_name if member else f"User {acc['discord_user_id']}"
            pname = acc.get("platform_name") or acc["platform_id"]
            count = acc["current_count"]
            lines.append(f"• **{name}** → {pname} ({count:,})")

        embed = discord.Embed(
            title=f"Verknüpfte {platform.name}-Accounts",
            description="\n".join(lines),
            color=0xFF0000 if platform.value == "youtube" else 0x6441A4,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── Refresh status ───────────────────────────────────────────────

    @app_commands.command(name="refresh_status", description="Zeige den Refresh-Status aller verknüpften Accounts.")
    @app_commands.describe(platform="youtube oder twitch")
    @app_commands.choices(platform=[
        app_commands.Choice(name="YouTube", value="youtube"),
        app_commands.Choice(name="Twitch", value="twitch"),
    ])
    @admin_only()
    async def refresh_status(
        self,
        interaction: discord.Interaction,
        platform: app_commands.Choice[str],
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        settings = await self.bot.db.get_guild_settings(interaction.guild.id)
        interval_key = "yt_refresh_interval" if platform.value == "youtube" else "tw_refresh_interval"
        interval = settings.get(interval_key, 600)

        accounts = await self.bot.db.get_all_linked(interaction.guild.id, platform.value)
        if not accounts:
            await interaction.followup.send(
                f"Keine {platform.name}-Accounts verknüpft.", ephemeral=True
            )
            return

        lines: list[str] = []
        now = time.time()
        for acc in accounts:
            member = interaction.guild.get_member(acc["discord_user_id"])
            name = member.display_name if member else f"User {acc['discord_user_id']}"
            last = acc["last_refreshed"]
            status = acc["last_status"]

            if last > 0:
                last_dt = datetime.fromtimestamp(last, tz=timezone.utc)
                last_str = discord.utils.format_dt(last_dt, style="R")
                next_refresh = last + interval
                if next_refresh > now:
                    next_dt = datetime.fromtimestamp(next_refresh, tz=timezone.utc)
                    next_str = discord.utils.format_dt(next_dt, style="R")
                else:
                    next_str = "**jetzt fällig**"
            else:
                last_str = "nie"
                next_str = "**jetzt fällig**"

            emoji = "✅" if status == "ok" else "⏳" if status == "pending" else "❌"
            lines.append(
                f"{emoji} **{name}** – Letzter Refresh: {last_str} | Nächster: {next_str} | Status: `{status}`"
            )

        embed = discord.Embed(
            title=f"{platform.name} Refresh-Status",
            description="\n".join(lines),
            color=0xFF0000 if platform.value == "youtube" else 0x6441A4,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── Manual refresh ───────────────────────────────────────────────

    @app_commands.command(name="force_refresh", description="Erzwinge einen sofortigen Refresh für einen User.")
    @app_commands.describe(
        user="Der Discord-User",
        platform="youtube oder twitch",
    )
    @app_commands.choices(platform=[
        app_commands.Choice(name="YouTube", value="youtube"),
        app_commands.Choice(name="Twitch", value="twitch"),
    ])
    @admin_only()
    async def force_refresh(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        platform: app_commands.Choice[str],
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        acc = await self.bot.db.get_linked_account(
            interaction.guild.id, user.id, platform.value
        )
        if acc is None:
            await interaction.followup.send(
                f"❌ Keine {platform.name}-Verknüpfung für **{user.display_name}** gefunden.",
                ephemeral=True,
            )
            return

        # Fetch new count
        if platform.value == "youtube":
            count = await self.bot.youtube.get_subscriber_count(acc["platform_id"])
        else:
            count = await self.bot.twitch.get_follower_count(acc["platform_id"])

        if count is None:
            await self.bot.db.set_account_status(
                interaction.guild.id, user.id, platform.value, "error"
            )
            await interaction.followup.send(
                f"❌ Konnte {platform.name}-Daten nicht abrufen.", ephemeral=True
            )
            return

        old_count = acc["current_count"]
        await self.bot.db.update_account_count(
            interaction.guild.id, user.id, platform.value, count, "ok"
        )

        # Update role
        settings = await self.bot.db.get_guild_settings(interaction.guild.id)
        role_name, role_color = await compute_role_name_and_color(
            self.bot.db, interaction.guild.id, platform.value, count, settings
        )
        await update_member_role(interaction.guild, user, platform.value, role_name, role_color)
        await cleanup_unused_roles(interaction.guild, platform.value)

        diff = count - old_count
        diff_str = f"+{diff}" if diff >= 0 else str(diff)
        await interaction.followup.send(
            f"✅ **{user.display_name}** {platform.name}: {old_count:,} → {count:,} ({diff_str})",
            ephemeral=True,
        )

    # ── Account history ──────────────────────────────────────────────

    @app_commands.command(name="history", description="Zeige die letzten Änderungen für einen verknüpften Account.")
    @app_commands.describe(
        user="Der Discord-User",
        platform="youtube oder twitch",
        limit="Anzahl Einträge (Standard: 20)",
    )
    @app_commands.choices(platform=[
        app_commands.Choice(name="YouTube", value="youtube"),
        app_commands.Choice(name="Twitch", value="twitch"),
    ])
    @admin_only()
    async def history(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        platform: app_commands.Choice[str],
        limit: int = 20,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        records = await self.bot.db.get_history(
            interaction.guild.id, user.id, platform.value, limit
        )
        if not records:
            await interaction.followup.send("Keine Historie vorhanden.", ephemeral=True)
            return

        lines: list[str] = []
        for i, rec in enumerate(records):
            dt = datetime.fromtimestamp(rec["recorded_at"], tz=timezone.utc)
            ts = discord.utils.format_dt(dt, style="f")
            count = rec["count"]
            if i + 1 < len(records):
                prev = records[i + 1]["count"]
                diff = count - prev
                diff_str = f" ({'+' if diff >= 0 else ''}{diff})"
            else:
                diff_str = ""
            lines.append(f"{ts} – **{count:,}**{diff_str}")

        embed = discord.Embed(
            title=f"{platform.name}-Historie für {user.display_name}",
            description="\n".join(lines),
            color=0xFF0000 if platform.value == "youtube" else 0x6441A4,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: SocialStatsBot) -> None:
    await bot.add_cog(AdminCog(bot))
