"""Status monitoring – health tracking and status embed builder.

Provides :class:`PlatformHealth` for tracking per-platform refresh results
and :func:`build_status_embed` for creating the admin status embed.
"""

from __future__ import annotations

import datetime
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

import discord

from bot.cogs import PLATFORM_COUNT_LABEL, PLATFORM_DISPLAY_NAME, PLATFORM_EMOJI
from bot.database import ALL_PLATFORMS
from bot.roles import PLATFORM_SETTINGS_PREFIX, format_count

if TYPE_CHECKING:
    from bot.bot import SocialStatsBot


@dataclass
class PlatformHealth:
    """Snapshot of the last refresh cycle for one platform in a guild."""

    last_refresh_start: float = 0.0
    last_refresh_end: float = 0.0
    accounts_total: int = 0
    accounts_ok: int = 0
    accounts_error: int = 0
    accounts_skipped: int = 0
    rate_limited: bool = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _format_interval(seconds: int) -> str:
    """Format an interval in seconds into a human-readable German string."""
    if seconds >= 3600 and seconds % 3600 == 0:
        h = seconds // 3600
        return f"{h} Stunde" if h == 1 else f"{h} Stunden"
    if seconds >= 60 and seconds % 60 == 0:
        m = seconds // 60
        return f"{m} Minute" if m == 1 else f"{m} Minuten"
    return f"{seconds} Sekunde" if seconds == 1 else f"{seconds} Sekunden"


def _status_indicator(
    health: PlatformHealth | None,
    service_health: dict,
    n_accounts: int,
) -> tuple[str, str]:
    """Return ``(emoji, label)`` for the platform's health status."""
    if n_accounts == 0:
        return "⚪", "Keine Accounts"
    if health is None:
        return "⏳", "Ausstehend"

    if service_health.get("global_cooldown_active"):
        return "🔴", "Rate-Limited (429)"

    if health.rate_limited:
        return "🔴", "Rate-Limited"

    if health.accounts_error > 0 and health.accounts_ok == 0:
        return "🔴", "Gestört"

    if health.accounts_error > 0:
        return "🟡", "Teilweise gestört"

    return "🟢", "Online"


def _fmt_remaining(seconds: float) -> str:
    """Format remaining seconds as ``m:ss``."""
    m, s = divmod(max(0, int(seconds)), 60)
    return f"{m}:{s:02d}"


def _get_service(bot: SocialStatsBot, platform: str):
    """Return the service instance for *platform*."""
    return {
        "youtube": bot.youtube,
        "twitch": bot.twitch,
        "instagram": bot.instagram,
        "tiktok": bot.tiktok,
    }.get(platform)


# ---------------------------------------------------------------------------
# Embed builder
# ---------------------------------------------------------------------------


