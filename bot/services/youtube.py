"""
YouTube Data API v3 service – fetch subscriber counts.
"""

from __future__ import annotations

import aiohttp
from typing import Optional

YT_CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"


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
        """Return basic channel info (title, id, sub count)."""
        session = await self._get_session()
        params = {
            "part": "snippet,statistics",
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
