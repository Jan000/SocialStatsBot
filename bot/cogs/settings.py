"""
Settings cog – all guild settings editable via slash commands.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from bot.bot import SocialStatsBot


def admin_only():
    async def predicate(interaction: discord.Interaction) -> bool:
        bot: SocialStatsBot = interaction.client  # type: ignore
        if not bot.is_admin(interaction.user.id):
            await interaction.response.send_message(
                "❌ Nur der Bot-Admin darf diesen Befehl verwenden.", ephemeral=True
            )
            return False
        return True
    return app_commands.check(predicate)


# ── Helper to parse hex color strings ────────────────────────────────

def parse_color(value: str) -> int:
    """Parse a hex color string like '#FF0000' or 'FF0000' to int."""
    value = value.strip().lstrip("#")
    return int(value, 16)


class SettingsCog(commands.Cog, name="Settings"):
    """Befehle zum Konfigurieren des Bots (nur Admin)."""

    def __init__(self, bot: SocialStatsBot) -> None:
        self.bot = bot

    # ── Show all settings ────────────────────────────────────────────

    @app_commands.command(name="show_settings", description="Zeige alle aktuellen Bot-Einstellungen für diesen Server.")
    @admin_only()
    async def show_settings(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        s = await self.bot.db.get_guild_settings(interaction.guild.id)

        def ch(cid: int) -> str:
            return f"<#{cid}>" if cid else "Nicht gesetzt"

        embed = discord.Embed(title="⚙️ Server-Einstellungen", color=0x2F3136)
        embed.add_field(
            name="YouTube",
            value=(
                f"Scoreboard-Channel: {ch(s['yt_scoreboard_channel_id'])}\n"
                f"Scoreboard-Größe: {s['yt_scoreboard_size']}\n"
                f"Refresh-Intervall: {s['yt_refresh_interval']}s\n"
                f"Rollen-Pattern: `{s['yt_default_role_pattern']}`\n"
                f"Rollen-Farbe: `#{s['yt_default_role_color']:06X}`"
            ),
            inline=False,
        )
        embed.add_field(
            name="Twitch",
            value=(
                f"Scoreboard-Channel: {ch(s['tw_scoreboard_channel_id'])}\n"
                f"Scoreboard-Größe: {s['tw_scoreboard_size']}\n"
                f"Refresh-Intervall: {s['tw_refresh_interval']}s\n"
                f"Rollen-Pattern: `{s['tw_default_role_pattern']}`\n"
                f"Rollen-Farbe: `#{s['tw_default_role_color']:06X}`"
            ),
            inline=False,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── Set scoreboard channel ───────────────────────────────────────

    @app_commands.command(name="set_scoreboard_channel", description="Setze den Scoreboard-Channel.")
    @app_commands.describe(
        platform="youtube oder twitch",
        channel="Der Text-Channel für das Scoreboard",
    )
    @app_commands.choices(platform=[
        app_commands.Choice(name="YouTube", value="youtube"),
        app_commands.Choice(name="Twitch", value="twitch"),
    ])
    @admin_only()
    async def set_scoreboard_channel(
        self,
        interaction: discord.Interaction,
        platform: app_commands.Choice[str],
        channel: discord.TextChannel,
    ) -> None:
        key = "yt_scoreboard_channel_id" if platform.value == "youtube" else "tw_scoreboard_channel_id"
        await self.bot.db.update_guild_setting(interaction.guild.id, key, channel.id)
        await interaction.response.send_message(
            f"✅ {platform.name}-Scoreboard-Channel auf {channel.mention} gesetzt.",
            ephemeral=True,
        )

    # ── Set scoreboard size ──────────────────────────────────────────

    @app_commands.command(name="set_scoreboard_size", description="Setze die Anzahl der User im Scoreboard.")
    @app_commands.describe(
        platform="youtube oder twitch",
        size="Anzahl der angezeigten User (1-50)",
    )
    @app_commands.choices(platform=[
        app_commands.Choice(name="YouTube", value="youtube"),
        app_commands.Choice(name="Twitch", value="twitch"),
    ])
    @admin_only()
    async def set_scoreboard_size(
        self,
        interaction: discord.Interaction,
        platform: app_commands.Choice[str],
        size: app_commands.Range[int, 1, 50],
    ) -> None:
        key = "yt_scoreboard_size" if platform.value == "youtube" else "tw_scoreboard_size"
        await self.bot.db.update_guild_setting(interaction.guild.id, key, size)
        await interaction.response.send_message(
            f"✅ {platform.name}-Scoreboard zeigt jetzt **{size}** User.",
            ephemeral=True,
        )

    # ── Set refresh interval ─────────────────────────────────────────

    @app_commands.command(name="set_refresh_interval", description="Setze das Refresh-Intervall in Sekunden.")
    @app_commands.describe(
        platform="youtube oder twitch",
        seconds="Intervall in Sekunden (min. 60)",
    )
    @app_commands.choices(platform=[
        app_commands.Choice(name="YouTube", value="youtube"),
        app_commands.Choice(name="Twitch", value="twitch"),
    ])
    @admin_only()
    async def set_refresh_interval(
        self,
        interaction: discord.Interaction,
        platform: app_commands.Choice[str],
        seconds: app_commands.Range[int, 60, 86400],
    ) -> None:
        key = "yt_refresh_interval" if platform.value == "youtube" else "tw_refresh_interval"
        await self.bot.db.update_guild_setting(interaction.guild.id, key, seconds)
        await interaction.response.send_message(
            f"✅ {platform.name}-Refresh-Intervall auf **{seconds}s** gesetzt.",
            ephemeral=True,
        )

    # ── Set default role pattern ─────────────────────────────────────

    @app_commands.command(name="set_role_pattern", description="Setze das Standard-Rollen-Pattern (nutze {count} als Platzhalter).")
    @app_commands.describe(
        platform="youtube oder twitch",
        pattern="z.B. '{count} YouTube Abos'",
    )
    @app_commands.choices(platform=[
        app_commands.Choice(name="YouTube", value="youtube"),
        app_commands.Choice(name="Twitch", value="twitch"),
    ])
    @admin_only()
    async def set_role_pattern(
        self,
        interaction: discord.Interaction,
        platform: app_commands.Choice[str],
        pattern: str,
    ) -> None:
        key = "yt_default_role_pattern" if platform.value == "youtube" else "tw_default_role_pattern"
        await self.bot.db.update_guild_setting(interaction.guild.id, key, pattern)
        await interaction.response.send_message(
            f"✅ Standard-Rollen-Pattern für {platform.name}: `{pattern}`",
            ephemeral=True,
        )

    # ── Set default role color ───────────────────────────────────────

    @app_commands.command(name="set_role_color", description="Setze die Standard-Rollen-Farbe (Hex, z.B. #FF0000).")
    @app_commands.describe(
        platform="youtube oder twitch",
        color="Hex-Farbcode, z.B. #FF0000",
    )
    @app_commands.choices(platform=[
        app_commands.Choice(name="YouTube", value="youtube"),
        app_commands.Choice(name="Twitch", value="twitch"),
    ])
    @admin_only()
    async def set_role_color(
        self,
        interaction: discord.Interaction,
        platform: app_commands.Choice[str],
        color: str,
    ) -> None:
        try:
            color_int = parse_color(color)
        except ValueError:
            await interaction.response.send_message(
                "❌ Ungültiger Hex-Farbcode. Beispiel: `#FF0000`", ephemeral=True
            )
            return
        key = "yt_default_role_color" if platform.value == "youtube" else "tw_default_role_color"
        await self.bot.db.update_guild_setting(interaction.guild.id, key, color_int)
        await interaction.response.send_message(
            f"✅ Standard-Rollen-Farbe für {platform.name}: `#{color_int:06X}`",
            ephemeral=True,
        )

    # ── Role design (custom per range / exact count) ─────────────────

    @app_commands.command(
        name="add_role_design",
        description="Füge ein benutzerdefiniertes Rollen-Design für einen Abo-Bereich hinzu.",
    )
    @app_commands.describe(
        platform="youtube oder twitch",
        range_min="Untere Grenze des Bereichs",
        range_max="Obere Grenze des Bereichs (leer = unbegrenzt)",
        exact_count="Exakter Wert (überschreibt Bereich)",
        pattern="Rollen-Name-Pattern ({count} = Platzhalter)",
        color="Hex-Farbcode, z.B. #FF0000",
    )
    @app_commands.choices(platform=[
        app_commands.Choice(name="YouTube", value="youtube"),
        app_commands.Choice(name="Twitch", value="twitch"),
    ])
    @admin_only()
    async def add_role_design(
        self,
        interaction: discord.Interaction,
        platform: app_commands.Choice[str],
        pattern: str,
        color: str,
        range_min: int = 0,
        range_max: int | None = None,
        exact_count: int | None = None,
    ) -> None:
        try:
            color_int = parse_color(color)
        except ValueError:
            await interaction.response.send_message(
                "❌ Ungültiger Hex-Farbcode.", ephemeral=True
            )
            return

        await self.bot.db.set_role_design(
            guild_id=interaction.guild.id,
            platform=platform.value,
            role_pattern=pattern,
            role_color=color_int,
            range_min=range_min,
            range_max=range_max,
            exact_count=exact_count,
        )

        if exact_count is not None:
            desc = f"exakt **{exact_count:,}**"
        elif range_max is not None:
            desc = f"**{range_min:,}** – **{range_max:,}**"
        else:
            desc = f"**{range_min:,}+**"

        await interaction.response.send_message(
            f"✅ Rollen-Design für {platform.name} ({desc}): `{pattern}` / `#{color_int:06X}`",
            ephemeral=True,
        )

    @app_commands.command(
        name="list_role_designs",
        description="Zeige alle benutzerdefinierten Rollen-Designs.",
    )
    @app_commands.describe(platform="youtube oder twitch")
    @app_commands.choices(platform=[
        app_commands.Choice(name="YouTube", value="youtube"),
        app_commands.Choice(name="Twitch", value="twitch"),
    ])
    @admin_only()
    async def list_role_designs(
        self,
        interaction: discord.Interaction,
        platform: app_commands.Choice[str],
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        designs = await self.bot.db.get_role_designs(interaction.guild.id, platform.value)
        if not designs:
            await interaction.followup.send(
                f"Keine benutzerdefinierten Rollen-Designs für {platform.name}.", ephemeral=True
            )
            return

        lines: list[str] = []
        for d in designs:
            if d["exact_count"] is not None:
                scope = f"exakt {d['exact_count']:,}"
            elif d["range_max"] is not None:
                scope = f"{d['range_min']:,} – {d['range_max']:,}"
            else:
                scope = f"{d['range_min']:,}+"
            lines.append(
                f"**ID {d['id']}** | {scope} | `{d['role_pattern']}` | `#{d['role_color']:06X}`"
            )

        embed = discord.Embed(
            title=f"Rollen-Designs – {platform.name}",
            description="\n".join(lines),
            color=0xFF0000 if platform.value == "youtube" else 0x6441A4,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(
        name="remove_role_design",
        description="Entferne ein benutzerdefiniertes Rollen-Design anhand seiner ID.",
    )
    @app_commands.describe(design_id="Die ID des Designs (siehe /list_role_designs)")
    @admin_only()
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
                f"❌ Design mit ID {design_id} nicht gefunden.", ephemeral=True
            )


async def setup(bot: SocialStatsBot) -> None:
    await bot.add_cog(SettingsCog(bot))
