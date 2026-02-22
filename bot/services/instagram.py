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
    r"(?:https?://)?(?:[\w-]+\.)*instagram\.com/([\w.]+)/?", re.IGNORECASE
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
        self._warmed_up: bool = False  # True after initial page visit
        self._csrf_token: str = ""  # csrftoken cookie value

    # -- session helpers ----------------------------------------------------

    async def _get_session(self) -> Any:
        if _HAS_CURL_CFFI:
            if self._session is None:
                self._session = _CurlAsyncSession(impersonate=_CURL_IMPERSONATE)
                log.info("Instagram: using curl_cffi (impersonate=%s)", _CURL_IMPERSONATE)
            return self._session
        # aiohttp fallback
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={"User-Agent": _IG_USER_AGENT}
            )
            log.info("Instagram: using aiohttp fallback (curl_cffi not available)")
        return self._session

    async def _warm_session(self, session: Any) -> None:
        """Visit the Instagram homepage once to acquire session cookies.

        Instagram gates its ``web_profile_info`` API behind a valid
        ``csrftoken`` cookie **and** a matching ``X-CSRFToken`` header.
        Without them the endpoint returns 401.
        """
        if self._warmed_up:
            return
        try:
            if _HAS_CURL_CFFI:
                resp = await session.get("https://www.instagram.com/")
                status = resp.status_code
                cookies = dict(session.cookies)
            else:
                async with session.get("https://www.instagram.com/") as resp:
                    status = resp.status
                    # aiohttp stores cookies on the session's cookie_jar
                    cookies = {c.key: c.value for c in session.cookie_jar}
            self._csrf_token = cookies.get("csrftoken", "")
            log.info(
                "Instagram session warm-up: status %s, csrftoken=%s",
                status,
                "present" if self._csrf_token else "MISSING",
            )
        except Exception:
            log.warning("Instagram session warm-up failed", exc_info=True)
        # Mark as done regardless – we don't want to retry every call.
        self._warmed_up = True

    async def close(self) -> None:
        if self._session is not None:
            if _HAS_CURL_CFFI:
                await self._session.close()
                self._session = None
            elif not self._session.closed:
                await self._session.close()
        self._warmed_up = False
        self._csrf_token = ""

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

    # -- HTML meta-tag fallback ---------------------------------------------

    async def _scrape_profile_html(self, session: Any, username: str) -> Optional[dict]:
        """Fallback: fetch the profile page HTML and extract follower count
        from the ``<meta name="description">`` tag.

        Instagram embeds a description like
        ``"103 Followers, 20 Following, 39 Posts - Display Name (@user) …"``
        in every public profile page.
        """
        url = f"https://www.instagram.com/{username}/"
        try:
            if _HAS_CURL_CFFI:
                resp = await session.get(url)
                status, html = resp.status_code, resp.text
            else:
                async with session.get(url) as resp:
                    status, html = resp.status, await resp.text()

            if status != 200:
                log.warning("Instagram HTML scrape returned %s for %s", status, username)
                return None

            # Parse meta description
            meta_match = re.search(
                r'<meta\s+[^>]*?content="([^"]*?Follower[^"]*?)"', html, re.IGNORECASE
            )
            if not meta_match:
                log.warning("Instagram HTML: no meta description with follower count for %s", username)
                return None

            desc = meta_match.group(1)
            # "103 Followers, 20 Following, 39 Posts - Display Name (@user) …"
            follower_match = re.search(r"([\d,.\s]+)\s*Follower", desc)
            if not follower_match:
                log.warning("Instagram HTML: could not parse follower count from meta for %s", username)
                return None

            raw = follower_match.group(1).replace(",", "").replace(".", "").replace(" ", "").strip()
            follower_count = int(raw) if raw.isdigit() else 0

            # Try to extract display name from "… - Display Name (@user) …"
            name_match = re.search(r"-\s*(.+?)\s*\(@?" + re.escape(username) + r"\)", desc)
            display_name = name_match.group(1).strip() if name_match else username

            log.info(
                "Instagram HTML fallback OK for %s: %d followers",
                username, follower_count,
            )
            return {
                "id": "",
                "username": username,
                "full_name": display_name,
                "follower_count": follower_count,
            }
        except Exception:
            log.exception("Instagram HTML scrape error for %s", username)
            return None

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
        await self._warm_session(session)

        params = {"username": username}
        headers = {
            "X-IG-App-ID": "936619743392459",  # public web app ID
            "X-CSRFToken": self._csrf_token,
            "Referer": f"https://www.instagram.com/{username}/",
        }

        do_request = self._request_curl if _HAS_CURL_CFFI else self._request_aiohttp

        for attempt in range(_MAX_429_RETRIES + 1):
            try:
                async with self._rate_limiter:
                    status, data = await do_request(
                        session, _IG_WEB_PROFILE, params=params, headers=headers
                    )
                    if status in (401, 429):
                        if attempt < _MAX_429_RETRIES:
                            wait = min(2 ** (attempt + 1), 30)
                            log.warning(
                                "Instagram %s for %s – retry %d/%d in %ds",
                                status, username, attempt + 1, _MAX_429_RETRIES, wait,
                            )
                            # Re-warm the session to refresh cookies/CSRF token
                            self._warmed_up = False
                            await self._warm_session(session)
                            headers["X-CSRFToken"] = self._csrf_token
                            await asyncio.sleep(wait)
                            continue
                        log.warning(
                            "Instagram %s for %s – API retries exhausted, trying HTML fallback",
                            status, username,
                        )
                        # Last resort: scrape the profile page HTML
                        result = await self._scrape_profile_html(session, username)
                        if result is not None:
                            return result
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
