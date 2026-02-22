"""
Instagram service – fetch follower counts via public web scraping.

Primary method: scrape the profile page HTML ``<meta>`` tag (no cookies/auth needed).
Fallback: ``web_profile_info`` JSON API (needs CSRF token, often returns 401).

Prefers *curl_cffi* for browser-grade TLS fingerprinting (avoids 429s),
falls back to plain *aiohttp* when curl_cffi is not installed.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
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

# Number of retries on transient errors (non-429).
_MAX_RETRIES = 1

# Cooldown (seconds) after a 429 – applies globally (IP-level block).
_GLOBAL_429_COOLDOWN = 600  # 10 minutes
# Cooldown (seconds) after a non-429 failure for a specific username.
_PER_USER_COOLDOWN = 300  # 5 minutes

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
    """Fetches Instagram follower counts via public web scraping.

    **Primary method**: fetch the profile page HTML and parse the follower
    count from the ``<meta name="description">`` tag.  This works without
    any cookies, CSRF tokens, or authentication.

    **Fallback**: the ``web_profile_info`` JSON endpoint (needs CSRF token).

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
        # Per-username cooldown: {username: monotonic timestamp when cooldown expires}
        self._fail_cooldowns: dict[str, float] = {}
        # Global cooldown (IP-level 429 block): monotonic timestamp when it expires
        self._global_cooldown: float = 0.0

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

    def _is_on_cooldown(self, username: str) -> bool:
        """Return True if requests should be skipped (global or per-user)."""
        now = time.monotonic()
        # Global 429 cooldown takes precedence
        if now < self._global_cooldown:
            return True
        # Per-username cooldown
        expires = self._fail_cooldowns.get(username)
        if expires is None:
            return False
        if now < expires:
            return True
        # Cooldown expired – remove entry
        del self._fail_cooldowns[username]
        return False

    def _set_global_cooldown(self) -> None:
        """Activate global cooldown – Instagram is blocking our IP."""
        self._global_cooldown = time.monotonic() + _GLOBAL_429_COOLDOWN
        remaining = int(self._global_cooldown - time.monotonic())
        log.warning(
            "Instagram: IP rate-limited (429). All requests paused for %ds.",
            remaining,
        )

    def _set_cooldown(self, username: str) -> None:
        """Put *username* on cooldown so it isn't retried immediately."""
        self._fail_cooldowns[username] = time.monotonic() + _PER_USER_COOLDOWN
        log.info("Instagram: %s on cooldown for %ds", username, _PER_USER_COOLDOWN)

    async def close(self) -> None:
        if self._session is not None:
            if _HAS_CURL_CFFI:
                await self._session.close()
                self._session = None
            elif not self._session.closed:
                await self._session.close()
        self._warmed_up = False
        self._csrf_token = ""
        self._fail_cooldowns.clear()
        self._global_cooldown = 0.0

    def get_health(self) -> dict:
        """Return service health information."""
        now = time.monotonic()
        global_cd_remaining = max(0.0, self._global_cooldown - now)
        per_user_cd = sum(1 for t in self._fail_cooldowns.values() if t > now)
        return {
            "configured": True,
            "session_active": self._session is not None,
            "backend": "curl_cffi" if _HAS_CURL_CFFI else "aiohttp",
            "global_cooldown_active": now < self._global_cooldown,
            "global_cooldown_remaining": int(global_cd_remaining),
            "per_user_cooldown_count": per_user_cd,
        }

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

    # -- HTML scrape (primary method) ---------------------------------------

    async def _scrape_profile_html(self, session: Any, username: str) -> tuple[Optional[dict], bool]:
        """Fetch the profile page HTML and extract follower count from the
        ``<meta name="description">`` tag.

        Returns ``(result_dict | None, was_429)``.
        Instagram embeds a description like
        ``"103 Followers, 20 Following, 39 Posts - Display Name (@user) …"``
        in every public profile page.  This works without cookies or auth.
        """
        url = f"https://www.instagram.com/{username}/"
        try:
            if _HAS_CURL_CFFI:
                resp = await session.get(url)
                status, html = resp.status_code, resp.text
            else:
                async with session.get(url) as resp:
                    status, html = resp.status, await resp.text()

            if status == 429:
                log.warning("Instagram HTML scrape returned 429 for %s", username)
                return None, True

            if status != 200:
                log.warning("Instagram HTML scrape returned %s for %s", status, username)
                return None, False

            # Parse meta description
            meta_match = re.search(
                r'<meta\s+[^>]*?content="([^"]*?Follower[^"]*?)"', html, re.IGNORECASE
            )
            if not meta_match:
                log.warning("Instagram HTML: no meta description with follower count for %s", username)
                return None, False

            desc = meta_match.group(1)
            # "103 Followers, 20 Following, 39 Posts - Display Name (@user) …"
            follower_match = re.search(r"([\d,.\s]+)\s*Follower", desc)
            if not follower_match:
                log.warning("Instagram HTML: could not parse follower count from meta for %s", username)
                return None, False

            raw = follower_match.group(1).replace(",", "").replace(".", "").replace(" ", "").strip()
            follower_count = int(raw) if raw.isdigit() else 0

            # Try to extract display name from "… - Display Name (@user) …"
            name_match = re.search(r"-\s*(.+?)\s*\(@?" + re.escape(username) + r"\)", desc)
            display_name = name_match.group(1).strip() if name_match else username

            log.info(
                "Instagram HTML OK for %s: %d followers",
                username, follower_count,
            )
            return {
                "id": "",
                "username": username,
                "full_name": display_name,
                "follower_count": follower_count,
            }, False
        except Exception:
            log.exception("Instagram HTML scrape error for %s", username)
            return None, False

    # -- JSON API (fallback) ------------------------------------------------

    async def _fetch_api(self, session: Any, username: str) -> Optional[dict]:
        """Try the ``web_profile_info`` JSON endpoint (needs CSRF token).

        Returns user info dict or None on error.  Does NOT raise on
        rate-limit – callers decide how to handle that.
        """
        await self._warm_session(session)

        params = {"username": username}
        headers = {
            "X-IG-App-ID": "936619743392459",  # public web app ID
            "X-CSRFToken": self._csrf_token,
            "Referer": f"https://www.instagram.com/{username}/",
        }

        do_request = self._request_curl if _HAS_CURL_CFFI else self._request_aiohttp

        try:
            async with self._rate_limiter:
                status, data = await do_request(
                    session, _IG_WEB_PROFILE, params=params, headers=headers
                )
        except Exception:
            log.exception("Instagram API error for user %s", username)
            return None

        if status in (401, 429):
            log.warning("Instagram API returned %s for %s", status, username)
            return None
        if status != 200 or data is None:
            log.warning("Instagram API returned %s for user %s", status, username)
            return None

        user = data.get("data", {}).get("user")
        if not user:
            return None
        return {
            "id": user.get("id", ""),
            "username": user.get("username", username),
            "full_name": user.get("full_name", ""),
            "follower_count": user.get("edge_followed_by", {}).get("count", 0),
        }

    # -- public API ---------------------------------------------------------

    async def get_user_info(self, username: str) -> Optional[dict]:
        """Fetch basic profile info for a public Instagram user.

        Strategy:
        1. **HTML scrape** (primary) – single GET, no auth, very reliable.
        2. **JSON API** (fallback) – only if HTML scrape fails with a non-429
           status (i.e. the profile page rendered but parsing failed).

        Returns dict with id, username, full_name, follower_count
        or None on error.

        Raises :class:`PlatformRateLimitError` when both methods are
        rate-limited / blocked.
        """
        from bot.cogs import PlatformRateLimitError

        # If this username recently failed, skip to avoid hammering Instagram.
        if self._is_on_cooldown(username):
            log.debug("Instagram: %s still on cooldown, skipping", username)
            raise PlatformRateLimitError("instagram", username)

        session = await self._get_session()

        # --- Attempt 1: HTML scrape (with retry only on non-429 errors) ---
        got_429 = False
        for attempt in range(_MAX_RETRIES + 1):
            async with self._rate_limiter:
                result, was_429 = await self._scrape_profile_html(session, username)
            if result is not None:
                return result
            if was_429:
                # IP-level block – don't retry, activate global cooldown
                got_429 = True
                break
            # Non-429 failure (e.g. parse error) – retry once
            if attempt < _MAX_RETRIES:
                wait = 2 ** (attempt + 1)
                log.info("Instagram: HTML retry %d/%d for %s in %ds", attempt + 1, _MAX_RETRIES, username, wait)
                await asyncio.sleep(wait)

        # --- Attempt 2: JSON API (only if HTML did NOT get 429) ---
        if not got_429:
            log.info("Instagram: HTML scrape failed for %s, trying JSON API", username)
            async with self._rate_limiter:
                result = await self._fetch_api(session, username)
            if result is not None:
                return result

        # Both methods failed — set appropriate cooldown and raise.
        if got_429:
            self._set_global_cooldown()
        else:
            self._set_cooldown(username)
        raise PlatformRateLimitError("instagram", username)

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
