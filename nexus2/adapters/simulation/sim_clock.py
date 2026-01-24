"""
Simulation Clock

Controls simulated time for backtesting and simulation modes.
Supports time acceleration for running multi-day simulations quickly.
"""

from datetime import datetime, timedelta
from typing import Optional
import pytz


class SimulationClock:
    """
    Controls simulated time for backtesting.
    
    Features:
    - Set current simulation time
    - Advance time by minutes/hours/days
    - Speed multiplier for real-time acceleration
    - Market hours detection based on sim time
    """
    
    # Eastern timezone for market hours
    ET = pytz.timezone("US/Eastern")
    
    # Market hours (ET)
    MARKET_OPEN = (9, 30)   # 9:30 AM ET
    MARKET_CLOSE = (16, 0)  # 4:00 PM ET
    
    def __init__(self, start_time: Optional[datetime] = None, speed: float = 1.0):
        """
        Initialize simulation clock.
        
        Args:
            start_time: Initial simulation time (defaults to now)
            speed: Time acceleration factor (1.0 = realtime, 60.0 = 1 min = 1 hour)
        """
        if start_time is None:
            start_time = datetime.now(self.ET)
        elif start_time.tzinfo is None:
            start_time = self.ET.localize(start_time)
        
        self._current_time = start_time
        self._speed = speed
        self._running = False
        self._start_real_time: Optional[datetime] = None
    
    @property
    def current_time(self) -> datetime:
        """Get current simulation time."""
        return self._current_time
    
    @property
    def speed(self) -> float:
        """Get current speed multiplier."""
        return self._speed
    
    @speed.setter
    def speed(self, value: float):
        """Set speed multiplier."""
        if value <= 0:
            raise ValueError("Speed must be positive")
        self._speed = value
    
    def set_time(self, dt: datetime) -> None:
        """Set simulation time to specific datetime."""
        if dt.tzinfo is None:
            dt = self.ET.localize(dt)
        self._current_time = dt
    
    def advance(self, minutes: int = 0, hours: int = 0, days: int = 0) -> datetime:
        """
        Advance simulation time by specified amount.
        
        Args:
            minutes: Minutes to advance
            hours: Hours to advance  
            days: Days to advance
        
        Returns:
            New current time
        """
        delta = timedelta(minutes=minutes, hours=hours, days=days)
        self._current_time += delta
        return self._current_time
    
    def advance_to(self, dt: datetime) -> datetime:
        """
        Advance to specific datetime.
        
        Args:
            dt: Target datetime (must be in the future)
        
        Returns:
            New current time
        """
        if dt.tzinfo is None:
            dt = self.ET.localize(dt)
        
        if dt < self._current_time:
            raise ValueError("Cannot advance backwards in time")
        
        self._current_time = dt
        return self._current_time
    
    def advance_to_next_market_open(self) -> datetime:
        """
        Advance to next market open (9:30 AM ET).
        
        Returns:
            New current time at market open
        """
        dt = self._current_time
        
        # If before market open today, advance to today's open
        market_open_today = dt.replace(
            hour=self.MARKET_OPEN[0], 
            minute=self.MARKET_OPEN[1], 
            second=0, 
            microsecond=0
        )
        
        if dt < market_open_today:
            # Check if today is a weekday
            if dt.weekday() < 5:  # Mon-Fri
                self._current_time = market_open_today
                return self._current_time
        
        # Otherwise, find next weekday market open
        days_ahead = 1
        while True:
            next_day = dt + timedelta(days=days_ahead)
            if next_day.weekday() < 5:  # Weekday found
                self._current_time = next_day.replace(
                    hour=self.MARKET_OPEN[0],
                    minute=self.MARKET_OPEN[1],
                    second=0,
                    microsecond=0
                )
                return self._current_time
            days_ahead += 1
            if days_ahead > 7:  # Safety check
                break
        
        return self._current_time
    
    def advance_to_market_close(self) -> datetime:
        """
        Advance to market close (4:00 PM ET).
        
        Returns:
            New current time at market close
        """
        self._current_time = self._current_time.replace(
            hour=self.MARKET_CLOSE[0],
            minute=self.MARKET_CLOSE[1],
            second=0,
            microsecond=0
        )
        return self._current_time
    
    def is_market_hours(self) -> bool:
        """
        Check if current sim time is during market hours.
        
        Returns:
            True if market is open (9:30 AM - 4:00 PM ET, weekdays)
        """
        dt = self._current_time
        
        # Check weekday
        if dt.weekday() >= 5:  # Saturday=5, Sunday=6
            return False
        
        # Check time
        market_open = dt.replace(
            hour=self.MARKET_OPEN[0], 
            minute=self.MARKET_OPEN[1], 
            second=0,
            microsecond=0
        )
        market_close = dt.replace(
            hour=self.MARKET_CLOSE[0], 
            minute=self.MARKET_CLOSE[1], 
            second=0,
            microsecond=0
        )
        
        return market_open <= dt < market_close
    
    def is_eod_window(self) -> bool:
        """
        Check if current time is in EOD window (3:45-4:00 PM ET).
        
        Returns:
            True if in EOD window
        """
        dt = self._current_time
        
        if dt.weekday() >= 5:
            return False
        
        eod_start = dt.replace(hour=15, minute=45, second=0, microsecond=0)
        eod_end = dt.replace(hour=16, minute=0, second=0, microsecond=0)
        
        return eod_start <= dt < eod_end
    
    def get_trading_day(self) -> str:
        """Get current trading day as YYYY-MM-DD string."""
        return self._current_time.strftime("%Y-%m-%d")
    
    def days_since(self, dt: datetime) -> int:
        """Calculate trading days since given date."""
        if dt.tzinfo is None:
            dt = self.ET.localize(dt)
        
        delta = (self._current_time.date() - dt.date()).days
        return max(0, delta)
    
    def get_time_string(self) -> str:
        """Get current time as HH:MM string."""
        return self._current_time.strftime("%H:%M")
    
    def step_forward(self, minutes: int = 1) -> datetime:
        """
        Step forward by specified minutes.
        
        Used for manual stepping through historical replay.
        
        Args:
            minutes: Number of minutes to step forward
        
        Returns:
            New current time
        """
        return self.advance(minutes=minutes)
    
    def step_back(self, minutes: int = 1) -> datetime:
        """
        Step backward by specified minutes.
        
        Args:
            minutes: Number of minutes to step backward
        
        Returns:
            New current time
        """
        self._current_time -= timedelta(minutes=minutes)
        return self._current_time
    
    def reset_to_market_open(self) -> datetime:
        """
        Reset time to market open (9:30 AM) on the current day.
        
        Returns:
            New current time at market open
        """
        self._current_time = self._current_time.replace(
            hour=self.MARKET_OPEN[0],
            minute=self.MARKET_OPEN[1],
            second=0,
            microsecond=0
        )
        return self._current_time
    
    def set_playback_speed(self, speed: float) -> None:
        """
        Set playback speed multiplier.
        
        Args:
            speed: Speed multiplier (1.0 = 1 minute per minute, 
                   2.0 = 2 minutes per minute, etc.)
        """
        if speed <= 0:
            raise ValueError("Speed must be positive")
        if speed > 100:
            raise ValueError("Speed cannot exceed 100x")
        self._speed = speed
    
    def get_playback_speed(self) -> float:
        """Get current playback speed."""
        return self._speed
    
    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "current_time": self._current_time.isoformat(),
            "time_string": self.get_time_string(),
            "speed": self._speed,
            "is_market_hours": self.is_market_hours(),
            "is_eod_window": self.is_eod_window(),
            "trading_day": self.get_trading_day(),
        }


# Global simulation clock (singleton for easy access)
_simulation_clock: Optional[SimulationClock] = None


def get_simulation_clock() -> SimulationClock:
    """Get or create global simulation clock."""
    global _simulation_clock
    if _simulation_clock is None:
        _simulation_clock = SimulationClock()
    return _simulation_clock


def reset_simulation_clock(start_time: Optional[datetime] = None, speed: float = 1.0) -> SimulationClock:
    """Reset global simulation clock to new state."""
    global _simulation_clock
    _simulation_clock = SimulationClock(start_time=start_time, speed=speed)
    return _simulation_clock
