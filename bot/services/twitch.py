"""
Twitch Helix API service – fetch follower counts via Client Credentials.
"""

from __future__ import annotations

import re
import logging
import aiohttp
from typing import Optional

from bot.ratelimit import RateLimiter

log = logging.getLogger(__name__)

TWITCH_HELIX = "https://api.twitch.tv/helix"
TWITCH_OAUTH = "https://id.twitch.tv/oauth2/token"

# Twitch Helix rate limit: 800 req / 60s for app access tokens.
# We stay well below with 20 req/s burst.
_DEFAULT_TW_MAX_CALLS = 20
_DEFAULT_TW_PERIOD = 1.0

# Patterns for parsing Twitch input
_TW_URL_RE = re.compile(
    r"(?:https?://)?(?:www\.)?twitch\.tv/([\w]+)/?", re.IGNORECASE
)
_TW_RAW_LOGIN_RE = re.compile(r"^[\w]{2,25}$")


def parse_twitch_input(value: str) -> str:
    """
    Parse a Twitch input and return the login name.

    Accepts:
      - https://www.twitch.tv/niruki  -> 'niruki'
      - twitch.tv/niruki               -> 'niruki'
      - niruki                         -> 'niruki'
    """
    value = value.strip()
    m = _TW_URL_RE.match(value)
    if m:
        return m.group(1).lower()
    if _TW_RAW_LOGIN_RE.match(value):
        return value.lower()
    return value.lower()


class TwitchService:
    """Fetches Twitch follower counts using Helix API with Client Credentials."""

    def __init__(self, client_id: str, client_secret: str, *, max_calls: int = _DEFAULT_TW_MAX_CALLS, period: float = _DEFAULT_TW_PERIOD) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self._session: Optional[aiohttp.ClientSession] = None
        self._access_token: Optional[str] = None
        self._rate_limiter = RateLimiter(max_calls, period)

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def _ensure_token(self) -> bool:
        """Obtain or refresh the app access token."""
        if self._access_token:
            return True
        session = await self._get_session()
        try:
            async with session.post(
                TWITCH_OAUTH,
                params={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "grant_type": "client_credentials",
                },
            ) as resp:
                if resp.status != 200:
                    log.error("Twitch OAuth failed: %s", resp.status)
                    return False
                data = await resp.json()
                self._access_token = data["access_token"]
                return True
        except Exception as e:
            log.error("Twitch OAuth error: %s", e)
            return False

    def _headers(self) -> dict:
        return {
            "Client-ID": self.client_id,
            "Authorization": f"Bearer {self._access_token}",
        }

    async def _helix_get(self, endpoint: str, params: dict) -> Optional[dict]:
        """Make an authenticated GET request to the Helix API."""
        if not await self._ensure_token():
            return None
        session = await self._get_session()
        try:
            async with self._rate_limiter:
                async with session.get(
                    f"{TWITCH_HELIX}/{endpoint}", headers=self._headers(), params=params
                ) as resp:
                    if resp.status == 401:
                        self._access_token = None
                        if not await self._ensure_token():
                            return None
                        async with session.get(
                            f"{TWITCH_HELIX}/{endpoint}", headers=self._headers(), params=params
                        ) as resp2:
                            if resp2.status != 200:
                                return None
                            return await resp2.json()
                    if resp.status != 200:
                        return None
                    return await resp.json()
        except Exception as e:
            log.error("Twitch Helix error (%s): %s", endpoint, e)
            return None

    async def get_user(self, login: str) -> Optional[dict]:
        """Lookup a Twitch user by login name. Returns dict with id, login, display_name."""
        data = await self._helix_get("users", {"login": login})
        if not data or not data.get("data"):
            return None
        user = data["data"][0]
        return {
            "id": user["id"],
            "login": user["login"],
            "display_name": user.get("display_name", user["login"]),
        }

    async def resolve_user(self, user_input: str) -> Optional[dict]:
        """Resolve a Twitch user from flexible input (URL, login name).

        Returns dict with id, login, display_name, or None.
        """
        login = parse_twitch_input(user_input)
        return await self.get_user(login)

    async def get_follower_count(self, broadcaster_id: str) -> Optional[int]:
        """Return the follower count for a Twitch broadcaster ID."""
        data = await self._helix_get(
            "channels/followers", {"broadcaster_id": broadcaster_id, "first": "1"}
        )
        if data is None:
            return None
        return data.get("total")

    async def get_channel_info(self, user_input: str) -> Optional[dict]:
        """Full resolve: accept URL/login, return id, login, display_name, follower_count."""
        user = await self.resolve_user(user_input)
        if user is None:
            return None

        followers = await self.get_follower_count(user["id"])
        if followers is None:
            return None

        return {
            "id": user["id"],
            "login": user["login"],
            "display_name": user["display_name"],
            "follower_count": followers,
        }
