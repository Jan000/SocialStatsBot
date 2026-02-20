"""
Async rate-limiter for API requests.

Uses a token-bucket algorithm with a sliding window so requests are spread
evenly and API quota limits are never exceeded.
"""

from __future__ import annotations

import asyncio
import logging
import time

log = logging.getLogger(__name__)


class RateLimiter:
    """Token-bucket rate limiter.

    Parameters
    ----------
    max_calls : int
        Maximum number of calls allowed within *period* seconds.
    period : float
        Length of the sliding window in seconds.
    """

    def __init__(self, max_calls: int, period: float) -> None:
        self.max_calls = max_calls
        self.period = period
        self._timestamps: list[float] = []
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Wait until a request slot is available, then consume one."""
        async with self._lock:
            now = time.monotonic()
            # Purge expired timestamps
            cutoff = now - self.period
            self._timestamps = [t for t in self._timestamps if t > cutoff]

            if len(self._timestamps) >= self.max_calls:
                # Wait until the oldest timestamp expires
                sleep_for = self._timestamps[0] - cutoff
                if sleep_for > 0:
                    log.debug(
                        "Rate-limit reached (%d/%d), sleeping %.2fs",
                        len(self._timestamps),
                        self.max_calls,
                        sleep_for,
                    )
                    await asyncio.sleep(sleep_for)
                # Re-purge after sleep
                now = time.monotonic()
                cutoff = now - self.period
                self._timestamps = [t for t in self._timestamps if t > cutoff]

            self._timestamps.append(time.monotonic())

    async def __aenter__(self) -> RateLimiter:
        await self.acquire()
        return self

    async def __aexit__(self, *exc) -> None:  # noqa: ANN002
        pass
