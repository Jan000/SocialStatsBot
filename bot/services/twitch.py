"""
Twitch Helix API service – fetch follower counts.
"""

from __future__ import annotations

import aiohttp
from typing import Optional

TWITCH_AUTH_URL = "https://id.twitch.tv/oauth2/token"
TWITCH_USERS_URL = "https://api.twitch.tv/helix/users"
TWITCH_FOLLOWERS_URL = "https://api.twitch.tv/helix/channels/followers"


class TwitchService:
    """Fetches Twitch channel follower counts using the Helix API."""

    def __init__(self, client_id: str, client_secret: str) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self._session: Optional[aiohttp.ClientSession] = None
        self._access_token: Optional[str] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def _ensure_token(self) -> str:
        """Obtain an app access token if we don't have one."""
        if self._access_token:
            return self._access_token
        session = await self._get_session()
        params = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials",
        }
        async with session.post(TWITCH_AUTH_URL, params=params) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Twitch auth failed: {resp.status}")
            data = await resp.json()
            self._access_token = data["access_token"]
            return self._access_token

    async def _headers(self) -> dict:
        token = await self._ensure_token()
        return {
            "Client-ID": self.client_id,
            "Authorization": f"Bearer {token}",
        }

    async def get_user(self, login: str) -> Optional[dict]:
        """Get Twitch user info by login name."""
        session = await self._get_session()
        headers = await self._headers()
        params = {"login": login}
        try:
            async with session.get(TWITCH_USERS_URL, headers=headers, params=params) as resp:
                if resp.status == 401:
                    self._access_token = None
                    headers = await self._headers()
                    async with session.get(TWITCH_USERS_URL, headers=headers, params=params) as retry:
                        data = await retry.json()
                else:
                    data = await resp.json()
                users = data.get("data", [])
                if not users:
                    return None
                return users[0]
        except Exception:
            return None

    async def get_user_by_id(self, user_id: str) -> Optional[dict]:
        """Get Twitch user info by user ID."""
        session = await self._get_session()
        headers = await self._headers()
        params = {"id": user_id}
        try:
            async with session.get(TWITCH_USERS_URL, headers=headers, params=params) as resp:
                if resp.status == 401:
                    self._access_token = None
                    headers = await self._headers()
                    async with session.get(TWITCH_USERS_URL, headers=headers, params=params) as retry:
                        data = await retry.json()
                else:
                    data = await resp.json()
                users = data.get("data", [])
                if not users:
                    return None
                return users[0]
        except Exception:
            return None

    async def get_follower_count(self, broadcaster_id: str) -> Optional[int]:
        """
        Return the follower count for a Twitch broadcaster ID.
        Uses the /channels/followers endpoint (total field).
        """
        session = await self._get_session()
        headers = await self._headers()
        params = {"broadcaster_id": broadcaster_id, "first": "1"}
        try:
            async with session.get(TWITCH_FOLLOWERS_URL, headers=headers, params=params) as resp:
                if resp.status == 401:
                    self._access_token = None
                    headers = await self._headers()
                    async with session.get(TWITCH_FOLLOWERS_URL, headers=headers, params=params) as retry:
                        data = await retry.json()
                else:
                    data = await resp.json()
                return data.get("total")
        except Exception:
            return None
