"""
Request cog – lets any user submit link/unlink requests for approval.

Requests are validated (API check + DB duplicate check) and posted
to a configurable admin channel with Accept / Reject buttons.

Users can also submit link requests via a button on the scoreboard
messages (opens a Modal dialog).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from bot.bot import SocialStatsBot
from bot.cogs import (
    PLATFORM_CHOICES,
    PLATFORM_COUNT_LABEL,
    PLATFORM_COLOUR_INT,
    PLATFORM_DISPLAY_NAME,
    PLATFORM_EMOJI,
    PlatformRateLimitError,
    detect_platform_from_url,
    resolve_platform,
)
from bot.roles import (
    compute_role_name_and_color,
    update_member_role,
    remove_account_roles,
    cleanup_unused_roles,
)
from bot.scoreboard import update_count_channel, update_scoreboard

log = logging.getLogger(__name__)

# Platform-specific placeholder hints shown in the scoreboard link modal.
_PLATFORM_PLACEHOLDER: dict[str, str] = {
    "youtube": "@MeinKanal oder https://www.youtube.com/@MeinKanal",
    "twitch": "meinkanal oder https://www.twitch.tv/meinkanal",
    "instagram": "meinkanal oder https://www.instagram.com/meinkanal",
    "tiktok": "@meinkanal oder https://www.tiktok.com/@meinkanal",
}


# ── Persistent view for Accept / Reject buttons ─────────────────────


class RequestDecisionView(discord.ui.View):
    """Persistent view with Accept / Reject buttons for account requests."""

    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Annehmen",
        style=discord.ButtonStyle.success,
        custom_id="request_accept",
        emoji="✅",
    )
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._handle_decision(interaction, approved=True)

    @discord.ui.button(
        label="Ablehnen",
        style=discord.ButtonStyle.danger,
        custom_id="request_reject",
        emoji="❌",
    )
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._handle_decision(interaction, approved=False)

    async def _handle_decision(self, interaction: discord.Interaction, *, approved: bool) -> None:
        await interaction.response.defer(ephemeral=True)
        bot: SocialStatsBot = interaction.client  # type: ignore[assignment]

        # Extract request_id from the embed footer
        embed = interaction.message.embeds[0] if interaction.message and interaction.message.embeds else None
        if embed is None or not embed.footer or not embed.footer.text:
            await interaction.followup.send("❌ Konnte die Anfrage nicht finden.", ephemeral=True)
            return

        try:
            request_id = int(embed.footer.text.split("#")[1])
        except (IndexError, ValueError):
            await interaction.followup.send("❌ Ungültiges Anfrage-Format.", ephemeral=True)
            return

        req = await bot.db.get_account_request(request_id)
        if req is None:
            await interaction.followup.send("❌ Anfrage nicht gefunden.", ephemeral=True)
            return
        if req["status"] != "pending":
            await interaction.followup.send(
                f"ℹ️ Diese Anfrage wurde bereits bearbeitet (Status: {req['status']}).",
                ephemeral=True,
            )
            return

        guild = interaction.guild
        if guild is None:
            return

        # Fetch the member who made the request
        try:
            member = guild.get_member(req["discord_user_id"]) or await guild.fetch_member(
                req["discord_user_id"]
            )
        except discord.NotFound:
            member = None

        status_label: str
        result_msg: str

        if approved:
            status_label = "approved"
            platform = req["platform"]
            platform_name = req["platform_name"]
            platform_id = req["platform_id"]
            plat_display = PLATFORM_DISPLAY_NAME.get(platform, platform)

            if req["request_type"] == "link":
                if member is None:
                    await interaction.followup.send(
                        "❌ Der User ist nicht mehr auf dem Server.", ephemeral=True,
                    )
                    return

                # Execute the link
                await bot.db.link_account(
                    guild.id, req["discord_user_id"], platform, platform_id, platform_name,
                )
                await bot.db.update_account_count(
                    guild.id, req["discord_user_id"], platform, platform_id, req["follower_count"],
                )

                settings = await bot.db.get_guild_settings(guild.id)
                role_name, role_color = await compute_role_name_and_color(
                    bot.db, guild.id, platform, req["follower_count"], settings, platform_name,
                )
                await update_member_role(guild, member, platform, platform_name, role_name, role_color)

                # Update scoreboard & count-channel immediately
                await update_scoreboard(bot, guild, platform, settings)
                await update_count_channel(bot, guild, platform, settings)

                count_label = PLATFORM_COUNT_LABEL.get(platform, "Follower")
                result_msg = (
                    f"✅ **{platform_name}** ({plat_display}) mit <@{req['discord_user_id']}> verknüpft. "
                    f"({req['follower_count']:,} {count_label})".replace(",", ".")
                )

            else:  # unlink
                if member is not None:
                    await remove_account_roles(guild, member, platform, platform_name)
                await bot.db.unlink_account(
                    guild.id, req["discord_user_id"], platform, platform_id,
                )
                await cleanup_unused_roles(guild, platform)

                # Update scoreboard & count-channel immediately
                settings = await bot.db.get_guild_settings(guild.id)
                await update_scoreboard(bot, guild, platform, settings)
                await update_count_channel(bot, guild, platform, settings)

                result_msg = (
                    f"✅ **{platform_name}** ({plat_display}) von <@{req['discord_user_id']}> entfernt."
                )
        else:
            status_label = "rejected"
            result_msg = f"❌ Anfrage #{request_id} abgelehnt."

        await bot.db.update_request_status(request_id, status_label)

        # Update the embed to show the decision
        if embed:
            new_embed = embed.copy()
            actor = interaction.user.display_name
            if approved:
                new_embed.color = discord.Color.green()
                new_embed.set_field_at(
                    len(new_embed.fields) - 1 if new_embed.fields else 0,
                    name="Status",
                    value=f"✅ Angenommen von {actor}",
                    inline=False,
                )
            else:
                new_embed.color = discord.Color.red()
                new_embed.set_field_at(
                    len(new_embed.fields) - 1 if new_embed.fields else 0,
                    name="Status",
                    value=f"❌ Abgelehnt von {actor}",
                    inline=False,
                )
            # Remove buttons after decision
            await interaction.message.edit(embed=new_embed, view=discord.ui.View())

        await interaction.followup.send(result_msg, ephemeral=True)


# ── Scoreboard link-request button + modal ───────────────────────────


class ScoreboardLinkModal(discord.ui.Modal):
    """Modal dialog that lets a user submit a link request from the scoreboard."""

    def __init__(self, platform: str) -> None:
        self.platform = platform
        plat_display = PLATFORM_DISPLAY_NAME.get(platform, platform)
        super().__init__(title=f"{plat_display}-Account verknüpfen")
        placeholder = _PLATFORM_PLACEHOLDER.get(platform, "URL, @Handle oder Username")
        self.channel_input = discord.ui.TextInput(
            label=f"{plat_display}-Account (URL oder Username)",
            placeholder=placeholder,
            style=discord.TextStyle.short,
            required=True,
            max_length=200,
        )
        self.add_item(self.channel_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        """Validate input, create DB request, post to admin channel."""
        await interaction.response.defer(ephemeral=True)
        bot: SocialStatsBot = interaction.client  # type: ignore[assignment]
        guild = interaction.guild
        if guild is None:
            return

        plat_key = self.platform
        plat_display = PLATFORM_DISPLAY_NAME.get(plat_key, plat_key)
        user_input = self.channel_input.value.strip()

        # Check request channel is configured
        settings = await bot.db.get_guild_settings(guild.id)
        channel_id = settings.get("request_channel_id", 0)
        if not channel_id:
            await interaction.followup.send(
                "❌ Es wurde noch kein Anfragen-Kanal konfiguriert. "
                "Ein Admin muss `/settings request_channel` setzen.",
                ephemeral=True,
            )
            return
        request_channel = guild.get_channel(channel_id)
        if request_channel is None or not isinstance(request_channel, discord.TextChannel):
            await interaction.followup.send(
                "❌ Der konfigurierte Anfragen-Kanal existiert nicht mehr.",
                ephemeral=True,
            )
            return

        # Resolve the platform account
        try:
            info = await resolve_platform(bot, plat_key, user_input)
        except PlatformRateLimitError:
            await interaction.followup.send(
                f"⏳ {plat_display} ist vorübergehend nicht erreichbar (Rate-Limit). "
                "Bitte versuche es später erneut.",
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

        # Check duplicate
        existing = await bot.db.find_linked_account_by_name(
            guild.id, interaction.user.id, plat_key, platform_name,
        )
        if existing is not None:
            await interaction.followup.send(
                f"❌ **{platform_name}** ({plat_display}) ist bereits mit dir verknüpft.",
                ephemeral=True,
            )
            return

        # Create DB request
        request_id = await bot.db.create_account_request(
            guild_id=guild.id,
            discord_user_id=interaction.user.id,
            request_type="link",
            platform=plat_key,
            platform_id=platform_id,
            platform_name=platform_name,
            follower_count=count,
        )

        # Build embed for admin channel
        emoji = PLATFORM_EMOJI.get(plat_key, "")
        count_label = PLATFORM_COUNT_LABEL.get(plat_key, "Follower")
        embed = discord.Embed(
            title=f"{emoji} Link-Anfrage",
            description=f"{interaction.user.mention} möchte einen {plat_display}-Account verknüpfen.",
            color=PLATFORM_COLOUR_INT.get(plat_key, 0x5865F2),
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="Plattform", value=plat_display, inline=True)
        embed.add_field(name="Account", value=platform_name, inline=True)
        embed.add_field(name=count_label, value=f"{count:,}".replace(",", "."), inline=True)
        embed.add_field(name="Status", value="⏳ Ausstehend", inline=False)
        embed.set_footer(text=f"Anfrage #{request_id}")

        msg = await request_channel.send(embed=embed, view=RequestDecisionView())
        await bot.db.update_request_status(request_id, "pending", message_id=msg.id)

        await interaction.followup.send(
            f"✅ Deine Anfrage für **{platform_name}** ({plat_display}) wurde eingereicht. "
            "Ein Admin wird sie prüfen.",
            ephemeral=True,
        )


def _scoreboard_button_custom_id(platform: str) -> str:
    """Return the stable custom_id for a scoreboard link button."""
    return f"scoreboard_link_{platform}"


class ScoreboardRequestView(discord.ui.View):
    """Persistent view attached to scoreboard messages with a link-request button."""

    def __init__(self, platform: str) -> None:
        super().__init__(timeout=None)
        self.platform = platform
        emoji = PLATFORM_EMOJI.get(platform, "🔗")
        plat_display = PLATFORM_DISPLAY_NAME.get(platform, platform)
        btn = discord.ui.Button(
            label=f"{plat_display}-Account verknüpfen",
            style=discord.ButtonStyle.primary,
            custom_id=_scoreboard_button_custom_id(platform),
            emoji=emoji,
        )
        btn.callback = self._on_click
        self.add_item(btn)

    async def _on_click(self, interaction: discord.Interaction) -> None:
        """Open the link-request modal."""
        await interaction.response.send_modal(ScoreboardLinkModal(self.platform))


# ── Request command group ────────────────────────────────────────────


class RequestCog(commands.GroupCog, group_name="request"):
    """Commands for users to request account linking/unlinking."""

    def __init__(self, bot: SocialStatsBot) -> None:
        self.bot = bot

    # ── Helpers ──────────────────────────────────────────────────────

    async def _get_request_channel(
        self, interaction: discord.Interaction,
    ) -> discord.TextChannel | None:
        """Return the configured request channel, or send an error response."""
        settings = await self.bot.db.get_guild_settings(interaction.guild_id)
        channel_id = settings.get("request_channel_id", 0)
        if not channel_id:
            await interaction.followup.send(
                "❌ Es wurde noch kein Anfragen-Kanal konfiguriert. "
                "Ein Admin muss `/settings request_channel` setzen.",
                ephemeral=True,
            )
            return None
        channel = interaction.guild.get_channel(channel_id)
        if channel is None or not isinstance(channel, discord.TextChannel):
            await interaction.followup.send(
                "❌ Der konfigurierte Anfragen-Kanal existiert nicht mehr.",
                ephemeral=True,
            )
            return None
        return channel

    # ── /request link ────────────────────────────────────────────────

    @app_commands.command(
        name="link",
        description="Stellt eine Anfrage, einen Social-Media-Account zu verknüpfen.",
    )
    @app_commands.describe(
        channel_input="Kanal (URL, @Handle, Login-Name oder ID)",
        platform="Plattform (optional bei URL-Eingabe)",
    )
    @app_commands.choices(platform=PLATFORM_CHOICES)
    async def link(
        self,
        interaction: discord.Interaction,
        channel_input: str,
        platform: app_commands.Choice[str] | None = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        # Resolve platform
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

        # Request channel configured?
        request_channel = await self._get_request_channel(interaction)
        if request_channel is None:
            return

        # Validate: does the channel actually exist on the platform?
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

        # Validate: not already linked for this user
        existing = await self.bot.db.find_linked_account_by_name(
            interaction.guild_id, interaction.user.id, plat_key, platform_name,
        )
        if existing is not None:
            await interaction.followup.send(
                f"❌ **{platform_name}** ({plat_display}) ist bereits mit dir verknüpft.",
                ephemeral=True,
            )
            return

        # Create DB request
        request_id = await self.bot.db.create_account_request(
            guild_id=interaction.guild_id,
            discord_user_id=interaction.user.id,
            request_type="link",
            platform=plat_key,
            platform_id=platform_id,
            platform_name=platform_name,
            follower_count=count,
        )

        # Build embed
        emoji = PLATFORM_EMOJI.get(plat_key, "")
        count_label = PLATFORM_COUNT_LABEL.get(plat_key, "Follower")
        embed = discord.Embed(
            title=f"{emoji} Link-Anfrage",
            description=f"{interaction.user.mention} möchte einen {plat_display}-Account verknüpfen.",
            color=PLATFORM_COLOUR_INT.get(plat_key, 0x5865F2),
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="Plattform", value=plat_display, inline=True)
        embed.add_field(name="Account", value=platform_name, inline=True)
        embed.add_field(name=count_label, value=f"{count:,}".replace(",", "."), inline=True)
        embed.add_field(name="Status", value="⏳ Ausstehend", inline=False)
        embed.set_footer(text=f"Anfrage #{request_id}")

        msg = await request_channel.send(embed=embed, view=RequestDecisionView())
        await self.bot.db.update_request_status(request_id, "pending", message_id=msg.id)

        await interaction.followup.send(
            f"✅ Deine Anfrage für **{platform_name}** ({plat_display}) wurde eingereicht. "
            f"Ein Admin wird sie prüfen.",
            ephemeral=True,
        )

    # ── /request unlink ──────────────────────────────────────────────

    @app_commands.command(
        name="unlink",
        description="Stellt eine Anfrage, einen verknüpften Account zu entfernen.",
    )
    @app_commands.describe(
        platform="Plattform",
        account_name="Name des Accounts (z.B. Niruki)",
    )
    @app_commands.choices(platform=PLATFORM_CHOICES)
    async def unlink(
        self,
        interaction: discord.Interaction,
        platform: app_commands.Choice[str],
        account_name: str,
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        # Request channel configured?
        request_channel = await self._get_request_channel(interaction)
        if request_channel is None:
            return

        # Validate: account must actually be linked for this user
        account = await self.bot.db.find_linked_account_by_name(
            interaction.guild_id, interaction.user.id, platform.value, account_name,
        )
        if account is None:
            await interaction.followup.send(
                f"❌ Kein {platform.name}-Account mit dem Namen **{account_name}** "
                f"für dich gefunden.",
                ephemeral=True,
            )
            return

        platform_name = account["platform_name"]
        platform_id = account["platform_id"]
        count = account.get("current_count", 0)

        # Create DB request
        request_id = await self.bot.db.create_account_request(
            guild_id=interaction.guild_id,
            discord_user_id=interaction.user.id,
            request_type="unlink",
            platform=platform.value,
            platform_id=platform_id,
            platform_name=platform_name,
            follower_count=count,
        )

        # Build embed
        emoji = PLATFORM_EMOJI.get(platform.value, "")
        plat_display = platform.name
        count_label = PLATFORM_COUNT_LABEL.get(platform.value, "Follower")
        embed = discord.Embed(
            title=f"{emoji} Unlink-Anfrage",
            description=f"{interaction.user.mention} möchte einen {plat_display}-Account entfernen.",
            color=PLATFORM_COLOUR_INT.get(platform.value, 0x5865F2),
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="Plattform", value=plat_display, inline=True)
        embed.add_field(name="Account", value=platform_name, inline=True)
        embed.add_field(name=count_label, value=f"{count:,}".replace(",", "."), inline=True)
        embed.add_field(name="Status", value="⏳ Ausstehend", inline=False)
        embed.set_footer(text=f"Anfrage #{request_id}")

        msg = await request_channel.send(embed=embed, view=RequestDecisionView())
        await self.bot.db.update_request_status(request_id, "pending", message_id=msg.id)

        await interaction.followup.send(
            f"✅ Deine Anfrage zum Entfernen von **{platform_name}** ({plat_display}) "
            f"wurde eingereicht. Ein Admin wird sie prüfen.",
            ephemeral=True,
        )

    @unlink.autocomplete("account_name")
    async def _unlink_account_ac(
        self, interaction: discord.Interaction, current: str,
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete for the user's own linked accounts."""
        guild_id = interaction.guild_id
        if not guild_id:
            return []

        platform = getattr(interaction.namespace, "platform", None)
        if not platform:
            return []

        plat = platform.value if hasattr(platform, "value") else str(platform)
        accounts = await self.bot.db.get_linked_accounts_for_user(
            guild_id, interaction.user.id, plat,
        )
        return [
            app_commands.Choice(name=a["platform_name"], value=a["platform_name"])
            for a in accounts
            if a["platform_name"] and current.lower() in a["platform_name"].lower()
        ][:25]

    # ── Error handler ────────────────────────────────────────────────

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError,
    ) -> None:
        log.error("Error in request cog: %s", error, exc_info=error)
        msg = "❌ Ein unerwarteter Fehler ist aufgetreten."
        if not interaction.response.is_done():
            await interaction.response.send_message(msg, ephemeral=True)
        else:
            await interaction.followup.send(msg, ephemeral=True)


async def setup(bot: SocialStatsBot) -> None:
    # Register persistent views so buttons work after restart
    bot.add_view(RequestDecisionView())
    for platform in ("youtube", "twitch", "instagram", "tiktok"):
        bot.add_view(ScoreboardRequestView(platform))
    await bot.add_cog(RequestCog(bot))
