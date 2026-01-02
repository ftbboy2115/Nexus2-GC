"""
Worker Controller (v1.1.0)
--------------------------
Adaptive worker/thread controller for Nexus scanners.

Design goals:
- Scanner-aware baseline worker counts (Trend vs HTF vs EP) from config.
- Time-of-day-aware scaling (market vs pre/post/overnight).
- Latency-aware adjustments (slow API => fewer workers).
- Rate-limit guardrail (avoid exceeding calls/min).
- Error-rate sensitivity (throttle when API is unhappy).
- No external dependencies, easy to log & audit.
"""

import time
from dataclasses import dataclass, field
from typing import Deque, Literal, Optional
from collections import deque
from datetime import datetime

import config   # NEW: all baselines & caps now come from config

ScannerName = Literal["TREND_DAILY", "HTF", "EP"]


# ==============================================================================
# Sliding Window for API Call Rate
# ==============================================================================
@dataclass
class RateWindow:
    """Tracks API call timestamps for a sliding 60s window."""
    calls: Deque[float] = field(default_factory=deque)
    window_seconds: int = 60

    def add_call(self, timestamp: Optional[float] = None) -> None:
        if timestamp is None:
            timestamp = time.time()
        self.calls.append(timestamp)
        self._trim(timestamp)

    def count_last_window(self, now: Optional[float] = None) -> int:
        if now is None:
            now = time.time()
        self._trim(now)
        return len(self.calls)

    def _trim(self, now: float) -> None:
        cutoff = now - self.window_seconds
        while self.calls and self.calls[0] < cutoff:
            self.calls.popleft()


# ==============================================================================
# Worker Controller
# ==============================================================================
@dataclass
class WorkerController:
    """
    Adaptive worker controller.

    Usage pattern inside scanners:
    - controller = WorkerController(scanner_name="TREND_DAILY")
    - After each API call: controller.record_api_call(latency, status_code)
    - Before launching workers: controller.get_worker_count()
    """
    scanner_name: ScannerName
    max_calls_per_min: int = config.MAX_CALLS_PER_MIN  # now from config

    # bounds
    min_workers: int = 2
    max_workers: int = 64  # soft ceiling; scanner-specific caps override this

    # internal state
    _rolling_latency: float = 0.3  # seconds
    _latency_alpha: float = 0.1    # EWMA smoothing factor
    _rate_window: RateWindow = field(default_factory=RateWindow)
    _error_count: int = 0
    _error_window_start: float = field(default_factory=time.time)
    _error_window_seconds: int = 60

    # ------------------------------------------------------------------
    # Baseline from config
    # ------------------------------------------------------------------
    def _scanner_baseline(self) -> int:
        """
        Baseline worker budget per scanner, pulled from config.
        """
        return config.WORKER_BASELINES.get(self.scanner_name, 8)

    # ------------------------------------------------------------------
    # Time-of-day adjustment
    # ------------------------------------------------------------------
    def _time_of_day_adjustment(self) -> int:
        now = datetime.now()
        hour = now.hour

        # 09:00–16:00 → market hours → conservative
        if 9 <= hour < 16:
            return -4
        # 07:00–09:00 → pre-market → moderate
        elif 7 <= hour < 9:
            return -2
        # 16:00–20:00 → post-market → neutral
        elif 16 <= hour < 20:
            return 0
        # 20:00–07:00 → overnight → aggressive
        else:
            return +4

    # ------------------------------------------------------------------
    # Latency adjustment
    # ------------------------------------------------------------------
    def _latency_adjustment(self) -> int:
        lat = self._rolling_latency

        if lat > 1.5:
            return -8
        if lat > 1.0:
            return -4
        if lat < 0.25:
            return +4
        if lat < 0.15:
            return +8
        return 0

    # ------------------------------------------------------------------
    # Rate-limit adjustment
    # ------------------------------------------------------------------
    def _rate_limit_adjustment(self) -> int:
        calls = self._rate_window.count_last_window()
        usage_ratio = calls / max(self.max_calls_per_min, 1)

        if usage_ratio > 0.9:
            return -12
        if usage_ratio > 0.75:
            return -6
        if usage_ratio < 0.4:
            return +2

        return 0

    # ------------------------------------------------------------------
    # Error-rate adjustment
    # ------------------------------------------------------------------
    def _error_rate_adjustment(self) -> int:
        now = time.time()

        # Reset window every minute
        if now - self._error_window_start > self._error_window_seconds:
            self._error_window_start = now
            self._error_count = 0
            return 0

        if self._error_count >= 10:
            return -8
        if self._error_count >= 5:
            return -4

        return 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def record_api_call(self, latency_sec: float, status_code: int) -> None:
        """
        Call this after each API request.
        Updates:
        - rolling latency
        - rate-limit window
        - error count
        """
        # rolling latency (EWMA)
        self._rolling_latency = (
            (1 - self._latency_alpha) * self._rolling_latency
            + self._latency_alpha * max(latency_sec, 0.0)
        )

        # rate window
        self._rate_window.add_call()

        # error tracking
        if status_code >= 500 or status_code == 429 or status_code == 0:
            self._error_count += 1

    def get_worker_count(self) -> int:
        """
        Compute the current recommended worker count.
        Combines:
        - scanner baseline (from config)
        - time-of-day adjustment
        - latency adjustment
        - rate-limit adjustment
        - error-rate adjustment
        - scanner-specific hard caps (from config)
        """
        base = self._scanner_baseline()
        delta_time = self._time_of_day_adjustment()
        delta_lat = self._latency_adjustment()
        delta_rate = self._rate_limit_adjustment()
        delta_err = self._error_rate_adjustment()

        workers = base + delta_time + delta_lat + delta_rate + delta_err

        # Apply scanner-specific hard cap from config
        hard_cap = config.WORKER_HARD_CAPS.get(self.scanner_name, self.max_workers)
        workers = max(self.min_workers, min(workers, hard_cap))

        return int(workers)

    def debug_snapshot(self) -> dict:
        """
        Returns a dict describing current internal state for logging/debugging.
        """
        return {
            "scanner": self.scanner_name,
            "rolling_latency": round(self._rolling_latency, 3),
            "calls_last_min": self._rate_window.count_last_window(),
            "max_calls_per_min": self.max_calls_per_min,
            "error_count_window": self._error_count,
            "error_window_seconds": self._error_window_seconds,
            "recommended_workers": self.get_worker_count(),
        }