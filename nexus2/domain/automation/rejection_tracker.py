"""
Rejection Tracker

Logs why stocks are rejected during scanner runs.
Writes to a rotating file that keeps the last N entries.
"""

import json
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, List
import threading

# Maximum rejections to keep in the log file
MAX_REJECTIONS = 500


class RejectionReason(Enum):
    """Reasons for scanner rejection."""
    # EP Scanner
    GAP_TOO_SMALL = "gap_too_small"
    RVOL_TOO_LOW = "rvol_too_low"
    DOLLAR_VOL_LOW = "dollar_vol_low"
    RANGE_POSITION = "range_position_low"
    NO_CATALYST = "no_catalyst"
    UPCOMING_EARNINGS = "upcoming_earnings"
    VALIDATION_FAILED = "validation_failed"
    
    # Breakout Scanner
    NO_CONSOLIDATION = "no_consolidation"
    WEAK_BREAKOUT = "weak_breakout"
    MA_NOT_STACKED = "ma_not_stacked"
    
    # HTF Scanner
    NO_HTF_PATTERN = "no_htf_pattern"
    HTF_EXTENDED = "htf_extended"
    
    # Warrior Scanner
    FLOAT_TOO_HIGH = "float_too_high"
    PRICE_OUT_OF_RANGE = "price_out_of_range"
    COUNTRY_EXCLUDED = "country_excluded"
    GAP_TOO_LOW = "gap_too_low"  # Recalculated gap below threshold
    CATALYST_DILUTION = "catalyst_dilution"  # Dilution-related catalyst (private placement, etc.)
    
    # Common
    PRICE_TOO_LOW = "price_too_low"
    ETF_EXCLUDED = "etf_excluded"
    SNAPSHOT_FAILED = "snapshot_failed"
    EXCEPTION = "exception"


@dataclass
class Rejection:
    """A single rejection record."""
    timestamp: str
    symbol: str
    scanner: str  # ep, breakout, htf
    reason: str
    details: Optional[str] = None
    values: Optional[dict] = None  # e.g., {"gap": 5.2, "min_gap": 8.0}


class RejectionTracker:
    """
    Tracks scanner rejections and writes to a log file.
    
    Thread-safe singleton that maintains a rolling log of the last N rejections.
    """
    
    _instance: Optional['RejectionTracker'] = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        # Log file path
        self.log_dir = Path(__file__).parent.parent.parent / "domain" / "logs"
        self.log_file = self.log_dir / "scan_rejections.json"
        
        # In-memory buffer (also persisted to file)
        self.rejections: List[Rejection] = []
        
        # Load existing rejections from file
        self._load()
        
        self._initialized = True
    
    def _load(self):
        """Load existing rejections from file."""
        if self.log_file.exists():
            try:
                with open(self.log_file, 'r') as f:
                    data = json.load(f)
                    self.rejections = [
                        Rejection(**r) for r in data.get("rejections", [])
                    ]
            except Exception:
                self.rejections = []
    
    def _save(self):
        """Save rejections to file."""
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Trim to max size
        if len(self.rejections) > MAX_REJECTIONS:
            self.rejections = self.rejections[-MAX_REJECTIONS:]
        
        data = {
            "updated_at": datetime.now().isoformat(),
            "count": len(self.rejections),
            "rejections": [asdict(r) for r in self.rejections],
        }
        
        with open(self.log_file, 'w') as f:
            # Custom encoder to handle Decimal types
            def default_encoder(obj):
                from decimal import Decimal
                if isinstance(obj, Decimal):
                    return float(obj)
                raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")
            json.dump(data, f, indent=2, default=default_encoder)
    
    def record(
        self,
        symbol: str,
        scanner: str,
        reason: RejectionReason,
        details: Optional[str] = None,
        values: Optional[dict] = None,
    ):
        """Record a rejection."""
        rejection = Rejection(
            timestamp=datetime.now().isoformat(),
            symbol=symbol,
            scanner=scanner,
            reason=reason.value,
            details=details,
            values=values,
        )
        
        with self._lock:
            self.rejections.append(rejection)
            # Save every 10 rejections to avoid too much I/O
            if len(self.rejections) % 10 == 0:
                self._save()
    
    def flush(self):
        """Force save to disk."""
        with self._lock:
            self._save()
    
    def get_recent(self, count: int = 100, scanner: Optional[str] = None) -> List[dict]:
        """Get recent rejections, optionally filtered by scanner."""
        with self._lock:
            if scanner:
                filtered = [r for r in self.rejections if r.scanner == scanner]
            else:
                filtered = self.rejections
            
            return [asdict(r) for r in filtered[-count:]]
    
    def get_summary(self) -> dict:
        """Get summary statistics of rejections."""
        with self._lock:
            by_reason = {}
            by_scanner = {}
            
            for r in self.rejections:
                by_reason[r.reason] = by_reason.get(r.reason, 0) + 1
                by_scanner[r.scanner] = by_scanner.get(r.scanner, 0) + 1
            
            return {
                "total": len(self.rejections),
                "by_reason": by_reason,
                "by_scanner": by_scanner,
            }
    
    def clear(self):
        """Clear all rejections."""
        with self._lock:
            self.rejections = []
            self._save()


def get_rejection_tracker() -> RejectionTracker:
    """Get the singleton rejection tracker."""
    return RejectionTracker()
