"""
Schwab Level 2 Order Book Streamer

Async streaming service that subscribes to NYSE and NASDAQ order book data
via schwab-py's StreamClient. Caches latest L2BookSnapshot per symbol and
emits callbacks for downstream consumers (recorder, signals).

Usage:
    streamer = SchwabL2Streamer()
    await streamer.start()
    await streamer.subscribe(["AAPL", "TSLA"])
    # ... snapshots available via streamer.get_snapshot("AAPL")
    await streamer.stop()

Feature-gated behind L2_ENABLED config flag.
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set

from nexus2.domain.market_data.l2_types import (
    L2BookSnapshot,
    parse_schwab_book_message,
)

logger = logging.getLogger(__name__)


# Exchange lookup for routing symbols to NYSE vs NASDAQ book
# Common NASDAQ-listed stocks trade on NASDAQ; everything else uses NYSE
# This is a heuristic — most small-cap momentum stocks are NASDAQ-listed
NASDAQ_EXCHANGES = {"NASDAQ", "Q", "XNAS"}
NYSE_EXCHANGES = {"NYSE", "N", "XNYS", "ARCA", "BATS"}


class SchwabL2Streamer:
    """
    Async L2 order book streamer using schwab-py's StreamClient.
    
    Manages:
    - Token bridge between Nexus custom format and schwab-py expected format
    - WebSocket connection lifecycle (connect, login, reconnect)
    - NYSE and NASDAQ book subscriptions
    - Snapshot caching per symbol
    - Callback dispatch for updates
    """

    def __init__(
        self,
        max_symbols: int = 5,
        on_update: Optional[Callable[[L2BookSnapshot], None]] = None,
    ):
        self._max_symbols = max_symbols
        self._on_update = on_update

        # State
        self._client = None  # schwab-py async Client
        self._stream_client = None  # schwab-py StreamClient
        self._subscribed_symbols: Set[str] = set()
        self._snapshots: Dict[str, L2BookSnapshot] = {}
        self._connected = False
        self._running = False
        self._message_loop_task: Optional[asyncio.Task] = None
        self._reconnect_task: Optional[asyncio.Task] = None

        # Stats
        self._messages_received = 0
        self._last_message_time: Optional[float] = None
        self._connection_time: Optional[float] = None

    @property
    def is_connected(self) -> bool:
        """Whether the WebSocket stream is currently connected."""
        return self._connected

    @property
    def subscribed_symbols(self) -> Set[str]:
        """Currently subscribed symbols."""
        return self._subscribed_symbols.copy()

    @property
    def stats(self) -> dict:
        """Connection and message statistics."""
        return {
            "connected": self._connected,
            "subscribed_symbols": len(self._subscribed_symbols),
            "symbols": sorted(self._subscribed_symbols),
            "messages_received": self._messages_received,
            "last_message_time": self._last_message_time,
            "uptime_seconds": (
                time.time() - self._connection_time
                if self._connection_time
                else 0
            ),
        }

    def get_snapshot(self, symbol: str) -> Optional[L2BookSnapshot]:
        """Get the latest cached L2 snapshot for a symbol."""
        return self._snapshots.get(symbol)

    def get_all_snapshots(self) -> Dict[str, L2BookSnapshot]:
        """Get all cached L2 snapshots."""
        return dict(self._snapshots)

    # ---------------------------------------------------------------
    # Token Bridge
    # ---------------------------------------------------------------

    def _get_token_path(self) -> Path:
        """Get path to the Nexus schwab_tokens.json file."""
        return (
            Path(__file__).parent.parent.parent.parent / "data" / "schwab_tokens.json"
        )

    def _build_schwab_py_token(self) -> dict:
        """
        Read the Nexus custom token file and convert to schwab-py format.
        
        Nexus format: {access_token, refresh_token, expiry, refresh_token_obtained}
        schwab-py format: {creation_timestamp: int, token: {access_token, refresh_token, ...}}
        
        Maps Nexus fields into an authlib-compatible OAuth2 token dict.
        """
        token_path = self._get_token_path()
        if not token_path.exists():
            raise FileNotFoundError(
                f"Schwab token file not found: {token_path}. "
                "Run schwab_auth.py to authenticate first."
            )

        raw = json.loads(token_path.read_text())
        access_token = raw.get("access_token")
        refresh_token = raw.get("refresh_token")
        expiry_str = raw.get("expiry")
        rt_obtained_str = raw.get("refresh_token_obtained")

        if not access_token or not refresh_token:
            raise ValueError(
                "Schwab token file is missing access_token or refresh_token. "
                "Re-authenticate via schwab_auth.py"
            )

        # Parse the creation timestamp from refresh_token_obtained
        # This is used by schwab-py's TokenMetadata for token age tracking
        creation_ts = int(time.time())  # fallback to now
        if rt_obtained_str:
            try:
                dt = datetime.fromisoformat(rt_obtained_str)
                creation_ts = int(dt.timestamp())
            except (ValueError, TypeError):
                pass

        # Parse expiry to compute expires_in
        expires_in = 1800  # default 30 minutes
        if expiry_str:
            try:
                expiry_dt = datetime.fromisoformat(expiry_str)
                remaining = (expiry_dt.timestamp() - time.time())
                if remaining > 0:
                    expires_in = int(remaining)
            except (ValueError, TypeError):
                pass

        # Build authlib-compatible token dict
        token = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "Bearer",
            "expires_in": expires_in,
            "scope": "api",
            "expires_at": time.time() + expires_in,
        }

        # Diagnostic logging (mask tokens for security)
        at_masked = f"{access_token[:8]}...{access_token[-4:]}" if len(access_token) > 12 else "***"
        logger.info(
            "[L2] Token bridge: access=%s, expires_in=%ds, expiry_str=%s, creation_ts=%s",
            at_masked, expires_in, expiry_str, rt_obtained_str,
        )

        # schwab-py expects {creation_timestamp, token}
        return {
            "creation_timestamp": creation_ts,
            "token": token,
        }

    def _token_read_func(self) -> dict:
        """Token reader for schwab-py client_from_access_functions."""
        return self._build_schwab_py_token()

    def _token_write_func(self, token: dict, *args, **kwargs) -> None:
        """
        Token writer for schwab-py client_from_access_functions.
        
        When schwab-py refreshes the token, write it back in Nexus format
        so the REST adapter (schwab_adapter.py) can also use it.
        """
        try:
            # token may already be wrapped by schwab-py's TokenMetadata
            if "token" in token and "creation_timestamp" in token:
                inner = token["token"]
            else:
                inner = token

            access_token = inner.get("access_token")
            refresh_token = inner.get("refresh_token")
            expires_in = inner.get("expires_in", 1800)

            if not access_token:
                logger.warning("[L2] Token write called with empty access_token, skipping")
                return

            from nexus2.utils.time_utils import now_et
            now = now_et()
            from datetime import timedelta
            expiry = now + timedelta(seconds=expires_in)

            # Write in Nexus format
            nexus_data = {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "expiry": expiry.isoformat(),
            }

            # Preserve refresh_token_obtained from existing file if available
            token_path = self._get_token_path()
            if token_path.exists():
                try:
                    existing = json.loads(token_path.read_text())
                    rt_obtained = existing.get("refresh_token_obtained")
                    if rt_obtained:
                        nexus_data["refresh_token_obtained"] = rt_obtained
                except Exception:
                    pass

            token_path.parent.mkdir(parents=True, exist_ok=True)
            token_path.write_text(json.dumps(nexus_data, indent=2))
            logger.info("[L2] Token refreshed and written to %s", token_path)

        except Exception as e:
            logger.error("[L2] Failed to write refreshed token: %s", e)

    # ---------------------------------------------------------------
    # Connection Lifecycle
    # ---------------------------------------------------------------

    async def _create_client(self):
        """Create schwab-py async client using token bridge."""
        import schwab.auth

        from nexus2 import config as app_config

        client_id = app_config.SCHWAB_CLIENT_ID
        client_secret = app_config.SCHWAB_CLIENT_SECRET

        if not client_id or not client_secret:
            raise ValueError(
                "SCHWAB_CLIENT_ID and SCHWAB_CLIENT_SECRET must be set in .env"
            )

        self._client = schwab.auth.client_from_access_functions(
            api_key=client_id,
            app_secret=client_secret,
            token_read_func=self._token_read_func,
            token_write_func=self._token_write_func,
            asyncio=True,
            enforce_enums=False,
        )

        logger.info("[L2] Created schwab-py async client")

        # Pre-flight: verify token works before attempting stream setup
        await self._preflight_check()

    async def _preflight_check(self):
        """
        Verify the token by making a lightweight API call.

        If the token is invalid (401), we let authlib's built-in refresh
        handle it. If that also fails, we raise immediately rather than
        waiting for the streaming login to fail with an opaque error.
        """
        import httpx

        try:
            resp = await self._client.get_account_numbers()
            if resp.status_code == httpx.codes.OK:
                logger.info("[L2] Pre-flight token check passed")
                return

            logger.warning(
                "[L2] Pre-flight check returned status %d, "
                "attempting to proceed anyway",
                resp.status_code,
            )
        except Exception as e:
            # 401 here means the token is genuinely invalid.
            # authlib's ensure_active_token should have tried a refresh.
            # If we're still failing, the refresh token may also be bad.
            logger.error(
                "[L2] Pre-flight token check failed: %s. "
                "This likely means the access token is invalid and "
                "auto-refresh also failed. Re-authenticate via schwab_auth.py",
                e,
            )
            raise

    async def _create_stream_client(self):
        """Create StreamClient and login to WebSocket."""
        from schwab.streaming import StreamClient

        self._stream_client = StreamClient(self._client, enforce_enums=False)

        # Register book handlers
        self._stream_client.add_nasdaq_book_handler(self._handle_book_message)
        self._stream_client.add_nyse_book_handler(self._handle_book_message)

        # Login performs WS connect + auth
        await self._stream_client.login()

        self._connected = True
        self._connection_time = time.time()
        logger.info("[L2] StreamClient connected and logged in")

    async def start(self):
        """
        Start the L2 streamer: create client, connect, start message loop.

        Includes retry logic: if the first attempt fails with a 401
        (likely stale token), we tear down, re-read tokens, and retry once.

        Call subscribe() after start() to begin receiving L2 data.
        """
        if self._running:
            logger.warning("[L2] Streamer already running")
            return

        self._running = True
        last_error = None

        for attempt in range(1, 3):  # max 2 attempts
            try:
                await self._create_client()
                await self._create_stream_client()

                # Start the message processing loop
                self._message_loop_task = asyncio.create_task(
                    self._message_loop(), name="l2_message_loop"
                )
                logger.info("[L2] Streamer started successfully (attempt %d)", attempt)
                return  # success

            except Exception as e:
                last_error = e
                err_str = str(e)
                is_auth_error = "401" in err_str or "Unauthorized" in err_str

                if attempt == 1 and is_auth_error:
                    logger.warning(
                        "[L2] Attempt %d failed with auth error: %s. "
                        "Retrying with fresh token...",
                        attempt, e,
                    )
                    # Clean up for retry
                    self._client = None
                    self._stream_client = None
                    await asyncio.sleep(1)  # brief pause before retry
                    continue
                else:
                    break

        # All attempts exhausted
        self._running = False
        self._connected = False
        logger.error("[L2] Failed to start streamer: %s", last_error, exc_info=True)
        raise last_error

    async def stop(self):
        """Stop the L2 streamer and clean up resources."""
        self._running = False

        # Cancel message loop
        if self._message_loop_task and not self._message_loop_task.done():
            self._message_loop_task.cancel()
            try:
                await self._message_loop_task
            except asyncio.CancelledError:
                pass

        # Cancel reconnect task if running
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass

        # Logout gracefully
        if self._stream_client and self._connected:
            try:
                await self._stream_client.logout()
            except Exception as e:
                logger.debug("[L2] Error during logout: %s", e)

        self._connected = False
        self._stream_client = None
        self._client = None
        self._subscribed_symbols.clear()
        self._snapshots.clear()
        logger.info("[L2] Streamer stopped")

    # ---------------------------------------------------------------
    # Subscriptions
    # ---------------------------------------------------------------

    async def subscribe(self, symbols: List[str]):
        """
        Subscribe to L2 book data for the given symbols.
        
        Subscribes to both NYSE and NASDAQ books for each symbol since
        we don't reliably know the listing exchange at subscription time.
        The streams will simply not produce data for the wrong exchange.
        
        Args:
            symbols: List of equity ticker symbols (e.g., ["AAPL", "TSLA"])
        """
        if not self._connected:
            logger.warning("[L2] Cannot subscribe — not connected")
            return

        # Enforce max symbol limit
        new_symbols = [s.upper() for s in symbols if s.upper() not in self._subscribed_symbols]
        available_slots = self._max_symbols - len(self._subscribed_symbols)

        if available_slots <= 0:
            logger.warning(
                "[L2] At max symbol limit (%d). Unsubscribe before adding more.",
                self._max_symbols,
            )
            return

        symbols_to_add = new_symbols[:available_slots]
        if not symbols_to_add:
            return

        if len(new_symbols) > available_slots:
            logger.warning(
                "[L2] Requested %d symbols but only %d slots available. "
                "Subscribing to: %s",
                len(new_symbols), available_slots, symbols_to_add,
            )

        try:
            # Subscribe to both exchanges — the service silently ignores 
            # symbols not on that exchange
            if not self._subscribed_symbols:
                # First subscription uses SUBS command
                await self._stream_client.nasdaq_book_subs(symbols_to_add)
                await self._stream_client.nyse_book_subs(symbols_to_add)
            else:
                # Subsequent subscriptions use ADD command
                await self._stream_client.nasdaq_book_add(symbols_to_add)
                await self._stream_client.nyse_book_add(symbols_to_add)

            self._subscribed_symbols.update(symbols_to_add)
            logger.info(
                "[L2] Subscribed to %d symbols: %s (total: %d)",
                len(symbols_to_add), symbols_to_add, len(self._subscribed_symbols),
            )

        except Exception as e:
            logger.error(
                "[L2] Failed to subscribe to %s: %s",
                symbols_to_add, e, exc_info=True,
            )

    async def unsubscribe(self, symbols: List[str]):
        """Unsubscribe from L2 book data for the given symbols."""
        if not self._connected:
            return

        symbols_to_remove = [
            s.upper() for s in symbols if s.upper() in self._subscribed_symbols
        ]
        if not symbols_to_remove:
            return

        try:
            await self._stream_client.nasdaq_book_unsubs(symbols_to_remove)
            await self._stream_client.nyse_book_unsubs(symbols_to_remove)

            for s in symbols_to_remove:
                self._subscribed_symbols.discard(s)
                self._snapshots.pop(s, None)

            logger.info(
                "[L2] Unsubscribed from %d symbols: %s (remaining: %d)",
                len(symbols_to_remove), symbols_to_remove, len(self._subscribed_symbols),
            )

        except Exception as e:
            logger.error("[L2] Failed to unsubscribe: %s", e, exc_info=True)

    async def update_subscriptions(self, new_symbols: List[str]):
        """
        Replace current subscriptions with a new set of symbols.
        
        Efficiently computes the diff and only subscribes/unsubscribes as needed.
        """
        new_set = {s.upper() for s in new_symbols}
        current = self._subscribed_symbols

        to_remove = current - new_set
        to_add = new_set - current

        if to_remove:
            await self.unsubscribe(list(to_remove))
        if to_add:
            await self.subscribe(list(to_add))

    # ---------------------------------------------------------------
    # Message Handling
    # ---------------------------------------------------------------

    async def _message_loop(self):
        """
        Main async loop that processes incoming WebSocket messages.
        
        schwab-py's handle_message() reads one message from the WebSocket,
        dispatches it to the appropriate handler, and returns.
        """
        logger.info("[L2] Message loop started")
        consecutive_errors = 0
        max_consecutive_errors = 10

        while self._running:
            try:
                await self._stream_client.handle_message()
                consecutive_errors = 0  # Reset on success

            except asyncio.CancelledError:
                logger.info("[L2] Message loop cancelled")
                break

            except Exception as e:
                consecutive_errors += 1
                logger.warning(
                    "[L2] Message loop error (%d/%d): %s",
                    consecutive_errors, max_consecutive_errors, e,
                )

                if consecutive_errors >= max_consecutive_errors:
                    logger.error(
                        "[L2] Too many consecutive errors, scheduling reconnect"
                    )
                    self._connected = False
                    if self._running:
                        self._reconnect_task = asyncio.create_task(
                            self._reconnect(), name="l2_reconnect"
                        )
                    break

                await asyncio.sleep(0.5)

        logger.info("[L2] Message loop ended")

    def _handle_book_message(self, msg: dict):
        """
        Handler for both NYSE and NASDAQ book updates.
        
        Registered with StreamClient via add_*_book_handler().
        Parses the message, caches the snapshot, and dispatches to callbacks.
        """
        try:
            result = parse_schwab_book_message(msg)

            if result is None:
                return

            # Handle single snapshot or list
            snapshots = result if isinstance(result, list) else [result]

            for snapshot in snapshots:
                self._snapshots[snapshot.symbol] = snapshot
                self._messages_received += 1
                self._last_message_time = time.time()

                # Dispatch to callback
                if self._on_update:
                    try:
                        self._on_update(snapshot)
                    except Exception as cb_err:
                        logger.debug(
                            "[L2] Callback error for %s: %s",
                            snapshot.symbol, cb_err,
                        )

        except Exception as e:
            logger.debug("[L2] Failed to parse book message: %s", e)

    # ---------------------------------------------------------------
    # Reconnection
    # ---------------------------------------------------------------

    async def _reconnect(self):
        """Attempt to reconnect the stream after a failure."""
        backoff = 5
        max_backoff = 120
        max_attempts = 10

        for attempt in range(1, max_attempts + 1):
            if not self._running:
                return

            logger.info(
                "[L2] Reconnect attempt %d/%d (backoff: %ds)",
                attempt, max_attempts, backoff,
            )

            await asyncio.sleep(backoff)

            try:
                # Clean up old connection
                self._stream_client = None
                self._client = None

                # Re-create everything
                await self._create_client()
                await self._create_stream_client()

                # Re-subscribe to previously subscribed symbols
                saved_symbols = list(self._subscribed_symbols)
                self._subscribed_symbols.clear()

                if saved_symbols:
                    await self.subscribe(saved_symbols)

                # Restart message loop
                self._message_loop_task = asyncio.create_task(
                    self._message_loop(), name="l2_message_loop"
                )

                logger.info("[L2] Reconnected successfully on attempt %d", attempt)
                return

            except Exception as e:
                logger.warning(
                    "[L2] Reconnect attempt %d failed: %s", attempt, e
                )
                backoff = min(backoff * 2, max_backoff)

        logger.error("[L2] All reconnect attempts exhausted. L2 streaming offline.")
        self._running = False
        self._connected = False
