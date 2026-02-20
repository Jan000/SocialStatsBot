"""
Database module – SQLite via aiosqlite.

All tables:
  - guild_settings: per-guild configurable settings
  - linked_accounts: discord_user -> youtube/twitch mapping (multiple per user)
  - sub_history: timestamped subscriber/follower snapshots (deduplicated)
  - role_designs: custom role name/colour patterns per range
  - scoreboard_messages: persistent scoreboard message IDs
"""

from __future__ import annotations

import logging
import aiosqlite
import time
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

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
    yt_default_role_pattern    TEXT    DEFAULT '{name} - {count} Abos',
    tw_default_role_pattern    TEXT    DEFAULT '{name} - {count} Follower',
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
    UNIQUE(guild_id, discord_user_id, platform, platform_id)
);

CREATE TABLE IF NOT EXISTS sub_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id        INTEGER NOT NULL,
    discord_user_id INTEGER NOT NULL,
    platform        TEXT    NOT NULL,
    platform_id     TEXT    NOT NULL DEFAULT '',
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
    role_pattern    TEXT    NOT NULL DEFAULT '{name} - {count} Abos',
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
CREATE INDEX IF NOT EXISTS idx_history_account ON sub_history(guild_id, discord_user_id, platform, platform_id);
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
        await self._migrate()

    async def _migrate(self) -> None:
        """Run migrations for schema changes on existing databases."""
        try:
            # Migration: multi-account support (old UNIQUE was guild+user+platform)
            async with self.db.execute("PRAGMA index_list(linked_accounts)") as cur:
                indexes = await cur.fetchall()

            for idx in indexes:
                idx_name = idx[1]
                async with self.db.execute(f"PRAGMA index_info('{idx_name}')") as cur:
                    idx_cols = [row[2] for row in await cur.fetchall()]
                if set(idx_cols) == {"guild_id", "discord_user_id", "platform"}:
                    log.info("Migrating linked_accounts to multi-account schema...")
                    await self.db.executescript("""
                        ALTER TABLE linked_accounts RENAME TO _linked_accounts_old;
                        CREATE TABLE linked_accounts (
                            id              INTEGER PRIMARY KEY AUTOINCREMENT,
                            guild_id        INTEGER NOT NULL,
                            discord_user_id INTEGER NOT NULL,
                            platform        TEXT    NOT NULL CHECK(platform IN ('youtube', 'twitch')),
                            platform_id     TEXT    NOT NULL,
                            platform_name   TEXT    DEFAULT '',
                            current_count   INTEGER DEFAULT 0,
                            last_refreshed  REAL    DEFAULT 0,
                            last_status     TEXT    DEFAULT 'pending',
                            UNIQUE(guild_id, discord_user_id, platform, platform_id)
                        );
                        INSERT INTO linked_accounts SELECT * FROM _linked_accounts_old;
                        DROP TABLE _linked_accounts_old;
                    """)
                    await self.db.commit()
                    log.info("Migration complete.")
                    break

            # Migration: add platform_id to sub_history if missing
            async with self.db.execute("PRAGMA table_info(sub_history)") as cur:
                history_cols = [row[1] for row in await cur.fetchall()]
            if "platform_id" not in history_cols:
                log.info("Adding platform_id column to sub_history...")
                await self.db.execute(
                    "ALTER TABLE sub_history ADD COLUMN platform_id TEXT NOT NULL DEFAULT ''"
                )
                await self.db.commit()

            # Migration: update default role patterns from old format
            await self.db.execute("""
                UPDATE guild_settings
                SET yt_default_role_pattern = '{name} - {count} Abos'
                WHERE yt_default_role_pattern = '{count} YouTube Abos'
            """)
            await self.db.execute("""
                UPDATE guild_settings
                SET tw_default_role_pattern = '{name} - {count} Follower'
                WHERE tw_default_role_pattern = '{count} Twitch Follower'
            """)
            await self.db.commit()

        except Exception as e:
            log.warning("Migration check failed (may be fine for fresh DB): %s", e)

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
        """Link a platform account. Allows multiple accounts per user per platform."""
        await self.db.execute(
            """INSERT INTO linked_accounts (guild_id, discord_user_id, platform, platform_id, platform_name)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(guild_id, discord_user_id, platform, platform_id)
               DO UPDATE SET platform_name = excluded.platform_name,
                             last_status = 'pending'
            """,
            (guild_id, discord_user_id, platform, platform_id, platform_name),
        )
        await self.db.commit()

    async def unlink_account(
        self, guild_id: int, discord_user_id: int, platform: str, platform_id: str
    ) -> bool:
        """Unlink a specific platform account by platform_id."""
        cur = await self.db.execute(
            "DELETE FROM linked_accounts WHERE guild_id = ? AND discord_user_id = ? AND platform = ? AND platform_id = ?",
            (guild_id, discord_user_id, platform, platform_id),
        )
        await self.db.commit()
        return cur.rowcount > 0

    async def unlink_account_by_name(
        self, guild_id: int, discord_user_id: int, platform: str, platform_name: str
    ) -> Optional[str]:
        """Unlink by platform_name (case-insensitive). Returns platform_id if found."""
        async with self.db.execute(
            "SELECT platform_id FROM linked_accounts WHERE guild_id = ? AND discord_user_id = ? AND platform = ? AND LOWER(platform_name) = LOWER(?)",
            (guild_id, discord_user_id, platform, platform_name),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        platform_id = row[0]
        await self.db.execute(
            "DELETE FROM linked_accounts WHERE guild_id = ? AND discord_user_id = ? AND platform = ? AND platform_id = ?",
            (guild_id, discord_user_id, platform, platform_id),
        )
        await self.db.commit()
        return platform_id

    async def get_linked_account(
        self, guild_id: int, discord_user_id: int, platform: str, platform_id: str
    ) -> Optional[dict]:
        """Get a specific linked account."""
        async with self.db.execute(
            "SELECT * FROM linked_accounts WHERE guild_id = ? AND discord_user_id = ? AND platform = ? AND platform_id = ?",
            (guild_id, discord_user_id, platform, platform_id),
        ) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None

    async def find_linked_account_by_name(
        self, guild_id: int, discord_user_id: int, platform: str, platform_name: str
    ) -> Optional[dict]:
        """Find linked account by platform_name (case-insensitive)."""
        async with self.db.execute(
            "SELECT * FROM linked_accounts WHERE guild_id = ? AND discord_user_id = ? AND platform = ? AND LOWER(platform_name) = LOWER(?)",
            (guild_id, discord_user_id, platform, platform_name),
        ) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None

    async def get_linked_accounts_for_user(
        self, guild_id: int, discord_user_id: int, platform: str
    ) -> list[dict]:
        """Get all linked accounts for a user on a platform."""
        async with self.db.execute(
            "SELECT * FROM linked_accounts WHERE guild_id = ? AND discord_user_id = ? AND platform = ? ORDER BY current_count DESC",
            (guild_id, discord_user_id, platform),
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

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
        platform_id: str,
        count: int,
        status: str = "ok",
    ) -> None:
        """Update account count and record history (deduplicated)."""
        now = time.time()
        await self.db.execute(
            """UPDATE linked_accounts
               SET current_count = ?, last_refreshed = ?, last_status = ?
               WHERE guild_id = ? AND discord_user_id = ? AND platform = ? AND platform_id = ?""",
            (count, now, status, guild_id, discord_user_id, platform, platform_id),
        )

        # Deduplicated history: if last two entries have the same count as new,
        # update the latest entry's timestamp instead of inserting a new one.
        # This keeps the first and last entry of unchanged streaks.
        async with self.db.execute(
            """SELECT id, count FROM sub_history
               WHERE guild_id = ? AND discord_user_id = ? AND platform = ? AND platform_id = ?
               ORDER BY recorded_at DESC LIMIT 2""",
            (guild_id, discord_user_id, platform, platform_id),
        ) as cur:
            recent = await cur.fetchall()

        if len(recent) >= 2 and recent[0][1] == count and recent[1][1] == count:
            # prev2, prev1, and new are the same count – update latest timestamp
            await self.db.execute(
                "UPDATE sub_history SET recorded_at = ? WHERE id = ?",
                (now, recent[0][0]),
            )
        else:
            # Count changed or not enough history – insert new entry
            await self.db.execute(
                "INSERT INTO sub_history (guild_id, discord_user_id, platform, platform_id, count, recorded_at) VALUES (?, ?, ?, ?, ?, ?)",
                (guild_id, discord_user_id, platform, platform_id, count, now),
            )
        await self.db.commit()

    async def set_account_status(
        self, guild_id: int, discord_user_id: int, platform: str, platform_id: str, status: str
    ) -> None:
        now = time.time()
        await self.db.execute(
            "UPDATE linked_accounts SET last_refreshed = ?, last_status = ? WHERE guild_id = ? AND discord_user_id = ? AND platform = ? AND platform_id = ?",
            (now, status, guild_id, discord_user_id, platform, platform_id),
        )
        await self.db.commit()

    # ── Sub / follower history ───────────────────────────────────────

    async def get_history(
        self, guild_id: int, discord_user_id: int, platform: str, platform_id: str, limit: int = 100
    ) -> list[dict]:
        async with self.db.execute(
            "SELECT * FROM sub_history WHERE guild_id = ? AND discord_user_id = ? AND platform = ? AND platform_id = ? ORDER BY recorded_at DESC LIMIT ?",
            (guild_id, discord_user_id, platform, platform_id, limit),
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def get_history_since(
        self, guild_id: int, discord_user_id: int, platform: str, platform_id: str, since: float
    ) -> list[dict]:
        """Get history entries since a given timestamp (DESC order)."""
        async with self.db.execute(
            "SELECT * FROM sub_history WHERE guild_id = ? AND discord_user_id = ? AND platform = ? AND platform_id = ? AND recorded_at >= ? ORDER BY recorded_at DESC",
            (guild_id, discord_user_id, platform, platform_id, since),
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
