"""
Database module – SQLite via aiosqlite.

All tables:
  - guild_settings: per-guild configurable settings
  - linked_accounts: discord_user -> youtube/twitch mapping
  - sub_history: timestamped subscriber/follower snapshots
  - role_designs: custom role name/colour patterns per range
  - refresh_status: tracks last refresh time & result per account
"""

from __future__ import annotations

import aiosqlite
import time
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "bot.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS guild_settings (
    guild_id          INTEGER PRIMARY KEY,
    yt_scoreboard_channel_id   INTEGER DEFAULT 0,
    tw_scoreboard_channel_id   INTEGER DEFAULT 0,
    yt_scoreboard_size         INTEGER DEFAULT 10,
    tw_scoreboard_size         INTEGER DEFAULT 10,
    yt_refresh_interval        INTEGER DEFAULT 600,
    tw_refresh_interval        INTEGER DEFAULT 600,
    yt_default_role_pattern    TEXT    DEFAULT '{count} YouTube Abos',
    tw_default_role_pattern    TEXT    DEFAULT '{count} Twitch Follower',
    yt_default_role_color      INTEGER DEFAULT 16711680,
    tw_default_role_color      INTEGER DEFAULT 6570404
);

CREATE TABLE IF NOT EXISTS linked_accounts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id        INTEGER NOT NULL,
    discord_user_id INTEGER NOT NULL,
    platform        TEXT    NOT NULL CHECK(platform IN ('youtube', 'twitch')),
    platform_id     TEXT    NOT NULL,
    platform_name   TEXT    DEFAULT '',
    current_count   INTEGER DEFAULT 0,
    last_refreshed  REAL    DEFAULT 0,
    last_status     TEXT    DEFAULT 'pending',
    UNIQUE(guild_id, discord_user_id, platform)
);

CREATE TABLE IF NOT EXISTS sub_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id        INTEGER NOT NULL,
    discord_user_id INTEGER NOT NULL,
    platform        TEXT    NOT NULL,
    count           INTEGER NOT NULL,
    recorded_at     REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS role_designs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id        INTEGER NOT NULL,
    platform        TEXT    NOT NULL CHECK(platform IN ('youtube', 'twitch')),
    range_min       INTEGER NOT NULL,
    range_max       INTEGER,
    exact_count     INTEGER,
    role_pattern    TEXT    NOT NULL DEFAULT '{count} Abos',
    role_color      INTEGER NOT NULL DEFAULT 0,
    UNIQUE(guild_id, platform, range_min, range_max, exact_count)
);

CREATE TABLE IF NOT EXISTS scoreboard_messages (
    guild_id        INTEGER NOT NULL,
    platform        TEXT    NOT NULL CHECK(platform IN ('youtube', 'twitch')),
    channel_id      INTEGER NOT NULL,
    message_id      INTEGER NOT NULL,
    PRIMARY KEY (guild_id, platform)
);

