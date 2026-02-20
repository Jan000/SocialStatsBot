"""Tests for role utility functions (pure logic, no Discord API)."""

from __future__ import annotations

import pytest
import pytest_asyncio
from pathlib import Path

from bot.roles import format_count, build_role_name, compute_role_name_and_color
from bot.database import Database


# ── format_count ──────────────────────────────────────────────

def test_format_count_small():
    assert format_count(0) == "0"
    assert format_count(99) == "99"
    assert format_count(999) == "999"


def test_format_count_thousands():
    assert format_count(1_000) == "1.000"
    assert format_count(12_345) == "12.345"
    assert format_count(999_999) == "999.999"


def test_format_count_millions():
    assert format_count(1_000_000) == "1.000.000"
    assert format_count(1_234_567) == "1.234.567"


# ── build_role_name ───────────────────────────────────────────

def test_build_role_name_youtube():
    result = build_role_name("youtube", "{name} - {count} Abos", 1234, "Niruki")
    assert result == "[YouTube] Niruki - 1.234 Abos"


def test_build_role_name_twitch():
    result = build_role_name("twitch", "{name} - {count} Follower", 500, "Niruki")
    assert result == "[Twitch] Niruki - 500 Follower"


def test_build_role_name_no_name():
    result = build_role_name("youtube", "{count} Subs", 100)
    assert result == "[YouTube] 100 Subs"


def test_build_role_name_unknown_platform():
    result = build_role_name("unknown", "{count}", 10)
    assert result == "10"


# ── compute_role_name_and_color ───────────────────────────────

@pytest_asyncio.fixture
async def db(tmp_path: Path):
    database = Database(path=tmp_path / "test.db")
    await database.connect()
    yield database
    await database.close()


@pytest.mark.asyncio
async def test_compute_default_pattern(db: Database):
    settings = await db.get_guild_settings(1)
    name, color = await compute_role_name_and_color(db, 1, "youtube", 1500, settings, "Ch")
    expected_pattern = settings.get("yt_default_role_pattern", "{name} - {count}")
    expected = build_role_name("youtube", expected_pattern, 1500, "Ch")
    assert name == expected


@pytest.mark.asyncio
async def test_compute_exact_design(db: Database):
    settings = await db.get_guild_settings(1)
    await db.set_role_design(1, "youtube", "⭐ {name} {count}", 0xFF0000, exact_count=1000)
    name, color = await compute_role_name_and_color(db, 1, "youtube", 1000, settings, "X")
    assert name == "[YouTube] ⭐ X 1.000"
    assert color == 0xFF0000


@pytest.mark.asyncio
async def test_compute_range_design(db: Database):
    settings = await db.get_guild_settings(1)
    await db.set_role_design(1, "youtube", "Silver {name}", 0xC0C0C0, range_min=100, range_max=999)
    name, color = await compute_role_name_and_color(db, 1, "youtube", 500, settings, "A")
    assert name == "[YouTube] Silver A"
    assert color == 0xC0C0C0


@pytest.mark.asyncio
async def test_compute_exact_beats_range(db: Database):
    settings = await db.get_guild_settings(1)
    await db.set_role_design(1, "youtube", "Range {name}", 0, range_min=0, range_max=2000)
    await db.set_role_design(1, "youtube", "Exact {name}", 0xFF, exact_count=500)
    name, color = await compute_role_name_and_color(db, 1, "youtube", 500, settings, "B")
    assert name == "[YouTube] Exact B"
    assert color == 0xFF
