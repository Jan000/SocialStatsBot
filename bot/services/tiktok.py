"""
TikTok service – fetch follower counts via public web API.

Uses a public endpoint that does not require API keys.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Optional

import aiohttp

from bot.ratelimit import RateLimiter

log = logging.getLogger(__name__)

_TT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

# Conservative rate limit for TikTok.
_DEFAULT_TT_MAX_CALLS = 2
_DEFAULT_TT_PERIOD = 5.0

# Number of retries on HTTP 429 (rate-limited) responses.
_MAX_429_RETRIES = 3

# Patterns for parsing TikTok input
_TT_URL_RE = re.compile(
    r"(?:https?://)?(?:[\w-]+\.)*tiktok\.com/@([\w.]+)/?", re.IGNORECASE
)
_TT_RAW_LOGIN_RE = re.compile(r"^@?([\w.]{1,24})$")


def parse_tiktok_input(value: str) -> str:
    """Parse a TikTok input and return the username.

    Accepts:
      - https://www.tiktok.com/@niruki  -> 'niruki'
      - tiktok.com/@niruki              -> 'niruki'
      - @niruki                         -> 'niruki'
      - niruki                          -> 'niruki'
    """
    value = value.strip()
    m = _TT_URL_RE.match(value)
    if m:
        return m.group(1).lower()
    m = _TT_RAW_LOGIN_RE.match(value)
    if m:
        return m.group(1).lower()
    return value.lower()


class TikTokService:
    """Fetches TikTok follower counts via a public web endpoint."""

    def __init__(
        self,
        *,
        max_calls: int = _DEFAULT_TT_MAX_CALLS,
        period: float = _DEFAULT_TT_PERIOD,
    ) -> None:
        self._session: Optional[aiohttp.ClientSession] = None
        self._rate_limiter = RateLimiter(max_calls, period)

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={"User-Agent": _TT_USER_AGENT}
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    def get_health(self) -> dict:
        """Return service health information."""
        return {
            "configured": True,
            "session_active": self._session is not None and not self._session.closed,
        }

    async def get_user_info(self, username: str) -> Optional[dict]:
        """Fetch basic profile info for a public TikTok user.

        Returns dict with id, username, nickname, follower_count
        or None on error.

        Raises :class:`PlatformRateLimitError` when the API keeps returning
        429 after all retry attempts.
        """
        from bot.cogs import PlatformRateLimitError

        session = await self._get_session()
        # TikTok embeds user data in the SSR __UNIVERSAL_DATA_FOR_REHYDRATION__
        # on the profile page.  We fetch it with accept: text/html and parse.
        url = f"https://www.tiktok.com/@{username}"
        for attempt in range(_MAX_429_RETRIES + 1):
            try:
                async with self._rate_limiter:
                    async with session.get(
                        url,
                        headers={"Accept": "text/html"},
                        allow_redirects=True,
                    ) as resp:
                        if resp.status == 429:
                            if attempt < _MAX_429_RETRIES:
                                wait = min(2 ** (attempt + 1), 30)
                                log.warning(
                                    "TikTok 429 for %s \u2013 retry %d/%d in %ds",
                                    username, attempt + 1, _MAX_429_RETRIES, wait,
                                )
                                await asyncio.sleep(wait)
                                continue
                            log.warning(
                                "TikTok 429 for %s \u2013 retries exhausted", username
                            )
                            raise PlatformRateLimitError("tiktok", username)
                        if resp.status != 200:
                            log.warning(
                                "TikTok returned %s for user %s",
                                resp.status, username,
                            )
                            return None
                        html = await resp.text()
                        return self._parse_profile(html, username)
            except PlatformRateLimitError:
                raise
            except Exception:
                log.exception("TikTok error for user %s", username)
                return None
        return None  # pragma: no cover \u2013 loop always returns or raises

    # Match both SIGI_STATE and UNIVERSAL_DATA hydration scripts
    _JSON_RE = re.compile(
        r'<script[^>]*id="(?:SIGI_STATE|__UNIVERSAL_DATA_FOR_REHYDRATION__)"[^>]*>'
        r"(.*?)</script>",
        re.DOTALL,
    )

    def _parse_profile(self, html: str, username: str) -> Optional[dict]:
        """Extract user data from TikTok's SSR HTML."""
        import json

        m = self._JSON_RE.search(html)
        if not m:
            log.warning("TikTok: could not find hydration data for %s", username)
            return None

        try:
            blob = json.loads(m.group(1))
        except (json.JSONDecodeError, ValueError):
            log.warning("TikTok: could not parse JSON for %s", username)
            return None

        # Navigate various known data-shapes
        user_info = None
        stats = None

        # Shape 1: __DEFAULT_SCOPE__ → webapp.user-detail
        default_scope = blob.get("__DEFAULT_SCOPE__", {})
        detail = default_scope.get("webapp.user-detail", {})
        if detail:
            user_info = detail.get("userInfo", {}).get("user")
            stats = detail.get("userInfo", {}).get("stats")

        # Shape 2: UserModule
        if not user_info:
            users = blob.get("UserModule", {}).get("users", {})
            if username in users:
                user_info = users[username]
            stats_all = blob.get("UserModule", {}).get("stats", {})
            if username in stats_all:
                stats = stats_all[username]

        if not user_info:
            log.warning("TikTok: user data not found for %s", username)
            return None

        return {
            "id": str(user_info.get("id", "")),
            "username": user_info.get("uniqueId", username),
            "nickname": user_info.get("nickname", username),
            "follower_count": (stats or {}).get("followerCount", 0),
        }

    async def get_follower_count(self, username: str) -> Optional[int]:
        """Return the follower count for a TikTok username."""
        info = await self.get_user_info(username)
        return info["follower_count"] if info else None

    async def resolve_user(self, user_input: str) -> Optional[dict]:
        """Resolve a TikTok user from flexible input (URL, @handle, username)."""
        username = parse_tiktok_input(user_input)
        return await self.get_user_info(username)

    async def get_channel_info(self, user_input: str) -> Optional[dict]:
        """Full resolve: accept URL/username, return standardised info dict.

        Returns dict with id, display_name, follower_count, or None.
        """
        info = await self.resolve_user(user_input)
        if info is None:
            return None
        return {
            "id": info["username"],  # TikTok uses username as stable ID
            "display_name": info["nickname"] or info["username"],
            "follower_count": info["follower_count"],
        }
