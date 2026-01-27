"""
Scan History Logger - Persists passed symbols from Warrior scans.

Used by the R&D Lab to build a historical universe of gappers
without needing to brute-force scan all stocks.
"""

import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from threading import Lock

logger = logging.getLogger(__name__)

# Default path for scan history
SCAN_HISTORY_PATH = Path(__file__).parent.parent.parent.parent / "data" / "scan_history.json"


class ScanHistoryLogger:
    """Logs passed symbols from Warrior scans for later use in backtesting."""
    
    def __init__(self, path: Path = None):
        self.path = path or SCAN_HISTORY_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._history: Dict[str, List[Dict[str, Any]]] = {}
        self._load()
    
    def _load(self) -> None:
        """Load existing history from disk."""
        if self.path.exists():
            try:
                with open(self.path, "r") as f:
                    self._history = json.load(f)
                logger.info(f"[ScanHistory] Loaded {len(self._history)} dates")
            except Exception as e:
                logger.warning(f"[ScanHistory] Failed to load: {e}")
                self._history = {}
    
    def _save(self) -> None:
        """Save history to disk."""
        try:
            with open(self.path, "w") as f:
                json.dump(self._history, f, indent=2)
        except Exception as e:
            logger.warning(f"[ScanHistory] Failed to save: {e}")
    
    def log_passed_symbol(
        self,
        symbol: str,
        scan_date: date,
        gap_percent: float,
        rvol: float,
        score: int,
        catalyst: Optional[str] = None,
        source: str = "scan",  # "scan" for real scanner, "backfill" for historical data
    ) -> None:
        """Log a symbol that passed the Warrior scanner.
        
        Args:
            symbol: Stock symbol
            scan_date: Date of the scan
            gap_percent: Gap percentage
            rvol: Relative volume
            score: Quality score
            catalyst: Catalyst type if any
            source: Origin of data - "scan" for real, "backfill" for historical
        """
        date_key = scan_date.isoformat()
        
        with self._lock:
            if date_key not in self._history:
                self._history[date_key] = []
            
            # Check if already logged
            existing = [s for s in self._history[date_key] if s["symbol"] == symbol]
            if existing:
                return
            
            entry = {
                "symbol": symbol,
                "gap_percent": gap_percent,
                "rvol": rvol,
                "score": score,
                "catalyst": catalyst,
                "source": source,
                "logged_at": datetime.utcnow().isoformat(),
            }
            
            self._history[date_key].append(entry)
            self._save()
            logger.debug(f"[ScanHistory] Logged {symbol} for {scan_date} (source={source})")
    
    def get_symbols_for_date(self, target_date: date) -> List[Dict[str, Any]]:
        """Get all passed symbols for a specific date.
        
        Args:
            target_date: The date to query
            
        Returns:
            List of symbol entries with gap_percent, rvol, score, catalyst
        """
        date_key = target_date.isoformat()
        return self._history.get(date_key, [])
    
    def get_all_symbols(self) -> List[str]:
        """Get all unique symbols ever logged."""
        symbols = set()
        for date_entries in self._history.values():
            for entry in date_entries:
                symbols.add(entry["symbol"])
        return sorted(list(symbols))
    
    def get_date_range(self) -> tuple:
        """Get the min and max dates in history."""
        if not self._history:
            return None, None
        dates = sorted(self._history.keys())
        return dates[0], dates[-1]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the scan history."""
        total_entries = sum(len(entries) for entries in self._history.values())
        unique_symbols = len(self.get_all_symbols())
        date_range = self.get_date_range()
        
        return {
            "total_entries": total_entries,
            "unique_symbols": unique_symbols,
            "total_dates": len(self._history),
            "date_range": date_range,
        }


# Singleton
_logger: Optional[ScanHistoryLogger] = None


def get_scan_history_logger() -> ScanHistoryLogger:
    """Get the singleton scan history logger."""
    global _logger
    if _logger is None:
        _logger = ScanHistoryLogger()
    return _logger
