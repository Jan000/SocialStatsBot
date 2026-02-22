"""
Instagram service – fetch follower counts via public web API.

Uses the public web profile endpoint (no API key required).
Prefers *curl_cffi* for browser-grade TLS fingerprinting (avoids 429s),
falls back to plain *aiohttp* when curl_cffi is not installed.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Optional

from bot.ratelimit import RateLimiter

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional curl_cffi import – falls back to aiohttp
# ---------------------------------------------------------------------------
try:
    from curl_cffi.requests import AsyncSession as _CurlAsyncSession  # type: ignore[import-untyped]

    _HAS_CURL_CFFI = True
    log.info("curl_cffi available – using browser-impersonation for Instagram")
except ImportError:
    _HAS_CURL_CFFI = False
    import aiohttp

    log.info("curl_cffi not installed – falling back to aiohttp for Instagram")

# Public endpoint that returns profile data as JSON.
_IG_WEB_PROFILE = "https://www.instagram.com/api/v1/users/web_profile_info/"
_IG_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

# Browser version that curl_cffi will impersonate at the TLS level.
_CURL_IMPERSONATE = "chrome131"

# Conservative rate limit – Instagram is strict about scraping.
_DEFAULT_IG_MAX_CALLS = 2
_DEFAULT_IG_PERIOD = 5.0

# Number of retries on HTTP 429 (rate-limited) responses.
_MAX_429_RETRIES = 3

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
    """Fetches Instagram follower counts via the public web API.

    When *curl_cffi* is installed the service impersonates a real Chrome
    browser at the TLS-fingerprint level, which dramatically reduces the
    chance of Instagram returning 429 responses.  If curl_cffi is not
    available it falls back to plain *aiohttp*.
    """

    def __init__(
        self,
        *,
        max_calls: int = _DEFAULT_IG_MAX_CALLS,
        period: float = _DEFAULT_IG_PERIOD,
    ) -> None:
        self._session: Any = None  # curl_cffi AsyncSession | aiohttp.ClientSession
        self._rate_limiter = RateLimiter(max_calls, period)

    # -- session helpers ----------------------------------------------------

    async def _get_session(self) -> Any:
        if _HAS_CURL_CFFI:
            if self._session is None:
                self._session = _CurlAsyncSession(impersonate=_CURL_IMPERSONATE)
            return self._session
        # aiohttp fallback
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={"User-Agent": _IG_USER_AGENT}
            )
        return self._session

    async def close(self) -> None:
        if self._session is not None:
            if _HAS_CURL_CFFI:
                await self._session.close()
                self._session = None
            elif not self._session.closed:
                await self._session.close()

    # -- internal request wrappers ------------------------------------------

    async def _request_curl(
        self, session: Any, url: str, *, params: dict, headers: dict
    ) -> tuple[int, Optional[dict]]:
        """Perform a GET using curl_cffi and return (status, json|None)."""
        resp = await session.get(url, params=params, headers=headers)
        status: int = resp.status_code
        try:
            data: Optional[dict] = resp.json()
        except Exception:
            data = None
        return status, data

    async def _request_aiohttp(
        self, session: Any, url: str, *, params: dict, headers: dict
    ) -> tuple[int, Optional[dict]]:
        """Perform a GET using aiohttp and return (status, json|None)."""
        async with session.get(url, params=params, headers=headers) as resp:
            status: int = resp.status
            try:
                data: Optional[dict] = await resp.json()
            except Exception:
                data = None
            return status, data

    # -- public API ---------------------------------------------------------

    async def get_user_info(self, username: str) -> Optional[dict]:
        """Fetch basic profile info for a public Instagram user.

        Returns dict with id, username, full_name, follower_count
        or None on error.

        Raises :class:`PlatformRateLimitError` when the API keeps returning
        429 after all retry attempts.
        """
        from bot.cogs import PlatformRateLimitError

        session = await self._get_session()
        params = {"username": username}
        headers = {
            "X-IG-App-ID": "936619743392459",  # public web app ID
            "Referer": f"https://www.instagram.com/{username}/",
        }

        do_request = self._request_curl if _HAS_CURL_CFFI else self._request_aiohttp

        for attempt in range(_MAX_429_RETRIES + 1):
            try:
                async with self._rate_limiter:
                    status, data = await do_request(
                        session, _IG_WEB_PROFILE, params=params, headers=headers
                    )
                    if status == 429:
                        if attempt < _MAX_429_RETRIES:
                            wait = min(2 ** (attempt + 1), 30)
                            log.warning(
                                "Instagram 429 for %s – retry %d/%d in %ds",
                                username, attempt + 1, _MAX_429_RETRIES, wait,
                            )
                            await asyncio.sleep(wait)
                            continue
                        log.warning(
                            "Instagram 429 for %s – retries exhausted", username
                        )
                        raise PlatformRateLimitError("instagram", username)
                    if status != 200:
                        log.warning(
                            "Instagram API returned %s for user %s",
                            status, username,
                        )
                        return None
                    if data is None:
                        return None
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
            except PlatformRateLimitError:
                raise
            except Exception:
                log.exception("Instagram API error for user %s", username)
                return None
        return None  # pragma: no cover – loop always returns or raises

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
