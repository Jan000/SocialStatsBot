"""Tests for the Database class."""

from __future__ import annotations

import asyncio
import time
import pytest
import pytest_asyncio
from pathlib import Path

from bot.database import Database


@pytest_asyncio.fixture
async def db(tmp_path: Path):
    """Create a temporary database for testing."""
    database = Database(path=tmp_path / "test.db")
    await database.connect()
    yield database
    await database.close()


@pytest.mark.asyncio
async def test_guild_settings_default(db: Database):
    """get_guild_settings should create defaults on first access."""
    settings = await db.get_guild_settings(123)
    assert settings["guild_id"] == 123
    assert settings["tw_refresh_interval"] == 600


@pytest.mark.asyncio
async def test_update_guild_setting(db: Database):
    settings = await db.get_guild_settings(1)
    assert settings["yt_refresh_interval"] == 600
    await db.update_guild_setting(1, "yt_refresh_interval", 300)
    settings = await db.get_guild_settings(1)
    assert settings["yt_refresh_interval"] == 300


@pytest.mark.asyncio
async def test_update_guild_setting_invalid_key(db: Database):
    with pytest.raises(ValueError, match="Unknown setting"):
        await db.update_guild_setting(1, "invalid_key", 42)


@pytest.mark.asyncio
async def test_link_and_get_account(db: Database):
    await db.link_account(1, 100, "youtube", "UC123", "TestChannel")
    acc = await db.get_linked_account(1, 100, "youtube", "UC123")
    assert acc is not None
    assert acc["platform_name"] == "TestChannel"
    assert acc["current_count"] == 0


@pytest.mark.asyncio
async def test_multi_account_link(db: Database):
    """A user should be able to link multiple accounts per platform."""
    await db.link_account(1, 100, "youtube", "UC111", "Channel1")
    await db.link_account(1, 100, "youtube", "UC222", "Channel2")
    accounts = await db.get_linked_accounts_for_user(1, 100, "youtube")
    assert len(accounts) == 2
    names = {a["platform_name"] for a in accounts}
    assert names == {"Channel1", "Channel2"}


@pytest.mark.asyncio
async def test_unlink_account(db: Database):
    await db.link_account(1, 100, "youtube", "UC123", "Test")
    result = await db.unlink_account(1, 100, "youtube", "UC123")
    assert result is True
    acc = await db.get_linked_account(1, 100, "youtube", "UC123")
    assert acc is None


@pytest.mark.asyncio
async def test_unlink_account_by_name(db: Database):
    await db.link_account(1, 100, "twitch", "12345", "Niruki")
    pid = await db.unlink_account_by_name(1, 100, "twitch", "niruki")  # case insensitive
    assert pid == "12345"
    acc = await db.get_linked_account(1, 100, "twitch", "12345")
    assert acc is None


@pytest.mark.asyncio
async def test_find_linked_account_by_name(db: Database):
    await db.link_account(1, 100, "youtube", "UC123", "MyChannel")
    acc = await db.find_linked_account_by_name(1, 100, "youtube", "mychannel")
    assert acc is not None
    assert acc["platform_id"] == "UC123"


@pytest.mark.asyncio
async def test_update_account_count_and_history(db: Database):
    await db.link_account(1, 100, "youtube", "UC123", "Test")
    await db.update_account_count(1, 100, "youtube", "UC123", 1000)
    acc = await db.get_linked_account(1, 100, "youtube", "UC123")
    assert acc["current_count"] == 1000
    assert acc["last_status"] == "ok"

    history = await db.get_history(1, 100, "youtube", "UC123")
    assert len(history) == 1
    assert history[0]["count"] == 1000


@pytest.mark.asyncio
async def test_history_deduplication(db: Database):
    """Consecutive identical counts should collapse to 2 entries (start + end)."""
    await db.link_account(1, 100, "youtube", "UC123", "Test")

    # Three updates with the same count
    await db.update_account_count(1, 100, "youtube", "UC123", 500)
    await db.update_account_count(1, 100, "youtube", "UC123", 500)
    await db.update_account_count(1, 100, "youtube", "UC123", 500)

    history = await db.get_history(1, 100, "youtube", "UC123")
    # Should only have 2 entries: original + updated timestamp
    assert len(history) == 2


@pytest.mark.asyncio
async def test_history_new_count_creates_entry(db: Database):
    await db.link_account(1, 100, "youtube", "UC123", "Test")
    await db.update_account_count(1, 100, "youtube", "UC123", 500)
    await db.update_account_count(1, 100, "youtube", "UC123", 600)

    history = await db.get_history(1, 100, "youtube", "UC123")
    assert len(history) == 2
    assert history[0]["count"] == 600  # newest first
    assert history[1]["count"] == 500


