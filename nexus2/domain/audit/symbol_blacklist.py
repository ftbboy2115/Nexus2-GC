"""
Symbol Blacklist

Tracks symbols temporarily skipped due to quote divergence issues.
Supports various skip durations from 10 minutes to end of day.
Persisted to disk for restart survival.
"""

import json
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional

from nexus2.utils.time_utils import now_utc, now_et


# Skip durations in minutes
SKIP_DURATIONS = {
    "10min": 10,
    "30min": 30,
    "1hour": 60,
    "2hours": 120,
    "3hours": 180,
    "4hours": 240,
    "today": None,  # Expires at midnight ET
}


@dataclass
class BlacklistEntry:
    """A symbol in the skip list."""
    symbol: str
    reason: str  # "divergence", "manual"
    alpaca_price: Optional[float] = None
    fmp_price: Optional[float] = None
    divergence_pct: Optional[float] = None
    created_at: datetime = None
    expires_at: datetime = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = now_utc()
    
    def is_expired(self) -> bool:
        """Check if skip has expired."""
        if self.expires_at is None:
            return False
        return now_utc() >= self.expires_at
    
    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "reason": self.reason,
            "alpaca_price": self.alpaca_price,
            "fmp_price": self.fmp_price,
            "divergence_pct": self.divergence_pct,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "BlacklistEntry":
        from zoneinfo import ZoneInfo
        entry = cls(
            symbol=data["symbol"],
            reason=data.get("reason", "divergence"),
            alpaca_price=data.get("alpaca_price"),
            fmp_price=data.get("fmp_price"),
            divergence_pct=data.get("divergence_pct"),
        )
        if data.get("created_at"):
            entry.created_at = datetime.fromisoformat(data["created_at"])
            if entry.created_at.tzinfo is None:
                entry.created_at = entry.created_at.replace(tzinfo=ZoneInfo("UTC"))
        if data.get("expires_at"):
            entry.expires_at = datetime.fromisoformat(data["expires_at"])
            if entry.expires_at.tzinfo is None:
                entry.expires_at = entry.expires_at.replace(tzinfo=ZoneInfo("UTC"))
        return entry


class SymbolBlacklist:
    """
    Thread-safe symbol blacklist with disk persistence.
    """
    
    def __init__(self, persist_path: Optional[Path] = None):
        self._lock = threading.Lock()
        self._entries: Dict[str, BlacklistEntry] = {}
        self._persist_path = persist_path or Path(__file__).parent.parent.parent.parent / "data" / "symbol_blacklist.json"
        self._load()
    
    def _load(self) -> None:
        """Load blacklist from disk."""
        try:
            if self._persist_path.exists():
                data = json.loads(self._persist_path.read_text())
                for entry_data in data.get("entries", []):
                    entry = BlacklistEntry.from_dict(entry_data)
                    if not entry.is_expired():
                        self._entries[entry.symbol.upper()] = entry
        except Exception as e:
            print(f"[Blacklist] Failed to load: {e}")
    
    def _save(self) -> None:
        """Save blacklist to disk."""
        try:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "entries": [e.to_dict() for e in self._entries.values() if not e.is_expired()]
            }
            self._persist_path.write_text(json.dumps(data, indent=2))
        except Exception as e:
            print(f"[Blacklist] Failed to save: {e}")
    
    def add(
        self,
        symbol: str,
        duration_key: str,
        reason: str = "divergence",
        alpaca_price: Optional[float] = None,
        fmp_price: Optional[float] = None,
        divergence_pct: Optional[float] = None,
    ) -> BlacklistEntry:
        """
        Add symbol to blacklist.
        
        Args:
            symbol: Stock symbol
            duration_key: One of "10min", "30min", "1hour", "2hours", "3hours", "4hours", "today"
            reason: Why symbol was blacklisted
        """
        with self._lock:
            if duration_key == "today":
                # Expire at midnight ET
                now = now_et()
                midnight = now.replace(hour=23, minute=59, second=59)
                expires_at = midnight.astimezone(now_utc().tzinfo)
            else:
                minutes = SKIP_DURATIONS.get(duration_key, 10)
                expires_at = now_utc() + timedelta(minutes=minutes)
            
            entry = BlacklistEntry(
                symbol=symbol.upper(),
                reason=reason,
                alpaca_price=alpaca_price,
                fmp_price=fmp_price,
                divergence_pct=divergence_pct,
                expires_at=expires_at,
            )
            self._entries[symbol.upper()] = entry
            self._save()
            return entry
    
    def is_blacklisted(self, symbol: str) -> bool:
        """Check if symbol is currently blacklisted."""
        with self._lock:
            entry = self._entries.get(symbol.upper())
            if entry and not entry.is_expired():
                return True
            # Clean up expired entry
            if entry and entry.is_expired():
                del self._entries[symbol.upper()]
            return False
    
    def get(self, symbol: str) -> Optional[BlacklistEntry]:
        """Get blacklist entry for symbol."""
        with self._lock:
            entry = self._entries.get(symbol.upper())
            if entry and not entry.is_expired():
                return entry
            return None
    
    def remove(self, symbol: str) -> bool:
        """Remove symbol from blacklist."""
        with self._lock:
            if symbol.upper() in self._entries:
                del self._entries[symbol.upper()]
                self._save()
                return True
            return False
    
    def get_all(self) -> list[BlacklistEntry]:
        """Get all active blacklist entries."""
        with self._lock:
            return [e for e in self._entries.values() if not e.is_expired()]
    
    def cleanup_expired(self) -> int:
        """Remove expired entries. Returns count removed."""
        with self._lock:
            expired = [s for s, e in self._entries.items() if e.is_expired()]
            for symbol in expired:
                del self._entries[symbol]
            if expired:
                self._save()
            return len(expired)


# Singleton
_blacklist: Optional[SymbolBlacklist] = None


def get_symbol_blacklist() -> SymbolBlacklist:
    """Get singleton symbol blacklist."""
    global _blacklist
    if _blacklist is None:
        _blacklist = SymbolBlacklist()
    return _blacklist
