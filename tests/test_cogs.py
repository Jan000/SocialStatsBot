"""Tests for cog utility functions (detect_platform_from_url, etc.)."""

from __future__ import annotations

import pytest

from bot.cogs import detect_platform_from_url


# ── detect_platform_from_url ─────────────────────────────────────────


class TestDetectPlatformFromUrl:
    """Test URL-based platform detection."""

    @pytest.mark.parametrize("url,expected", [
        ("https://www.youtube.com/@Niruki", "youtube"),
        ("https://youtube.com/channel/UC1234", "youtube"),
        ("http://www.youtube.com/@SomeChannel", "youtube"),
        ("https://youtu.be/dQw4w9WgXcQ", "youtube"),
    ])
    def test_youtube_urls(self, url: str, expected: str) -> None:
        assert detect_platform_from_url(url) == expected

    @pytest.mark.parametrize("url,expected", [
        ("https://www.twitch.tv/niruki", "twitch"),
        ("https://twitch.tv/somestreamer", "twitch"),
        ("http://www.twitch.tv/other", "twitch"),
    ])
    def test_twitch_urls(self, url: str, expected: str) -> None:
        assert detect_platform_from_url(url) == expected

    @pytest.mark.parametrize("url,expected", [
        ("https://www.instagram.com/niruki", "instagram"),
        ("https://instagram.com/someone", "instagram"),
        ("http://www.instagram.com/test.user/", "instagram"),
    ])
    def test_instagram_urls(self, url: str, expected: str) -> None:
        assert detect_platform_from_url(url) == expected

    @pytest.mark.parametrize("url,expected", [
        ("https://www.tiktok.com/@niruki", "tiktok"),
        ("https://tiktok.com/@someone", "tiktok"),
        ("http://www.tiktok.com/@test.user/", "tiktok"),
    ])
    def test_tiktok_urls(self, url: str, expected: str) -> None:
        assert detect_platform_from_url(url) == expected

    @pytest.mark.parametrize("input_str", [
        "niruki",
        "@niruki",
        "UC1234567890",
        "some random text",
        "",
    ])
    def test_non_urls_return_none(self, input_str: str) -> None:
        assert detect_platform_from_url(input_str) is None
