"""
Historical Bar Loader

Loads intraday bar data from JSON test case files for MockMarket replay.
Supports time-based price lookup and bar aggregation (1-min → 5-min).
"""

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Dict, List, Optional
from pathlib import Path
import logging

import pytz

logger = logging.getLogger(__name__)

# Eastern timezone for market time
ET = pytz.timezone("US/Eastern")


@dataclass
class IntradayBar:
    """Single intraday bar."""
    time: str  # "09:30" format
    open: float
    high: float
    low: float
    close: float
    volume: int
    
    @property
    def time_obj(self) -> time:
        """Parse time string to time object."""
        parts = self.time.split(":")
        return time(int(parts[0]), int(parts[1]))
    
    def to_dict(self) -> Dict:
        return {
            "t": self.time,
            "o": self.open,
            "h": self.high,
            "l": self.low,
            "c": self.close,
            "v": self.volume,
        }


@dataclass
class IntradayData:
    """Complete intraday data for a symbol/date."""
    symbol: str
    date: str  # "2026-01-23" format
    premarket: Dict = field(default_factory=dict)
    bars: List[IntradayBar] = field(default_factory=list)
    continuity_bars: List[IntradayBar] = field(default_factory=list)  # Previous day's bars for MACD
    # PATTERN COMPETITION: setup_type from YAML (pmh, abcd, vwap_break, orb, etc.)
    setup_type: Optional[str] = None
    # ENTRY VALIDATION: Ross's ground truth for comparison
    ross_entry: Optional[float] = None  # Ross's actual entry price
    ross_pnl: Optional[float] = None    # Ross's actual P&L
    
    @classmethod
    def from_json(cls, data: Dict) -> "IntradayData":
        """Load from JSON dict."""
        bars = [
            IntradayBar(
                time=b.get("t", b.get("time", "")),
                open=float(b.get("o", b.get("open", 0))),
                high=float(b.get("h", b.get("high", 0))),
                low=float(b.get("l", b.get("low", 0))),
                close=float(b.get("c", b.get("close", 0))),
                volume=int(b.get("v", b.get("volume", 0))),
            )
            for b in data.get("bars", [])
        ]
        
        # Load continuity bars (previous day's bars for MACD calculation)
        continuity_bars = [
            IntradayBar(
                time=b.get("t", b.get("time", "")),
                open=float(b.get("o", b.get("open", 0))),
                high=float(b.get("h", b.get("high", 0))),
                low=float(b.get("l", b.get("low", 0))),
                close=float(b.get("c", b.get("close", 0))),
                volume=int(b.get("v", b.get("volume", 0))),
            )
            for b in data.get("continuity_bars", [])
        ]
        
        return cls(
            symbol=data.get("symbol", ""),
            date=data.get("date", ""),
            premarket=data.get("premarket", {}),
            bars=bars,
            continuity_bars=continuity_bars,
            setup_type=data.get("setup_type"),  # From YAML merge
            ross_entry=data.get("ross_entry"),   # From YAML merge
            ross_pnl=data.get("ross_pnl"),       # From YAML merge
        )
    
    def get_price_at(self, time_str: str) -> Optional[float]:
        """Get the closing price at or before given time."""
        target = self._parse_time(time_str)
        
        # Find the last bar at or before target time
        last_price = None
        for bar in self.bars:
            bar_time = bar.time_obj
            if bar_time <= target:
                last_price = bar.close
            else:
                break
        
        return last_price
    
    def get_bars_up_to(self, time_str: str, include_continuity: bool = True) -> List[IntradayBar]:
        """
        Get all bars up to and including the given time.
        
        Args:
            time_str: Time in HH:MM format
            include_continuity: If True, prepend previous day's continuity bars for MACD calculation
        """
        target = self._parse_time(time_str)
        
        result = []
        
        # Prepend continuity bars for MACD calculation (previous day's bars)
        if include_continuity and self.continuity_bars:
            result.extend(self.continuity_bars)
        
        for bar in self.bars:
            bar_time = bar.time_obj
            if bar_time <= target:
                result.append(bar)
            else:
                break
        
        return result
    
    def aggregate_to_5min(self, time_str: str) -> List[IntradayBar]:
        """Aggregate 1-min bars to 5-min bars up to given time."""
        bars_1min = self.get_bars_up_to(time_str)
        
        if not bars_1min:
            return []
        
        # Group into 5-min buckets
        buckets: Dict[str, List[IntradayBar]] = {}
        for bar in bars_1min:
            # Calculate 5-min bucket start
            hour, minute = int(bar.time.split(":")[0]), int(bar.time.split(":")[1])
            bucket_minute = (minute // 5) * 5
            bucket_key = f"{hour:02d}:{bucket_minute:02d}"
            
            if bucket_key not in buckets:
                buckets[bucket_key] = []
            buckets[bucket_key].append(bar)
        
        # Aggregate each bucket
        result = []
        for bucket_time in sorted(buckets.keys()):
            bucket_bars = buckets[bucket_time]
            aggregated = IntradayBar(
                time=bucket_time,
                open=bucket_bars[0].open,
                high=max(b.high for b in bucket_bars),
                low=min(b.low for b in bucket_bars),
                close=bucket_bars[-1].close,
                volume=sum(b.volume for b in bucket_bars),
            )
            result.append(aggregated)
        
        return result
    
    def _parse_time(self, time_str: str) -> time:
        """Parse time string to time object."""
        parts = time_str.split(":")
        return time(int(parts[0]), int(parts[1]))


class HistoricalBarLoader:
    """
    Loads and manages historical intraday bar data for MockMarket replay.
    
    Features:
    - Load test cases from JSON files
    - Cache loaded data in memory
    - Time-based price lookup
    - Bar aggregation (1-min → 5-min)
    """
    
    # Default path to test case files
    DEFAULT_TEST_CASES_DIR = Path(__file__).parent.parent.parent / "tests" / "test_cases"
    
    def __init__(self, test_cases_dir: Optional[Path] = None):
        """
        Initialize loader.
        
        Args:
            test_cases_dir: Path to test_cases directory
        """
        self._test_cases_dir = test_cases_dir or self.DEFAULT_TEST_CASES_DIR
        self._loaded_data: Dict[str, IntradayData] = {}  # symbol -> IntradayData
        self._current_case_id: Optional[str] = None
    
    def reset(self):
        """Reset all cached data (called when loading new test case)."""
        self._loaded_data.clear()
        self._current_case_id = None
        logger.info("[HistoricalBarLoader] Reset all cached data")
    
    def load_test_case(self, case_id: str) -> Optional[IntradayData]:
        """
        Load a test case from JSON file, merging YAML metadata for setup_type.
        
        Args:
            case_id: Test case ID (e.g., "bnai_2026_01_23")
        
        Returns:
            IntradayData or None if not found
        """
        # Look for JSON file in intraday/ subdirectory
        json_path = self._test_cases_dir / "intraday" / f"{case_id}.json"
        
        if not json_path.exists():
            logger.error(f"[HistoricalBarLoader] Test case not found: {json_path}")
            return None
        
        # Load YAML metadata to get setup_type (Pattern Competition)
        yaml_meta = self._load_yaml_metadata(case_id)
        
        try:
            with open(json_path, "r") as f:
                data = json.load(f)
            
            # Merge setup_type from YAML into JSON data before parsing
            if yaml_meta and "setup_type" in yaml_meta:
                data["setup_type"] = yaml_meta["setup_type"]
            
            # ENTRY VALIDATION: Merge Ross's ground truth for comparison
            if yaml_meta:
                # Ross's entry price from expected.entry_near
                expected = yaml_meta.get("expected", {})
                if expected.get("entry_near"):
                    data["ross_entry"] = expected["entry_near"]
                # Ross's actual P&L from ross_pnl
                if yaml_meta.get("ross_pnl"):
                    data["ross_pnl"] = yaml_meta["ross_pnl"]
            
            intraday = IntradayData.from_json(data)
            self._loaded_data[intraday.symbol] = intraday
            self._current_case_id = case_id
            
            cont_count = len(intraday.continuity_bars)
            setup_info = f", setup_type={intraday.setup_type}" if intraday.setup_type else ""
            logger.info(f"[HistoricalBarLoader] Loaded {case_id}: {len(intraday.bars)} bars + {cont_count} continuity bars for {intraday.symbol}{setup_info}")
            return intraday
            
        except Exception as e:
            logger.error(f"[HistoricalBarLoader] Error loading {case_id}: {e}")
            return None
    
    def _load_yaml_metadata(self, case_id: str) -> Optional[Dict]:
        """Load metadata from warrior_setups.yaml for a test case."""
        import yaml
        yaml_path = self._test_cases_dir / "warrior_setups.yaml"
        
        if not yaml_path.exists():
            return None
        
        try:
            with open(yaml_path, "r") as f:
                data = yaml.safe_load(f)
            
            for tc in data.get("test_cases", []):
                if tc.get("id") == case_id:
                    return tc
            return None
        except Exception as e:
            logger.warning(f"[HistoricalBarLoader] Error loading YAML: {e}")
            return None
    
    def get_price_at(self, symbol: str, time_str: str) -> Optional[float]:
        """
        Get price for symbol at given time.
        
        Args:
            symbol: Stock symbol
            time_str: Time in "HH:MM" format
        
        Returns:
            Closing price at that time, or None
        """
        if symbol not in self._loaded_data:
            return None
        
        return self._loaded_data[symbol].get_price_at(time_str)
    
    def get_bars_up_to(self, symbol: str, time_str: str, timeframe: str = "1min", include_continuity: bool = True) -> List[IntradayBar]:
        """
        Get bars for symbol up to given time.
        
        Args:
            symbol: Stock symbol
            time_str: Time in "HH:MM" format
            timeframe: "1min" or "5min"
            include_continuity: If True, prepend previous day's bars for MACD calculation.
                               Set False for chart display (avoids time order issues).
        
        Returns:
            List of bars
        """
        if symbol not in self._loaded_data:
            return []
        
        data = self._loaded_data[symbol]
        
        if timeframe == "5min":
            return data.aggregate_to_5min(time_str)
        else:
            return data.get_bars_up_to(time_str, include_continuity=include_continuity)
    
    def get_premarket_data(self, symbol: str) -> Dict:
        """Get premarket data for symbol."""
        if symbol not in self._loaded_data:
            return {}
        return self._loaded_data[symbol].premarket
    
    def get_loaded_symbols(self) -> List[str]:
        """Get list of currently loaded symbols."""
        return list(self._loaded_data.keys())
    
    def clear(self):
        """Clear all loaded data."""
        self._loaded_data.clear()
        self._current_case_id = None
    
    def to_dict(self) -> Dict:
        """Convert state to dict for debugging."""
        return {
            "current_case_id": self._current_case_id,
            "loaded_symbols": self.get_loaded_symbols(),
            "bar_counts": {
                sym: len(data.bars) for sym, data in self._loaded_data.items()
            },
        }


# Global instance
_historical_bar_loader: Optional[HistoricalBarLoader] = None


def get_historical_bar_loader() -> HistoricalBarLoader:
    """Get or create global historical bar loader."""
    global _historical_bar_loader
    if _historical_bar_loader is None:
        _historical_bar_loader = HistoricalBarLoader()
    return _historical_bar_loader


def reset_historical_bar_loader() -> HistoricalBarLoader:
    """Reset global historical bar loader."""
    global _historical_bar_loader
    _historical_bar_loader = HistoricalBarLoader()
    return _historical_bar_loader
