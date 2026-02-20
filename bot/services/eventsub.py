"""
Twitch EventSub WebSocket client – optional real-time event notifications.

Connects to the Twitch EventSub WebSocket transport to receive live
notifications (e.g. channel updates) which trigger immediate count refreshes
instead of waiting for the polling interval.

NOTE: ``channel.follow`` (v2) requires a *user* access token with
``moderator:read:followers`` scope – this is NOT available with app-only
(client-credentials) auth.  Therefore the current implementation subscribes
to ``channel.update`` events and triggers a follower-count re-fetch when
the channel changes.  Full follower EventSub would require an OAuth2
authorization-code flow per broadcaster.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Callable, Coroutine, Any, Optional

import aiohttp

if TYPE_CHECKING:
    from bot.services.twitch import TwitchService

log = logging.getLogger(__name__)

WSS_URL = "wss://eventsub.wss.twitch.tv/ws"


class TwitchEventSub:
    """Manages a WebSocket connection to Twitch EventSub.

    Parameters
    ----------
    twitch_service:
        A ``TwitchService`` instance used to obtain tokens and make
        subscription API calls.
    on_channel_update:
        Async callback invoked with the broadcaster user-id when a
        ``channel.update`` notification is received.
    """

    def __init__(
        self,
        twitch_service: TwitchService,
        on_channel_update: Callable[[str], Coroutine[Any, Any, None]],
    ) -> None:
        self._twitch = twitch_service
        self._on_channel_update = on_channel_update
        self._session_id: Optional[str] = None
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._http: Optional[aiohttp.ClientSession] = None
        self._task: Optional[asyncio.Task[None]] = None
        self._subscribed_ids: set[str] = set()
        self._running = False
        self._keepalive_timeout: float = 30.0

    # ── lifecycle ────────────────────────────────────────────

    async def start(self) -> None:
        """Open the WebSocket and begin listening in the background."""
        if self._running:
            return
        self._running = True
        self._http = aiohttp.ClientSession()
        self._task = asyncio.create_task(self._run_forever(), name="eventsub-ws")
        log.info("Twitch EventSub WebSocket task started.")

    async def stop(self) -> None:
        """Gracefully shut down the WebSocket connection."""
        self._running = False
        if self._ws and not self._ws.closed:
            await self._ws.close()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self._http and not self._http.closed:
            await self._http.close()
        self._session_id = None
        self._subscribed_ids.clear()
        log.info("Twitch EventSub WebSocket stopped.")

    # ── subscription management ──────────────────────────────

    async def subscribe(self, broadcaster_id: str) -> bool:
        """Subscribe to ``channel.update`` events for a broadcaster.

        Returns True on success, False otherwise.
        """
        if broadcaster_id in self._subscribed_ids:
            return True

        if not self._session_id:
            log.warning("Cannot subscribe – no active EventSub session.")
            return False

        if not await self._twitch._ensure_token():
            return False

        headers = {
            "Client-ID": self._twitch.client_id,
            "Authorization": f"Bearer {self._twitch._access_token}",
            "Content-Type": "application/json",
        }
        body = {
            "type": "channel.update",
            "version": "2",
            "condition": {"broadcaster_user_id": broadcaster_id},
            "transport": {
                "method": "websocket",
                "session_id": self._session_id,
            },
        }

        try:
            assert self._http is not None
            async with self._http.post(
                "https://api.twitch.tv/helix/eventsub/subscriptions",
                headers=headers,
                json=body,
            ) as resp:
                if resp.status in (200, 202):
                    self._subscribed_ids.add(broadcaster_id)
                    log.info("Subscribed to channel.update for %s", broadcaster_id)
                    return True
                else:
                    text = await resp.text()
                    log.warning(
                        "EventSub subscribe failed (%s): %s", resp.status, text
                    )
                    return False
        except Exception:
            log.exception("Error subscribing to EventSub for %s", broadcaster_id)
            return False

    async def unsubscribe(self, broadcaster_id: str) -> None:
        """Remove a broadcaster from the tracked set (subscription cleanup
        happens automatically when the WebSocket session ends)."""
        self._subscribed_ids.discard(broadcaster_id)

    async def subscribe_all(self, broadcaster_ids: list[str]) -> None:
        """Bulk-subscribe a list of broadcaster IDs."""
        for bid in broadcaster_ids:
            await self.subscribe(bid)

    # ── internal WebSocket loop ──────────────────────────────

    async def _run_forever(self) -> None:
        """Reconnect loop – keeps the WebSocket alive."""
        backoff = 1.0
        while self._running:
            try:
                await self._connect_and_listen()
            except asyncio.CancelledError:
                return
            except Exception:
                log.exception("EventSub WebSocket error, reconnecting in %.0fs …", backoff)
            if self._running:
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60.0)

    async def _connect_and_listen(self) -> None:
        assert self._http is not None
        async with self._http.ws_connect(WSS_URL) as ws:
            self._ws = ws
            log.info("Connected to Twitch EventSub WebSocket.")
            backoff_reset = False

            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    msg_type = data.get("metadata", {}).get("message_type")

                    if msg_type == "session_welcome":
                        session = data["payload"]["session"]
                        self._session_id = session["session_id"]
                        self._keepalive_timeout = session.get(
                            "keepalive_timeout_seconds", 30
                        )
                        log.info(
                            "EventSub session %s (keepalive %ss)",
                            self._session_id,
                            self._keepalive_timeout,
                        )
                        # Re-subscribe previous IDs after reconnect
                        old_ids = list(self._subscribed_ids)
                        self._subscribed_ids.clear()
                        await self.subscribe_all(old_ids)
                        backoff_reset = True

                    elif msg_type == "session_keepalive":
                        pass  # Connection is alive

                    elif msg_type == "session_reconnect":
                        new_url = data["payload"]["session"]["reconnect_url"]
                        log.info("EventSub reconnect requested → %s", new_url)
                        # The server will close this WS; we reconnect via the loop
                        break

                    elif msg_type == "notification":
                        await self._handle_notification(data)

                    elif msg_type == "revocation":
                        sub = data["payload"]["subscription"]
                        log.warning(
                            "EventSub subscription revoked: %s (%s)",
                            sub["type"],
                            sub.get("status"),
                        )

                elif msg.type in (
                    aiohttp.WSMsgType.CLOSED,
                    aiohttp.WSMsgType.ERROR,
                ):
                    break

            self._ws = None
            self._session_id = None

    async def _handle_notification(self, data: dict) -> None:
        sub_type = data["payload"]["subscription"]["type"]
        event = data["payload"]["event"]

        if sub_type == "channel.update":
            broadcaster_id = event.get("broadcaster_user_id")
            if broadcaster_id:
                log.info(
                    "channel.update for %s – triggering refresh",
                    broadcaster_id,
                )
                try:
                    await self._on_channel_update(broadcaster_id)
                except Exception:
                    log.exception(
                        "Error in on_channel_update callback for %s",
                        broadcaster_id,
                    )
