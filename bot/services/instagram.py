"""
Instagram service – fetch follower counts via public web API.

Uses the public web profile endpoint (no API key required).
"""

from __future__ import annotations

import logging
import re
from typing import Optional

import aiohttp

from bot.ratelimit import RateLimiter

log = logging.getLogger(__name__)

# Public endpoint that returns profile data as JSON.
_IG_WEB_PROFILE = "https://www.instagram.com/api/v1/users/web_profile_info/"
_IG_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# Conservative rate limit – Instagram is strict about scraping.
_DEFAULT_IG_MAX_CALLS = 2
_DEFAULT_IG_PERIOD = 5.0

# Patterns for parsing Instagram input
_IG_URL_RE = re.compile(
    r"(?:https?://)?(?:www\.)?instagram\.com/([\w.]+)/?", re.IGNORECASE
)
_IG_RAW_LOGIN_RE = re.compile(r"^@?([\w.]{1,30})$")


def parse_instagram_input(value: str) -> str:
    """Parse an Instagram input and return the username.

    Accepts:
      - https://www.instagram.com/niruki  -> 'niruki'
      - instagram.com/niruki              -> 'niruki'
      - @niruki                           -> 'niruki'
      - niruki                            -> 'niruki'
    """
    value = value.strip()
    m = _IG_URL_RE.match(value)
    if m:
        return m.group(1).lower()
    m = _IG_RAW_LOGIN_RE.match(value)
    if m:
        return m.group(1).lower()
    return value.lower()


class InstagramService:
    """Fetches Instagram follower counts via the public web API."""

    def __init__(
        self,
        *,
        max_calls: int = _DEFAULT_IG_MAX_CALLS,
        period: float = _DEFAULT_IG_PERIOD,
    ) -> None:
        self._session: Optional[aiohttp.ClientSession] = None
        self._rate_limiter = RateLimiter(max_calls, period)

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={"User-Agent": _IG_USER_AGENT}
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def get_user_info(self, username: str) -> Optional[dict]:
        """Fetch basic profile info for a public Instagram user.

        Returns dict with id, username, full_name, follower_count
        or None on error.
        """
        session = await self._get_session()
        params = {"username": username}
        headers = {
            "X-IG-App-ID": "936619743392459",  # public web app ID
            "Referer": f"https://www.instagram.com/{username}/",
        }
        try:
            async with self._rate_limiter:
                async with session.get(
                    _IG_WEB_PROFILE, params=params, headers=headers
                ) as resp:
                    if resp.status != 200:
                        log.warning(
                            "Instagram API returned %s for user %s",
                            resp.status, username,
                        )
                        return None
                    data = await resp.json()
                    user = data.get("data", {}).get("user")
                    if not user:
                        return None
                    return {
                        "id": user.get("id", ""),
                        "username": user.get("username", username),
                        "full_name": user.get("full_name", ""),
                        "follower_count": user.get("edge_followed_by", {}).get(
                            "count", 0
                        ),
                    }
        except Exception:
            log.exception("Instagram API error for user %s", username)
            return None

    async def get_follower_count(self, username: str) -> Optional[int]:
        """Return the follower count for an Instagram username."""
        info = await self.get_user_info(username)
        return info["follower_count"] if info else None

    async def resolve_user(self, user_input: str) -> Optional[dict]:
        """Resolve an Instagram user from flexible input (URL, @handle, username).

        Returns dict with id, username, full_name, follower_count, or None.
        """
        username = parse_instagram_input(user_input)
        return await self.get_user_info(username)

    async def get_channel_info(self, user_input: str) -> Optional[dict]:
        """Full resolve: accept URL/username, return standardised info dict.

        Returns dict with id, display_name, follower_count, or None.
        """
        info = await self.resolve_user(user_input)
        if info is None:
            return None
        return {
            "id": info["username"],  # Instagram uses username as stable ID
            "display_name": info["full_name"] or info["username"],
            "follower_count": info["follower_count"],
        }