async def build_status_embed(
    bot: SocialStatsBot,
    guild: discord.Guild,
) -> discord.Embed:
    """Build a comprehensive status embed for *guild*."""
    settings = await bot.db.get_guild_settings(guild.id)

    all_ok = True
    any_error = False
    sections: list[str] = []

    for platform in ALL_PLATFORMS:
        prefix = PLATFORM_SETTINGS_PREFIX[platform]
        emoji = PLATFORM_EMOJI[platform]
        display = PLATFORM_DISPLAY_NAME[platform]
        count_label = PLATFORM_COUNT_LABEL[platform]
        interval = settings.get(f"{prefix}_refresh_interval", 600)

        # Guild-level health (from last refresh cycle)
        guild_health = bot.platform_health.get(guild.id, {})
        health: PlatformHealth | None = guild_health.get(platform)

        # Service-level health
        service = _get_service(bot, platform)
        svc_health: dict = {}
        if service and hasattr(service, "get_health"):
            svc_health = service.get_health()

        # Account data from DB
        accounts = await bot.db.get_all_linked(guild.id, platform)
        total_count = sum(a["current_count"] for a in accounts)
        n_accounts = len(accounts)
        error_accounts = [
            a for a in accounts
            if a.get("last_status") not in ("ok", "pending")
        ]

        # Status indicator
        s_emoji, s_label = _status_indicator(health, svc_health, n_accounts)
        if s_emoji == "🔴":
            any_error = True
            all_ok = False
        elif s_emoji in ("🟡", "⏳"):
            all_ok = False

        # Build section
        acct_word = "Account" if n_accounts == 1 else "Accounts"
        lines = [f"**{emoji} {display}** ({n_accounts} {acct_word})"]
        lines.append(f"├ Status: {s_emoji} {s_label}")

        # Platform-specific details
        if platform == "instagram":
            backend = svc_health.get("backend", "unbekannt")
            lines.append(f"├ Backend: `{backend}`")
            if svc_health.get("global_cooldown_active"):
                remaining = svc_health.get("global_cooldown_remaining", 0)
                lines.append(f"├ ⚠️ IP-Cooldown: noch {_fmt_remaining(remaining)}")
            cd_count = svc_health.get("per_user_cooldown_count", 0)
            if cd_count > 0:
                lines.append(f"├ Account-Cooldowns: {cd_count}")

        if platform == "twitch" and bot.eventsub:
            lines.append("├ EventSub: ✅ Aktiv")

        # Error accounts detail (max 5)
        if error_accounts:
            lines.append(f"├ ⚠️ Fehlerhafte Accounts ({len(error_accounts)}):")
            for ea in error_accounts[:5]:
                name = ea.get("platform_name") or ea.get("platform_id", "?")
                status = ea.get("last_status", "error")
                status_label = {
                    "error": "API-Fehler",
                    "rate_limited": "Rate-Limited",
                }.get(status, status)
                lines.append(f"│  └ ❌ {name} – {status_label}")
            if len(error_accounts) > 5:
                lines.append(f"│  └ … und {len(error_accounts) - 5} weitere")

        # Refresh stats
        if health and health.last_refresh_end > 0:
            last_ts = int(health.last_refresh_end)
            next_ts = last_ts + interval
            lines.append(f"├ Letzter Refresh: <t:{last_ts}:R>")
            lines.append(f"├ Nächster Refresh: <t:{next_ts}:R>")
            if health.accounts_total > 0:
                parts: list[str] = [f"✅ {health.accounts_ok}"]
                if health.accounts_error > 0:
                    parts.append(f"❌ {health.accounts_error}")
                if health.accounts_skipped > 0:
                    parts.append(f"⏭️ {health.accounts_skipped}")
                lines.append(
                    f"├ Abfragen: {' / '.join(parts)} (von {health.accounts_total})"
                )
        elif n_accounts > 0:
            lines.append("├ Refresh: ⏳ Ausstehend")

        lines.append(f"├ Intervall: {_format_interval(interval)}")
        lines.append(f"└ Gesamt: **{format_count(total_count)}** {count_label}")

        sections.append("\n".join(lines))

    # Overall embed colour
    if any_error:
        colour = discord.Colour.red()
        title = "🔴 Bot-Status"
    elif not all_ok:
        colour = discord.Colour.gold()
        title = "🟡 Bot-Status"
    else:
        colour = discord.Colour.green()
        title = "🟢 Bot-Status"

    now_ts = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
    status_interval = settings.get("status_refresh_interval", 30)
    next_status_ts = now_ts + status_interval

    description = "\n\n".join(sections)
    description += (
        "\n\n─────────────────────────\n"
        f"🕐 Aktualisiert: <t:{now_ts}:f>\n"
        f"⏭️ Nächstes Update: <t:{next_status_ts}:R> ({_format_interval(status_interval)})"
    )

    embed = discord.Embed(title=title, colour=colour, description=description)

    # Set bot avatar as thumbnail if available
    if bot.user and bot.user.display_avatar:
        embed.set_thumbnail(url=bot.user.display_avatar.url)

    return embed