@pytest.mark.asyncio
async def test_get_history_since(db: Database):
    await db.link_account(1, 100, "youtube", "UC123", "Test")
    await db.update_account_count(1, 100, "youtube", "UC123", 100)
    await db.update_account_count(1, 100, "youtube", "UC123", 200)

    since = time.time() - 10  # last 10 seconds
    history = await db.get_history_since(1, 100, "youtube", "UC123", since)
    assert len(history) == 2


@pytest.mark.asyncio
async def test_get_all_linked(db: Database):
    await db.link_account(1, 100, "youtube", "UC111", "A")
    await db.link_account(1, 200, "youtube", "UC222", "B")
    await db.link_account(1, 100, "twitch", "T111", "C")

    yt = await db.get_all_linked(1, "youtube")
    assert len(yt) == 2
    tw = await db.get_all_linked(1, "twitch")
    assert len(tw) == 1


@pytest.mark.asyncio
async def test_accounts_due_refresh(db: Database):
    await db.link_account(1, 100, "youtube", "UC123", "Test")
    # Account was never refreshed (last_refreshed=0), so it should be due
    due = await db.get_accounts_due_refresh(1, "youtube", 600)
    assert len(due) == 1

    # After refresh, it should not be due
    await db.update_account_count(1, 100, "youtube", "UC123", 1000)
    due = await db.get_accounts_due_refresh(1, "youtube", 600)
    assert len(due) == 0


@pytest.mark.asyncio
async def test_set_account_status(db: Database):
    await db.link_account(1, 100, "youtube", "UC123", "Test")
    await db.set_account_status(1, 100, "youtube", "UC123", "error")
    acc = await db.get_linked_account(1, 100, "youtube", "UC123")
    assert acc["last_status"] == "error"


@pytest.mark.asyncio
async def test_role_design_exact_match(db: Database):
    await db.set_role_design(1, "youtube", "⭐ {name} - {count}", 0xFF0000, exact_count=1000)
    design = await db.get_role_design_for_count(1, "youtube", 1000)
    assert design is not None
    assert design["role_pattern"] == "⭐ {name} - {count}"


@pytest.mark.asyncio
async def test_role_design_range_match(db: Database):
    await db.set_role_design(1, "youtube", "Silver {name} - {count}", 0xC0C0C0, range_min=100, range_max=999)
    design = await db.get_role_design_for_count(1, "youtube", 500)
    assert design is not None
    assert design["role_pattern"] == "Silver {name} - {count}"

    # Outside range
    design = await db.get_role_design_for_count(1, "youtube", 1500)
    assert design is None


@pytest.mark.asyncio
async def test_role_design_exact_over_range(db: Database):
    """Exact match should take priority over range match."""
    await db.set_role_design(1, "youtube", "Range", 0, range_min=0, range_max=2000)
    await db.set_role_design(1, "youtube", "Exact", 0xFF0000, exact_count=1000)
    design = await db.get_role_design_for_count(1, "youtube", 1000)
    assert design is not None
    assert design["role_pattern"] == "Exact"


@pytest.mark.asyncio
async def test_remove_role_design(db: Database):
    await db.set_role_design(1, "youtube", "Test", 0, range_min=0)
    designs = await db.get_role_designs(1, "youtube")
    assert len(designs) == 1
    removed = await db.remove_role_design(designs[0]["id"])
    assert removed is True
    designs = await db.get_role_designs(1, "youtube")
    assert len(designs) == 0


@pytest.mark.asyncio
async def test_scoreboard_message(db: Database):
    ids = await db.get_scoreboard_message_ids(1, "youtube")
    assert ids == []

    await db.set_scoreboard_message_ids(1, "youtube", 999, [12345])
    ids = await db.get_scoreboard_message_ids(1, "youtube")
    assert ids == [12345]

    # Upsert with two message IDs
    await db.set_scoreboard_message_ids(1, "youtube", 999, [12345, 67890])
    ids = await db.get_scoreboard_message_ids(1, "youtube")
    assert ids == [12345, 67890]


# ── Instagram & TikTok platform tests ───────────────────────────


@pytest.mark.asyncio
async def test_link_instagram_account(db: Database):
    """Instagram accounts should link and retrieve correctly."""
    await db.link_account(1, 100, "instagram", "niruki", "Niruki")
    acc = await db.get_linked_account(1, 100, "instagram", "niruki")
    assert acc is not None
    assert acc["platform_name"] == "Niruki"
    assert acc["current_count"] == 0


