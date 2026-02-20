"""
Settings cog – guild-specific configuration commands.

All commands restricted to server administrators via Discord's
built-in permission system (default_permissions).
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot.bot import SocialStatsBot

log = logging.getLogger(__name__)


class SettingsCog(commands.GroupCog, group_name="settings"):
    """Commands to configure bot settings per guild."""

    def __init__(self, bot: SocialStatsBot) -> None:
        self.bot = bot

    # ── Autocomplete helpers ─────────────────────────────────────────

    async def _design_id_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[int]]:
        """Autocomplete for design_id – shows all role designs in this guild."""
        guild_id = interaction.guild_id
        if not guild_id:
            return []

        choices: list[app_commands.Choice[int]] = []
        for plat in ("youtube", "twitch"):
            designs = await self.bot.db.get_role_designs(guild_id, plat)
            for d in designs:
                if d["exact_count"] is not None:
                    scope = f"Exakt {d['exact_count']}"
                elif d["range_max"]:
                    scope = f"{d['range_min']}–{d['range_max']}"
                else:
                    scope = f"Ab {d['range_min']}"
                label = f"#{d['id']} {plat.title()} | {scope} | {d['role_pattern']}"
                if current and current not in str(d["id"]) and current.lower() not in label.lower():
                    continue
                choices.append(app_commands.Choice(name=label[:100], value=d["id"]))
        return choices[:25]

    # ── /settings show ───────────────────────────────────────────────

    @app_commands.command(name="show", description="Zeigt die aktuellen Einstellungen.")
    async def show(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        s = await self.bot.db.get_guild_settings(interaction.guild_id)

        def ch(cid: int) -> str:
            return f"<#{cid}>" if cid else "Nicht gesetzt"

        lines = [
            "**⚙️ Aktuelle Einstellungen:**\n",
            f"📺 **YouTube Scoreboard-Kanal:** {ch(s['yt_scoreboard_channel_id'])}",
            f"📺 **YouTube Scoreboard-Größe:** {s['yt_scoreboard_size']}",
            f"📺 **YouTube Refresh-Intervall:** {s['yt_refresh_interval']}s",
            f"📺 **YouTube Rollen-Pattern:** `{s['yt_default_role_pattern']}`",
            f"📺 **YouTube Rollen-Farbe:** #{s['yt_default_role_color']:06X}",
            "",
            f"🎮 **Twitch Scoreboard-Kanal:** {ch(s['tw_scoreboard_channel_id'])}",
            f"🎮 **Twitch Scoreboard-Größe:** {s['tw_scoreboard_size']}",
            f"🎮 **Twitch Refresh-Intervall:** {s['tw_refresh_interval']}s",
            f"🎮 **Twitch Rollen-Pattern:** `{s['tw_default_role_pattern']}`",
            f"🎮 **Twitch Rollen-Farbe:** #{s['tw_default_role_color']:06X}",
        ]
        await interaction.followup.send("\n".join(lines), ephemeral=True)

    # ── /settings scoreboard_channel ─────────────────────────────────

    @app_commands.command(
        name="scoreboard_channel",
        description="Setzt den Scoreboard-Kanal für eine Plattform.",
    )
    @app_commands.describe(platform="Plattform", channel="Text-Kanal")
    @app_commands.choices(
        platform=[
            app_commands.Choice(name="YouTube", value="youtube"),
            app_commands.Choice(name="Twitch", value="twitch"),
        ]
    )
    async def scoreboard_channel(
        self,
        interaction: discord.Interaction,
        platform: app_commands.Choice[str],
        channel: discord.TextChannel,
    ) -> None:
        key = "yt_scoreboard_channel_id" if platform.value == "youtube" else "tw_scoreboard_channel_id"
        await self.bot.db.update_guild_setting(interaction.guild_id, key, channel.id)
        await interaction.response.send_message(
            f"✅ {platform.name} Scoreboard-Kanal auf {channel.mention} gesetzt.",
            ephemeral=True,
        )

    # ── /settings scoreboard_size ────────────────────────────────────

    @app_commands.command(
        name="scoreboard_size",
        description="Setzt die maximale Anzahl an Einträgen im Scoreboard.",
    )
    @app_commands.describe(platform="Plattform", size="Anzahl (1–50)")
    @app_commands.choices(
        platform=[
            app_commands.Choice(name="YouTube", value="youtube"),
            app_commands.Choice(name="Twitch", value="twitch"),
        ]
    )
    async def scoreboard_size(
        self,
        interaction: discord.Interaction,
        platform: app_commands.Choice[str],
        size: app_commands.Range[int, 1, 50],
    ) -> None:
        key = "yt_scoreboard_size" if platform.value == "youtube" else "tw_scoreboard_size"
        await self.bot.db.update_guild_setting(interaction.guild_id, key, size)
        await interaction.response.send_message(
            f"✅ {platform.name} Scoreboard-Größe auf **{size}** gesetzt.",
            ephemeral=True,
        )

    # ── /settings refresh_interval ───────────────────────────────────

    @app_commands.command(
        name="refresh_interval",
        description="Setzt das Aktualisierungs-Intervall (in Sekunden).",
    )
    @app_commands.describe(platform="Plattform", seconds="Intervall in Sekunden (min. 60)")
    @app_commands.choices(
        platform=[
            app_commands.Choice(name="YouTube", value="youtube"),
            app_commands.Choice(name="Twitch", value="twitch"),
        ]
    )
    async def refresh_interval(
        self,
        interaction: discord.Interaction,
        platform: app_commands.Choice[str],
        seconds: app_commands.Range[int, 60, 86400],
    ) -> None:
        key = "yt_refresh_interval" if platform.value == "youtube" else "tw_refresh_interval"
        await self.bot.db.update_guild_setting(interaction.guild_id, key, seconds)
        await interaction.response.send_message(
            f"✅ {platform.name} Refresh-Intervall auf **{seconds}s** gesetzt.",
            ephemeral=True,
        )

    # ── /settings role_pattern ───────────────────────────────────────

    @app_commands.command(
        name="role_pattern",
        description="Setzt das Standard-Rollen-Pattern. Platzhalter: {name}, {count}",
    )
    @app_commands.describe(
        platform="Plattform",
        pattern="Pattern mit {name} und {count} (z.B. '{name} - {count} Abos')",
    )
    @app_commands.choices(
        platform=[
            app_commands.Choice(name="YouTube", value="youtube"),
            app_commands.Choice(name="Twitch", value="twitch"),
        ]
    )
    async def role_pattern(
        self,
        interaction: discord.Interaction,
        platform: app_commands.Choice[str],
        pattern: str,
    ) -> None:
        if "{count}" not in pattern:
            await interaction.response.send_message(
                "❌ Pattern muss `{count}` enthalten.", ephemeral=True
            )
            return
        key = "yt_default_role_pattern" if platform.value == "youtube" else "tw_default_role_pattern"
        await self.bot.db.update_guild_setting(interaction.guild_id, key, pattern)
        await interaction.response.send_message(
            f"✅ {platform.name} Rollen-Pattern auf `{pattern}` gesetzt.",
            ephemeral=True,
        )

    # ── /settings role_color ─────────────────────────────────────────

    @app_commands.command(
        name="role_color",
        description="Setzt die Standard-Rollenfarbe (Hex, z.B. FF0000).",
    )
    @app_commands.describe(platform="Plattform", hex_color="Farbe als Hex (z.B. FF0000)")
    @app_commands.choices(
        platform=[
            app_commands.Choice(name="YouTube", value="youtube"),
            app_commands.Choice(name="Twitch", value="twitch"),
        ]
    )
    async def role_color(
        self,
        interaction: discord.Interaction,
        platform: app_commands.Choice[str],
        hex_color: str,
    ) -> None:
        try:
            color_int = int(hex_color.strip("#"), 16)
        except ValueError:
            await interaction.response.send_message(
                "❌ Ungültiger Hex-Farbwert.", ephemeral=True
            )
            return

        key = "yt_default_role_color" if platform.value == "youtube" else "tw_default_role_color"
        await self.bot.db.update_guild_setting(interaction.guild_id, key, color_int)
        await interaction.response.send_message(
            f"✅ {platform.name} Rollenfarbe auf `#{color_int:06X}` gesetzt.",
            ephemeral=True,
        )

    # ── /settings role_design ────────────────────────────────────────

    @app_commands.command(
        name="role_design",
        description="Erstellt ein benutzerdefiniertes Rollen-Design für einen Bereich.",
    )
    @app_commands.describe(
        platform="Plattform",
        range_min="Ab-Wert (z.B. 1000)",
        range_max="Bis-Wert (leer = unbegrenzt)",
        pattern="Rollen-Pattern mit {name} und {count}",
        hex_color="Farbe als Hex",
    )
    @app_commands.choices(
        platform=[
            app_commands.Choice(name="YouTube", value="youtube"),
            app_commands.Choice(name="Twitch", value="twitch"),
        ]
    )
    async def role_design(
        self,
        interaction: discord.Interaction,
        platform: app_commands.Choice[str],
        range_min: int,
        pattern: str,
        hex_color: str,
        range_max: int = None,
    ) -> None:
        try:
            color = int(hex_color.strip("#"), 16)
        except ValueError:
            await interaction.response.send_message("❌ Ungültiger Hex-Farbwert.", ephemeral=True)
            return

        await self.bot.db.set_role_design(
            interaction.guild_id,
            platform.value,
            pattern,
            color,
            range_min=range_min,
            range_max=range_max,
        )
        range_str = f"{range_min}–{range_max}" if range_max else f"ab {range_min}"
        await interaction.response.send_message(
            f"✅ {platform.name} Role-Design für **{range_str}** gespeichert.\n"
            f"Pattern: `{pattern}`, Farbe: `#{color:06X}`",
            ephemeral=True,
        )

    # ── /settings role_design_exact ──────────────────────────────────

    @app_commands.command(
        name="role_design_exact",
        description="Erstellt ein Rollen-Design für eine exakte Zahl.",
    )
    @app_commands.describe(
        platform="Plattform",
        exact_count="Exakter Wert",
        pattern="Rollen-Pattern mit {name} und {count}",
        hex_color="Farbe als Hex",
    )
    @app_commands.choices(
        platform=[
            app_commands.Choice(name="YouTube", value="youtube"),
            app_commands.Choice(name="Twitch", value="twitch"),
        ]
    )
    async def role_design_exact(
        self,
        interaction: discord.Interaction,
        platform: app_commands.Choice[str],
        exact_count: int,
        pattern: str,
        hex_color: str,
    ) -> None:
        try:
            color = int(hex_color.strip("#"), 16)
        except ValueError:
            await interaction.response.send_message("❌ Ungültiger Hex-Farbwert.", ephemeral=True)
            return

        await self.bot.db.set_role_design(
            interaction.guild_id,
            platform.value,
            pattern,
            color,
            exact_count=exact_count,
        )
        await interaction.response.send_message(
            f"✅ {platform.name} Role-Design für exakt **{exact_count}** gespeichert.\n"
            f"Pattern: `{pattern}`, Farbe: `#{color:06X}`",
            ephemeral=True,
        )

    # ── /settings list_role_designs ──────────────────────────────────

    @app_commands.command(
        name="list_role_designs",
        description="Zeigt alle benutzerdefinierten Rollen-Designs.",
    )
    @app_commands.describe(platform="Plattform")
    @app_commands.choices(
        platform=[
            app_commands.Choice(name="YouTube", value="youtube"),
            app_commands.Choice(name="Twitch", value="twitch"),
        ]
    )
    async def list_role_designs(
        self,
        interaction: discord.Interaction,
        platform: app_commands.Choice[str],
    ) -> None:
        designs = await self.bot.db.get_role_designs(interaction.guild_id, platform.value)
        if not designs:
            await interaction.response.send_message(
                f"Keine benutzerdefinierten Rollen-Designs für {platform.name}.",
                ephemeral=True,
            )
            return

        lines = [f"**🎨 {platform.name} Rollen-Designs:**\n"]
        for d in designs:
            if d["exact_count"] is not None:
                scope = f"Exakt {d['exact_count']}"
            elif d["range_max"]:
                scope = f"{d['range_min']}–{d['range_max']}"
            else:
                scope = f"Ab {d['range_min']}"
            lines.append(
                f"  **ID {d['id']}** | {scope} | `{d['role_pattern']}` | #{d['role_color']:06X}"
            )

        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    # ── /settings remove_role_design ─────────────────────────────────

    @app_commands.command(
        name="remove_role_design",
        description="Entfernt ein Rollen-Design anhand seiner ID.",
    )
    @app_commands.describe(design_id="ID des Rollen-Designs")
    async def remove_role_design(
        self,
        interaction: discord.Interaction,
        design_id: int,
    ) -> None:
        removed = await self.bot.db.remove_role_design(design_id)
        if removed:
            await interaction.response.send_message(
                f"✅ Rollen-Design **#{design_id}** entfernt.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"❌ Kein Rollen-Design mit ID **{design_id}** gefunden.", ephemeral=True
            )

    @remove_role_design.autocomplete("design_id")
    async def _remove_design_ac(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[int]]:
        return await self._design_id_autocomplete(interaction, current)

    # ── Error handler ────────────────────────────────────────────────

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        if isinstance(error, (app_commands.MissingPermissions, app_commands.CheckFailure)):
            msg = "❌ Du hast keine Berechtigung für diesen Befehl."
        else:
            log.error("Error in settings cog: %s", error, exc_info=error)
            msg = "❌ Ein unerwarteter Fehler ist aufgetreten."

        if not interaction.response.is_done():
            await interaction.response.send_message(msg, ephemeral=True)
        else:
            await interaction.followup.send(msg, ephemeral=True)


async def setup(bot: SocialStatsBot) -> None:
    await bot.add_cog(SettingsCog(bot))
