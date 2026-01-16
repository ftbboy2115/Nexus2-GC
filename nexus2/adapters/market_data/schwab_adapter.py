"""
Schwab Market Data Adapter

Provides real-time bid/ask quotes via Schwab API.
Uses OAuth 2.0 for authentication.

Usage:
    from nexus2.adapters.market_data.schwab_adapter import get_schwab_adapter
    schwab = get_schwab_adapter()
    quote = schwab.get_quote("EVTV")
    print(f"Bid: {quote['bid']}, Ask: {quote['ask']}")
"""

import base64
import json
import logging
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any
from urllib.parse import urlencode, unquote

import httpx

from nexus2 import config as app_config
from nexus2.utils.time_utils import now_et

logger = logging.getLogger(__name__)

# Schwab API endpoints
SCHWAB_AUTH_URL = "https://api.schwabapi.com/v1/oauth/authorize"
SCHWAB_TOKEN_URL = "https://api.schwabapi.com/v1/oauth/token"
SCHWAB_QUOTES_URL = "https://api.schwabapi.com/marketdata/v1/quotes"


class SchwabAdapter:
    """
    Schwab Market Data API adapter for bid/ask quotes.
    
    OAuth 2.0 flow:
    1. First use: Call authenticate() to open browser for login
    2. After login: Callback receives auth code, exchanges for tokens
    3. Access token (30 min) auto-refreshes using refresh token (7 days)
    """
    
    def __init__(self):
        self.client_id = app_config.SCHWAB_CLIENT_ID
        self.client_secret = app_config.SCHWAB_CLIENT_SECRET
        self.callback_url = "https://127.0.0.1:8443/callback"
        
        # Token storage
        self._token_file = Path(__file__).parent.parent.parent.parent / "data" / "schwab_tokens.json"
        self._access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._token_expiry: Optional[datetime] = None
        
        # HTTP client
        self._client = httpx.Client(timeout=10.0)
        
        # Load existing tokens
        self._load_tokens()
    
    def _load_tokens(self):
        """Load tokens from disk."""
        from zoneinfo import ZoneInfo
        try:
            if self._token_file.exists():
                data = json.loads(self._token_file.read_text())
                self._access_token = data.get("access_token")
                self._refresh_token = data.get("refresh_token")
                expiry = data.get("expiry")
                if expiry:
                    self._token_expiry = datetime.fromisoformat(expiry)
                    # Ensure timezone-aware for comparison with now_et()
                    if self._token_expiry.tzinfo is None:
                        self._token_expiry = self._token_expiry.replace(tzinfo=ZoneInfo("America/New_York"))
                logger.info("[Schwab] Loaded tokens from disk")
        except Exception as e:
            logger.warning(f"[Schwab] Failed to load tokens: {e}")
    
    def _save_tokens(self):
        """Save tokens to disk."""
        try:
            self._token_file.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "access_token": self._access_token,
                "refresh_token": self._refresh_token,
                "expiry": self._token_expiry.isoformat() if self._token_expiry else None,
            }
            self._token_file.write_text(json.dumps(data, indent=2))
            logger.debug("[Schwab] Saved tokens to disk")
        except Exception as e:
            logger.warning(f"[Schwab] Failed to save tokens: {e}")
    
    def is_authenticated(self) -> bool:
        """Check if we have valid tokens."""
        if not self._access_token:
            return False
        if self._token_expiry and now_et() >= self._token_expiry:
            # Token expired, try to refresh
            return self._refresh_access_token()
        return True
    
    def get_auth_url(self) -> str:
        """Get OAuth authorization URL for user login."""
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.callback_url,
            "scope": "api",
        }
        return f"{SCHWAB_AUTH_URL}?{urlencode(params)}"
    
    def authenticate(self):
        """Start OAuth flow by opening browser."""
        if not self.client_id or not self.client_secret:
            logger.error("[Schwab] Missing CLIENT_ID or CLIENT_SECRET in config")
            return False
        
        auth_url = self.get_auth_url()
        logger.info(f"[Schwab] Opening browser for authentication...")
        logger.info(f"[Schwab] URL: {auth_url}")
        webbrowser.open(auth_url)
        return True
    
    def exchange_code_for_tokens(self, auth_code: str) -> bool:
        """Exchange authorization code for access/refresh tokens."""
        try:
            # URL-decode the code (may contain %40 etc from URL)
            auth_code = unquote(auth_code)
            
            # Schwab requires Basic Auth header with base64(client_id:secret)
            credentials = f"{self.client_id}:{self.client_secret}"
            basic_auth = base64.b64encode(credentials.encode()).decode()
            
            response = self._client.post(
                SCHWAB_TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "code": auth_code,
                    "redirect_uri": self.callback_url,
                },
                headers={
                    "Authorization": f"Basic {basic_auth}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )
            response.raise_for_status()
            data = response.json()
            
            self._access_token = data["access_token"]
            self._refresh_token = data.get("refresh_token")
            expires_in = data.get("expires_in", 1800)  # Default 30 min
            self._token_expiry = now_et() + timedelta(seconds=expires_in - 60)  # Buffer
            
            self._save_tokens()
            logger.info("[Schwab] Successfully authenticated!")
            return True
            
        except httpx.HTTPStatusError as e:
            logger.error(f"[Schwab] Token exchange failed: {e}")
            logger.error(f"[Schwab] Response body: {e.response.text}")
            return False
        except Exception as e:
            logger.error(f"[Schwab] Token exchange failed: {e}")
            return False
    
    def _refresh_access_token(self) -> bool:
        """Refresh the access token using refresh token."""
        if not self._refresh_token:
            logger.warning("[Schwab] No refresh token available")
            return False
        
        try:
            # Schwab requires Basic Auth header
            credentials = f"{self.client_id}:{self.client_secret}"
            basic_auth = base64.b64encode(credentials.encode()).decode()
            
            response = self._client.post(
                SCHWAB_TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self._refresh_token,
                },
                headers={
                    "Authorization": f"Basic {basic_auth}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )
            response.raise_for_status()
            data = response.json()
            
            self._access_token = data["access_token"]
            if "refresh_token" in data:
                self._refresh_token = data["refresh_token"]
            expires_in = data.get("expires_in", 1800)
            self._token_expiry = now_et() + timedelta(seconds=expires_in - 60)
            
            self._save_tokens()
            logger.info("[Schwab] Token refreshed successfully")
            return True
            
        except Exception as e:
            logger.warning(f"[Schwab] Token refresh failed: {e}")
            self._access_token = None
            return False
    
    def get_quote(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get real-time quote with bid/ask for a symbol.
        
        Returns dict with: price, bid, ask, bidSize, askSize, volume
        Returns None if authentication failed or API error.
        """
        if not self.is_authenticated():
            logger.warning(f"[Schwab] Not authenticated - cannot get quote for {symbol}")
            return None
        
        try:
            response = self._client.get(
                SCHWAB_QUOTES_URL,
                params={"symbols": symbol, "fields": "quote"},
                headers={"Authorization": f"Bearer {self._access_token}"},
            )
            response.raise_for_status()
            data = response.json()
            
            if symbol not in data:
                logger.warning(f"[Schwab] No data returned for {symbol}")
                return None
            
            quote = data[symbol].get("quote", {})
            
            return {
                "symbol": symbol,
                "price": quote.get("lastPrice", 0),
                "bid": quote.get("bidPrice", 0),
                "ask": quote.get("askPrice", 0),
                "bidSize": quote.get("bidSize", 0),
                "askSize": quote.get("askSize", 0),
                "volume": quote.get("totalVolume", 0),
            }
            
        except Exception as e:
            logger.warning(f"[Schwab] Quote request failed for {symbol}: {e}")
            return None


# Singleton
_schwab_adapter: Optional[SchwabAdapter] = None


def get_schwab_adapter() -> SchwabAdapter:
    """Get singleton Schwab adapter."""
    global _schwab_adapter
    if _schwab_adapter is None:
        _schwab_adapter = SchwabAdapter()
    return _schwab_adapter
