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
    _cached_time_obj: object = field(default=None, init=False, repr=False)
    
    def __post_init__(self):
        """Pre-parse time string once at construction."""
        parts = self.time.split(":")
        if len(parts) == 3:
            self._cached_time_obj = time(int(parts[0]), int(parts[1]), int(parts[2]))
        else:
            self._cached_time_obj = time(int(parts[0]), int(parts[1]))
    
    @property
    def time_obj(self) -> time:
        """Return cached parsed time object."""
        return self._cached_time_obj
    
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
    bars_10s: List[IntradayBar] = field(default_factory=list)  # 10-second bars for high-fidelity timing
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
        
        # Load 10s bars if present (for high-fidelity timing)
        bars_10s = [
            IntradayBar(
                time=b.get("t", b.get("time", "")),
                open=float(b.get("o", b.get("open", 0))),
                high=float(b.get("h", b.get("high", 0))),
                low=float(b.get("l", b.get("low", 0))),
                close=float(b.get("c", b.get("close", 0))),
                volume=int(b.get("v", b.get("volume", 0))),
            )
            for b in data.get("bars_10s", [])
        ]
        
        return cls(
            symbol=data.get("symbol", ""),
            date=data.get("date", ""),
            premarket=data.get("premarket", {}),
            bars=bars,
            continuity_bars=continuity_bars,
            bars_10s=bars_10s,
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
    
    def _parse_time_with_seconds(self, time_str: str) -> time:
        """Parse time string with seconds (HH:MM:SS) to time object."""
        parts = time_str.split(":")
        if len(parts) == 3:
            return time(int(parts[0]), int(parts[1]), int(parts[2]))
        return time(int(parts[0]), int(parts[1]))
    
    def has_10s_bars(self) -> bool:
        """Check if 10s bar data is available."""
        return len(self.bars_10s) > 0
    
    def get_10s_price_at(self, time_str: str) -> Optional[float]:
        """
        Get the closing price at or before given time using 10s bars.
        
        Args:
            time_str: Time in HH:MM or HH:MM:SS format
        """
        if not self.bars_10s:
            return self.get_price_at(time_str)  # Fallback to 1-min
        
        target = self._parse_time_with_seconds(time_str)
        
        last_price = None
        for bar in self.bars_10s:
            if bar.time_obj <= target:
                last_price = bar.close
            else:
                break
        
        return last_price
    
    def get_10s_bars_up_to(self, time_str: str) -> List[IntradayBar]:
        """
        Get all 10s bars up to and including the given time.
        
        Args:
            time_str: Time in HH:MM or HH:MM:SS format
        """
        if not self.bars_10s:
            return []
        
        target = self._parse_time_with_seconds(time_str)
        
        result = []
        for bar in self.bars_10s:
            if bar.time_obj <= target:
                result.append(bar)
            else:
                break
        
        return result


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
        
        Also auto-loads 10s bars if a corresponding *_10s.json file exists.
        
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
            with open(json_path, "r", encoding="utf-8") as f:
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
            
            # AUTO-LOAD 10s BARS: Look for matching *_10s.json file
            symbol = data.get("symbol", "").lower()
            date_str = data.get("date", "").replace("-", "")
            if symbol and date_str:
                bars_10s_path = self._test_cases_dir / "intraday" / f"{symbol}_{date_str}_10s.json"
                if bars_10s_path.exists():
                    try:
                        with open(bars_10s_path, "r", encoding="utf-8") as f:
                            data_10s = json.load(f)
                        data["bars_10s"] = data_10s.get("bars", [])
                        logger.info(f"[HistoricalBarLoader] Loaded {len(data['bars_10s'])} 10s bars from {bars_10s_path.name}")
                    except Exception as e:
                        logger.warning(f"[HistoricalBarLoader] Failed to load 10s bars: {e}")
            
            intraday = IntradayData.from_json(data)
            self._loaded_data[intraday.symbol] = intraday
            self._current_case_id = case_id
            
            cont_count = len(intraday.continuity_bars)
            bars_10s_count = len(intraday.bars_10s)
            setup_info = f", setup_type={intraday.setup_type}" if intraday.setup_type else ""
            bars_10s_info = f", 10s_bars={bars_10s_count}" if bars_10s_count else ""
            logger.info(f"[HistoricalBarLoader] Loaded {case_id}: {len(intraday.bars)} bars + {cont_count} continuity{bars_10s_info} for {intraday.symbol}{setup_info}")
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
            with open(yaml_path, "r", encoding="utf-8") as f:
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
    
    def has_10s_bars(self, symbol: str) -> bool:
        """Check if 10s bar data is available for symbol."""
        if symbol not in self._loaded_data:
            return False
        return self._loaded_data[symbol].has_10s_bars()
    
    def get_10s_price_at(self, symbol: str, time_str: str) -> Optional[float]:
        """
        Get price at given time using 10s bars (higher precision).
        Falls back to 1-min bars if 10s not available.
        
        Args:
            symbol: Stock symbol
            time_str: Time in "HH:MM" or "HH:MM:SS" format
        
        Returns:
            Closing price at that time, or None
        """
        if symbol not in self._loaded_data:
            return None
        
        return self._loaded_data[symbol].get_10s_price_at(time_str)
    
    def get_bars_up_to(self, symbol: str, time_str: str, timeframe: str = "1min", include_continuity: bool = True) -> List[IntradayBar]:
        """
        Get bars for symbol up to given time.
        
        Args:
            symbol: Stock symbol
            time_str: Time in "HH:MM" format
            timeframe: "1min", "5min", or "10s"
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
        elif timeframe == "10s":
            # Use 10s bars if available, fall back to 1min
            if data.has_10s_bars():
                return data.get_10s_bars_up_to(time_str)
            else:
                logger.debug(f"[HistoricalBarLoader] No 10s bars for {symbol}, falling back to 1min")
                return data.get_bars_up_to(time_str, include_continuity=include_continuity)
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