CREATE INDEX IF NOT EXISTS idx_linked_guild ON linked_accounts(guild_id);
CREATE INDEX IF NOT EXISTS idx_history_guild ON sub_history(guild_id, platform);
"""


class Database:
    """Async wrapper around the SQLite database."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path or DB_PATH
        self._db: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(str(self.path))
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(_SCHEMA)
        await self._db.commit()

    async def close(self) -> None:
        if self._db:
            await self._db.close()

    @property
    def db(self) -> aiosqlite.Connection:
        assert self._db is not None, "Database not connected"
        return self._db

    # ── Guild settings ───────────────────────────────────────────────

    async def get_guild_settings(self, guild_id: int) -> dict:
        """Return guild settings, creating defaults if missing."""
        async with self.db.execute(
            "SELECT * FROM guild_settings WHERE guild_id = ?", (guild_id,)
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            await self.db.execute(
                "INSERT INTO guild_settings (guild_id) VALUES (?)", (guild_id,)
            )
            await self.db.commit()
            return await self.get_guild_settings(guild_id)
        return dict(row)

    async def update_guild_setting(self, guild_id: int, key: str, value) -> None:
        allowed = {
            "yt_scoreboard_channel_id",
            "tw_scoreboard_channel_id",
            "yt_scoreboard_size",
            "tw_scoreboard_size",
            "yt_refresh_interval",
            "tw_refresh_interval",
            "yt_default_role_pattern",
            "tw_default_role_pattern",
            "yt_default_role_color",
            "tw_default_role_color",
        }
        if key not in allowed:
            raise ValueError(f"Unknown setting: {key}")
        await self.get_guild_settings(guild_id)  # ensure row exists
        await self.db.execute(
            f"UPDATE guild_settings SET {key} = ? WHERE guild_id = ?",
            (value, guild_id),
        )
        await self.db.commit()

    # ── Linked accounts ──────────────────────────────────────────────

    async def link_account(
        self,
        guild_id: int,
        discord_user_id: int,
        platform: str,
        platform_id: str,
        platform_name: str = "",
    ) -> None:
        await self.db.execute(
            """INSERT INTO linked_accounts (guild_id, discord_user_id, platform, platform_id, platform_name)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(guild_id, discord_user_id, platform)
               DO UPDATE SET platform_id = excluded.platform_id,
                             platform_name = excluded.platform_name,
                             last_status = 'pending'
            """,
            (guild_id, discord_user_id, platform, platform_id, platform_name),
        )
        await self.db.commit()

    async def unlink_account(
        self, guild_id: int, discord_user_id: int, platform: str
    ) -> bool:
        cur = await self.db.execute(
            "DELETE FROM linked_accounts WHERE guild_id = ? AND discord_user_id = ? AND platform = ?",
            (guild_id, discord_user_id, platform),
        )
        await self.db.commit()
        return cur.rowcount > 0

    async def get_linked_account(
        self, guild_id: int, discord_user_id: int, platform: str
    ) -> Optional[dict]:
        async with self.db.execute(
            "SELECT * FROM linked_accounts WHERE guild_id = ? AND discord_user_id = ? AND platform = ?",
            (guild_id, discord_user_id, platform),
        ) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None

    async def get_all_linked(self, guild_id: int, platform: str) -> list[dict]:
        async with self.db.execute(
            "SELECT * FROM linked_accounts WHERE guild_id = ? AND platform = ? ORDER BY current_count DESC",
            (guild_id, platform),
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def get_accounts_due_refresh(
        self, guild_id: int, platform: str, interval: int
    ) -> list[dict]:
        threshold = time.time() - interval
        async with self.db.execute(
            "SELECT * FROM linked_accounts WHERE guild_id = ? AND platform = ? AND last_refreshed < ?",
            (guild_id, platform, threshold),
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def update_account_count(
        self,
        guild_id: int,
        discord_user_id: int,
        platform: str,
        count: int,
        status: str = "ok",
    ) -> None:
        now = time.time()
        await self.db.execute(
            """UPDATE linked_accounts
               SET current_count = ?, last_refreshed = ?, last_status = ?
               WHERE guild_id = ? AND discord_user_id = ? AND platform = ?""",
            (count, now, status, guild_id, discord_user_id, platform),
        )
        # record history
        await self.db.execute(
            "INSERT INTO sub_history (guild_id, discord_user_id, platform, count, recorded_at) VALUES (?, ?, ?, ?, ?)",
            (guild_id, discord_user_id, platform, count, now),
        )
        await self.db.commit()

    async def set_account_status(
        self, guild_id: int, discord_user_id: int, platform: str, status: str
    ) -> None:
        now = time.time()
        await self.db.execute(
            "UPDATE linked_accounts SET last_refreshed = ?, last_status = ? WHERE guild_id = ? AND discord_user_id = ? AND platform = ?",
            (now, status, guild_id, discord_user_id, platform),
        )
        await self.db.commit()

    # ── Sub / follower history ───────────────────────────────────────

    async def get_history(
        self, guild_id: int, discord_user_id: int, platform: str, limit: int = 100
    ) -> list[dict]:
        async with self.db.execute(
            "SELECT * FROM sub_history WHERE guild_id = ? AND discord_user_id = ? AND platform = ? ORDER BY recorded_at DESC LIMIT ?",
            (guild_id, discord_user_id, platform, limit),
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    # ── Role designs ─────────────────────────────────────────────────

    async def set_role_design(
        self,
        guild_id: int,
        platform: str,
        role_pattern: str,
        role_color: int,
        range_min: int = 0,
        range_max: Optional[int] = None,
        exact_count: Optional[int] = None,
    ) -> None:
        await self.db.execute(
            """INSERT INTO role_designs (guild_id, platform, range_min, range_max, exact_count, role_pattern, role_color)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(guild_id, platform, range_min, range_max, exact_count)
               DO UPDATE SET role_pattern = excluded.role_pattern,
                             role_color = excluded.role_color
            """,
            (guild_id, platform, range_min, range_max, exact_count, role_pattern, role_color),
        )
        await self.db.commit()

    async def remove_role_design(self, design_id: int) -> bool:
        cur = await self.db.execute(
            "DELETE FROM role_designs WHERE id = ?", (design_id,)
        )
        await self.db.commit()
        return cur.rowcount > 0

    async def get_role_designs(self, guild_id: int, platform: str) -> list[dict]:
        async with self.db.execute(
            "SELECT * FROM role_designs WHERE guild_id = ? AND platform = ? ORDER BY range_min",
            (guild_id, platform),
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def get_role_design_for_count(
        self, guild_id: int, platform: str, count: int
    ) -> Optional[dict]:
        """Find the best matching role design for a given count."""
        # exact match first
        async with self.db.execute(
            "SELECT * FROM role_designs WHERE guild_id = ? AND platform = ? AND exact_count = ?",
            (guild_id, platform, count),
        ) as cur:
            row = await cur.fetchone()
        if row:
            return dict(row)
        # range match
        async with self.db.execute(
            """SELECT * FROM role_designs
               WHERE guild_id = ? AND platform = ? AND exact_count IS NULL
                 AND range_min <= ? AND (range_max IS NULL OR range_max >= ?)
               ORDER BY range_min DESC LIMIT 1""",
            (guild_id, platform, count, count),
        ) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None

    # ── Scoreboard messages ──────────────────────────────────────────

    async def get_scoreboard_message(
        self, guild_id: int, platform: str
    ) -> Optional[dict]:
        async with self.db.execute(
            "SELECT * FROM scoreboard_messages WHERE guild_id = ? AND platform = ?",
            (guild_id, platform),
        ) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None

    async def set_scoreboard_message(
        self, guild_id: int, platform: str, channel_id: int, message_id: int
    ) -> None:
        await self.db.execute(
            """INSERT INTO scoreboard_messages (guild_id, platform, channel_id, message_id)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(guild_id, platform)
               DO UPDATE SET channel_id = excluded.channel_id, message_id = excluded.message_id""",
            (guild_id, platform, channel_id, message_id),
        )
        await self.db.commit()