@pytest.mark.asyncio
async def test_link_tiktok_account(db: Database):
    """TikTok accounts should link and retrieve correctly."""
    await db.link_account(1, 100, "tiktok", "niruki", "Niruki")
    acc = await db.get_linked_account(1, 100, "tiktok", "niruki")
    assert acc is not None
    assert acc["platform_name"] == "Niruki"
    assert acc["current_count"] == 0


@pytest.mark.asyncio
async def test_all_four_platforms(db: Database):
    """A user should be able to link accounts across all four platforms."""
    await db.link_account(1, 100, "youtube", "UC123", "YT")
    await db.link_account(1, 100, "twitch", "T123", "TW")
    await db.link_account(1, 100, "instagram", "ig_user", "IG")
    await db.link_account(1, 100, "tiktok", "tt_user", "TT")

    for plat in ("youtube", "twitch", "instagram", "tiktok"):
        accs = await db.get_linked_accounts_for_user(1, 100, plat)
        assert len(accs) == 1, f"Expected 1 account for {plat}"


@pytest.mark.asyncio
async def test_instagram_guild_settings(db: Database):
    """Instagram-specific guild settings should be accessible."""
    settings = await db.get_guild_settings(1)
    assert settings.get("ig_refresh_interval") == 600
    await db.update_guild_setting(1, "ig_refresh_interval", 300)
    settings = await db.get_guild_settings(1)
    assert settings["ig_refresh_interval"] == 300


@pytest.mark.asyncio
async def test_tiktok_guild_settings(db: Database):
    """TikTok-specific guild settings should be accessible."""
    settings = await db.get_guild_settings(1)
    assert settings.get("tt_refresh_interval") == 600
    await db.update_guild_setting(1, "tt_scoreboard_channel_id", 42)
    settings = await db.get_guild_settings(1)
    assert settings["tt_scoreboard_channel_id"] == 42


@pytest.mark.asyncio
async def test_role_design_instagram(db: Database):
    """Role designs should work for Instagram platform."""
    await db.set_role_design(1, "instagram", "📷 {name} - {count}", 0xDB4A76, range_min=100)
    design = await db.get_role_design_for_count(1, "instagram", 500)
    assert design is not None
    assert design["role_pattern"] == "📷 {name} - {count}"


@pytest.mark.asyncio
async def test_scoreboard_message_tiktok(db: Database):
    """Scoreboard messages should work for TikTok platform."""
    await db.set_scoreboard_message_ids(1, "tiktok", 999, [11111])
    ids = await db.get_scoreboard_message_ids(1, "tiktok")
    assert ids == [11111]


# ── Account request tests ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_and_get_account_request(db: Database):
    """create_account_request should return an id, get should retrieve it."""
    rid = await db.create_account_request(
        guild_id=1, discord_user_id=100, request_type="link",
        platform="youtube", platform_id="UC123", platform_name="TestChannel",
        follower_count=500,
    )
    assert rid is not None and rid > 0
    req = await db.get_account_request(rid)
    assert req is not None
    assert req["guild_id"] == 1
    assert req["discord_user_id"] == 100
    assert req["request_type"] == "link"
    assert req["platform"] == "youtube"
    assert req["platform_id"] == "UC123"
    assert req["platform_name"] == "TestChannel"
    assert req["follower_count"] == 500
    assert req["status"] == "pending"


@pytest.mark.asyncio
async def test_update_request_status(db: Database):
    """update_request_status should change status and optionally message_id."""
    rid = await db.create_account_request(
        guild_id=1, discord_user_id=100, request_type="link",
        platform="twitch", platform_id="tw123", platform_name="Test",
    )
    await db.update_request_status(rid, "approved", message_id=99999)
    req = await db.get_account_request(rid)
    assert req["status"] == "approved"
    assert req["message_id"] == 99999


@pytest.mark.asyncio
async def test_get_pending_requests(db: Database):
    """get_pending_requests should only return pending requests."""
    r1 = await db.create_account_request(1, 100, "link", "youtube", "UC1", "Ch1")
    r2 = await db.create_account_request(1, 200, "unlink", "twitch", "tw1", "Ch2")
    await db.update_request_status(r1, "approved")
    pending = await db.get_pending_requests(1)
    assert len(pending) == 1
    assert pending[0]["id"] == r2


@pytest.mark.asyncio
async def test_request_channel_id_setting(db: Database):
    """request_channel_id should be a valid guild setting."""
    settings = await db.get_guild_settings(1)
    assert settings.get("request_channel_id") == 0
    await db.update_guild_setting(1, "request_channel_id", 12345)
    settings = await db.get_guild_settings(1)
    assert settings["request_channel_id"] == 12345
