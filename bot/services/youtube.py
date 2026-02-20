"""
YouTube Data API v3 service – fetch subscriber counts.
"""

from __future__ import annotations

import re
import aiohttp
from typing import Optional

YT_CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"

# Patterns to extract a handle or channel ID from various YouTube URL formats
_YT_HANDLE_RE = re.compile(
    r"(?:https?://)?(?:www\.)?youtube\.com/@([\w.-]+)", re.IGNORECASE
)
_YT_CHANNEL_ID_RE = re.compile(
    r"(?:https?://)?(?:www\.)?youtube\.com/channel/(UC[\w-]+)", re.IGNORECASE
)
_YT_RAW_HANDLE_RE = re.compile(r"^@([\w.-]+)$")
_YT_RAW_CHANNEL_ID_RE = re.compile(r"^UC[\w-]+$")


def parse_youtube_input(value: str) -> tuple[str, str]:
    """
    Parse a YouTube input string and return (type, identifier).
    type is 'handle', 'id', or 'unknown'.
    Accepts:
      - https://www.youtube.com/@Niruki  -> ('handle', 'Niruki')
      - @Niruki                          -> ('handle', 'Niruki')
      - https://www.youtube.com/channel/UCxxx -> ('id', 'UCxxx')
      - UCxxx                            -> ('id', 'UCxxx')
    """
    value = value.strip()

    m = _YT_HANDLE_RE.match(value)
    if m:
        return ("handle", m.group(1))

    m = _YT_CHANNEL_ID_RE.match(value)
    if m:
        return ("id", m.group(1))

    m = _YT_RAW_HANDLE_RE.match(value)
    if m:
        return ("handle", m.group(1))

    if _YT_RAW_CHANNEL_ID_RE.match(value):
        return ("id", value)

    return ("unknown", value)


class YouTubeService:
    """Fetches YouTube channel subscriber counts."""

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def get_subscriber_count(self, channel_id: str) -> Optional[int]:
        """
        Return the subscriber count for a YouTube channel ID.
        Returns None on error or if hidden.
        """
        session = await self._get_session()
        params = {
            "part": "statistics",
            "id": channel_id,
            "key": self.api_key,
        }
        try:
            async with session.get(YT_CHANNELS_URL, params=params) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                items = data.get("items", [])
                if not items:
                    return None
                stats = items[0].get("statistics", {})
                if stats.get("hiddenSubscriberCount", False):
                    return None
                return int(stats.get("subscriberCount", 0))
        except Exception:
            return None

    async def get_channel_info(self, channel_id: str) -> Optional[dict]:
        """Return basic channel info (title, id, sub count) by channel ID."""
        session = await self._get_session()
        params = {
            "part": "snippet,statistics",
            "id": channel_id,
            "key": self.api_key,
        }
        return await self._fetch_channel_info(session, params)

    async def get_channel_info_by_handle(self, handle: str) -> Optional[dict]:
        """Return basic channel info by @handle (without the @ prefix)."""
        session = await self._get_session()
        params = {
            "part": "snippet,statistics",
            "forHandle": handle,
            "key": self.api_key,
        }
        return await self._fetch_channel_info(session, params)

    async def resolve_channel(self, user_input: str) -> Optional[dict]:
        """
        Resolve a YouTube channel from flexible user input.
        Accepts: channel URL, @handle, or channel ID.
        Returns channel info dict or None.
        """
        input_type, identifier = parse_youtube_input(user_input)

        if input_type == "handle":
            return await self.get_channel_info_by_handle(identifier)
        elif input_type == "id":
            return await self.get_channel_info(identifier)
        else:
            # Try as channel ID first, then as handle
            info = await self.get_channel_info(identifier)
            if info:
                return info
            return await self.get_channel_info_by_handle(identifier)

    async def _fetch_channel_info(self, session: aiohttp.ClientSession, params: dict) -> Optional[dict]:
        """Shared helper to fetch and parse channel info from the API."""
        try:
            async with session.get(YT_CHANNELS_URL, params=params) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                items = data.get("items", [])
                if not items:
                    return None
                item = items[0]
                snippet = item.get("snippet", {})
                stats = item.get("statistics", {})
                return {
                    "id": item["id"],
                    "title": snippet.get("title", "Unknown"),
                    "subscriber_count": int(stats.get("subscriberCount", 0)),
                    "hidden": stats.get("hiddenSubscriberCount", False),
                }
        except Exception:
            return None
