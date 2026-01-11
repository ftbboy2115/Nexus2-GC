"""
Tests for End-of-Day MA Check Job

Tests the KK-style trailing stop logic that exits positions on daily close below MA.
"""

import pytest
from datetime import datetime, date, time, timedelta
from decimal import Decimal
from unittest.mock import Mock, AsyncMock, patch
from zoneinfo import ZoneInfo

from nexus2.domain.automation.ema_check_job import (
    MACheckJob,
    MACheckResult,
    MAExitSignal,
    TrailingMAType,
    is_within_eod_window,
)


# =============================================================================
# EOD Window Tests
# =============================================================================

class TestEodWindow:
    """Tests for is_within_eod_window function."""
    
    def test_within_window_345pm(self):
        """3:45 PM ET should be within window."""
        et = ZoneInfo("America/New_York")
        mock_time = datetime(2026, 1, 10, 15, 45, 0, tzinfo=et)
        
        with patch("nexus2.domain.automation.ema_check_job.datetime") as mock_dt:
            mock_dt.now.return_value = mock_time
            assert is_within_eod_window() == True
    
    def test_within_window_355pm(self):
        """3:55 PM ET should be within window."""
        et = ZoneInfo("America/New_York")
        mock_time = datetime(2026, 1, 10, 15, 55, 0, tzinfo=et)
        
        with patch("nexus2.domain.automation.ema_check_job.datetime") as mock_dt:
            mock_dt.now.return_value = mock_time
            assert is_within_eod_window() == True
    
    def test_at_window_boundary_4pm(self):
        """4:00 PM ET should be within window (end boundary inclusive)."""
        et = ZoneInfo("America/New_York")
        mock_time = datetime(2026, 1, 10, 16, 0, 0, tzinfo=et)
        
        with patch("nexus2.domain.automation.ema_check_job.datetime") as mock_dt:
            mock_dt.now.return_value = mock_time
            assert is_within_eod_window() == True
    
    def test_outside_window_early(self):
        """3:30 PM ET should be outside window."""
        et = ZoneInfo("America/New_York")
        mock_time = datetime(2026, 1, 10, 15, 30, 0, tzinfo=et)
        
        with patch("nexus2.domain.automation.ema_check_job.datetime") as mock_dt:
            mock_dt.now.return_value = mock_time
            assert is_within_eod_window() == False
    
    def test_outside_window_late(self):
        """4:05 PM ET should be outside window."""
        et = ZoneInfo("America/New_York")
        mock_time = datetime(2026, 1, 10, 16, 5, 0, tzinfo=et)
        
        with patch("nexus2.domain.automation.ema_check_job.datetime") as mock_dt:
            mock_dt.now.return_value = mock_time
            assert is_within_eod_window() == False


# =============================================================================
# MA Exit Signal Tests
# =============================================================================

class TestMAExitSignal:
    """Tests for MAExitSignal dataclass."""
    
    def test_signal_creation(self):
        """Can create exit signal with required fields."""
        signal = MAExitSignal(
            position_id="pos-123",
            symbol="NVDA",
            daily_close=Decimal("450.00"),
            ma_value=Decimal("455.00"),
            ma_type=TrailingMAType.EMA_10,
            days_held=7,
        )
        
        assert signal.symbol == "NVDA"
        assert signal.daily_close == Decimal("450.00")
        assert signal.ma_type == TrailingMAType.EMA_10
        assert signal.days_held == 7
        assert signal.generated_at is not None


# =============================================================================
# MACheckJob Tests
# =============================================================================

class TestMACheckJobInit:
    """Tests for MACheckJob initialization."""
    
    def test_default_config(self):
        """Default config uses EMA_10 and 5-day minimum."""
        job = MACheckJob()
        
        assert job.min_days_for_trailing == 5
        assert job.default_ma_type == TrailingMAType.EMA_10
        assert job.require_timing_window == False
    
    def test_custom_config(self):
        """Can customize min days and MA type."""
        job = MACheckJob(
            min_days_for_trailing=3,
            default_ma_type=TrailingMAType.EMA_20,
            require_timing_window=True,
        )
        
        assert job.min_days_for_trailing == 3
        assert job.default_ma_type == TrailingMAType.EMA_20
        assert job.require_timing_window == True


class TestMACheckJobRun:
    """Tests for MACheckJob.run() method."""
    
    @pytest.fixture
    def job(self):
        """Create MA check job with mocked callbacks."""
        job = MACheckJob(min_days_for_trailing=5)
        return job
    
    @pytest.mark.asyncio
    async def test_no_positions_callback(self, job):
        """Returns error if no positions callback configured."""
        result = await job.run()
        
        assert result.positions_checked == 0
        assert "No get_positions callback" in result.errors[0]
    
    @pytest.mark.asyncio
    async def test_empty_positions(self, job):
        """Returns empty result for no open positions."""
        job.set_callbacks(get_positions=AsyncMock(return_value=[]))
        
        result = await job.run()
        
        assert result.positions_checked == 0
        assert result.exit_signals == []
        assert result.errors == []
    
    @pytest.mark.asyncio
    async def test_position_too_young(self, job):
        """Positions under 5 days don't trigger single-MA trailing."""
        # Position opened 2 days ago
        et = ZoneInfo("America/New_York")
        opened_at = datetime.now(et) - timedelta(days=2)
        
        positions = [{
            "id": "pos-123",
            "symbol": "NVDA",
            "opened_at": opened_at,
            "remaining_shares": 100,
        }]
        
        job.set_callbacks(
            get_positions=AsyncMock(return_value=positions),
            get_daily_close=AsyncMock(return_value=Decimal("450.00")),
            get_ema=AsyncMock(return_value=Decimal("440.00")),  # Close > both EMAs
        )
        
        result = await job.run()
        
        assert result.positions_checked == 1
        # Should not exit - close is above EMAs (trend intact)
        assert len(result.exit_signals) == 0
    
    @pytest.mark.asyncio
    async def test_character_change_early_position(self, job):
        """Days 0-4: Exit on close below BOTH 10 and 20 EMA (character change)."""
        et = ZoneInfo("America/New_York")
        opened_at = datetime.now(et) - timedelta(days=2)
        
        positions = [{
            "id": "pos-123",
            "symbol": "NVDA",
            "opened_at": opened_at,
            "remaining_shares": 100,
        }]
        
        job.set_callbacks(
            get_positions=AsyncMock(return_value=positions),
            get_daily_close=AsyncMock(return_value=Decimal("430.00")),  # Below both MAs
            get_ema=AsyncMock(side_effect=lambda sym, period: 
                Decimal("440.00") if period == 10 else Decimal("435.00")),  # 10 EMA, 20 EMA
        )
        
        result = await job.run()
        
        assert result.positions_checked == 1
        assert len(result.exit_signals) == 1
        assert result.exit_signals[0].symbol == "NVDA"
        assert result.exit_signals[0].days_held == 2
    
    @pytest.mark.asyncio
    async def test_mature_position_below_ma(self, job):
        """Day 5+: Exit on close below selected MA."""
        et = ZoneInfo("America/New_York")
        opened_at = datetime.now(et) - timedelta(days=7)
        
        positions = [{
            "id": "pos-123",
            "symbol": "TSLA",
            "opened_at": opened_at,
            "remaining_shares": 50,
        }]
        
        job.set_callbacks(
            get_positions=AsyncMock(return_value=positions),
            get_daily_close=AsyncMock(return_value=Decimal("200.00")),
            get_ema=AsyncMock(return_value=Decimal("210.00")),  # Close below 10 EMA
        )
        
        result = await job.run()
        
        assert result.positions_checked == 1
        assert len(result.exit_signals) == 1
        assert result.exit_signals[0].symbol == "TSLA"
        assert result.exit_signals[0].ma_type == TrailingMAType.EMA_10
        assert result.exit_signals[0].days_held == 7
    
    @pytest.mark.asyncio
    async def test_mature_position_above_ma(self, job):
        """Day 5+: No exit if close is above MA."""
        et = ZoneInfo("America/New_York")
        opened_at = datetime.now(et) - timedelta(days=10)
        
        positions = [{
            "id": "pos-123",
            "symbol": "AAPL",
            "opened_at": opened_at,
            "remaining_shares": 100,
        }]
        
        job.set_callbacks(
            get_positions=AsyncMock(return_value=positions),
            get_daily_close=AsyncMock(return_value=Decimal("190.00")),
            get_ema=AsyncMock(return_value=Decimal("185.00")),  # Close above 10 EMA
        )
        
        result = await job.run()
        
        assert result.positions_checked == 1
        assert len(result.exit_signals) == 0  # Should hold
    
    @pytest.mark.asyncio
    async def test_dry_run_no_execution(self, job):
        """Dry run logs but doesn't execute exits."""
        et = ZoneInfo("America/New_York")
        opened_at = datetime.now(et) - timedelta(days=7)
        
        positions = [{
            "id": "pos-123",
            "symbol": "NVDA",
            "opened_at": opened_at,
            "remaining_shares": 100,
        }]
        
        execute_mock = AsyncMock()
        job.set_callbacks(
            get_positions=AsyncMock(return_value=positions),
            get_daily_close=AsyncMock(return_value=Decimal("450.00")),
            get_ema=AsyncMock(return_value=Decimal("460.00")),  # Close below MA
            execute_exit=execute_mock,
        )
        
        result = await job.run(dry_run=True)
        
        assert len(result.exit_signals) == 1
        execute_mock.assert_not_called()  # Dry run - no execution
    
    @pytest.mark.asyncio
    async def test_live_run_executes_exits(self, job):
        """Live run (dry_run=False) executes exits."""
        et = ZoneInfo("America/New_York")
        opened_at = datetime.now(et) - timedelta(days=7)
        
        positions = [{
            "id": "pos-123",
            "symbol": "NVDA",
            "opened_at": opened_at,
            "remaining_shares": 100,
        }]
        
        execute_mock = AsyncMock()
        job.set_callbacks(
            get_positions=AsyncMock(return_value=positions),
            get_daily_close=AsyncMock(return_value=Decimal("450.00")),
            get_ema=AsyncMock(return_value=Decimal("460.00")),  # Close below MA
            execute_exit=execute_mock,
        )
        
        result = await job.run(dry_run=False)
        
        assert len(result.exit_signals) == 1
        execute_mock.assert_called_once()
        assert job.total_exits == 1


# =============================================================================
# MA Type Selection Tests
# =============================================================================

class TestMATypeSelection:
    """Tests for MA type auto-selection logic."""
    
    @pytest.fixture
    def job(self):
        """Create job with AUTO mode."""
        return MACheckJob(default_ma_type=TrailingMAType.AUTO)
    
    @pytest.mark.asyncio
    async def test_stored_affinity_10(self, job):
        """Uses stored position affinity when set."""
        job.set_position_affinity("pos-123", "10")
        
        job.set_callbacks(
            get_adr_percent=AsyncMock(return_value=3.0),
        )
        
        ma_type, adr = await job._auto_select_ma("NVDA", "pos-123")
        
        assert ma_type == TrailingMAType.LOWER_10
    
    @pytest.mark.asyncio
    async def test_stored_affinity_20(self, job):
        """Uses LOWER_20 for '20' affinity."""
        job.set_position_affinity("pos-456", "20")
        
        job.set_callbacks(
            get_adr_percent=AsyncMock(return_value=3.0),
        )
        
        ma_type, adr = await job._auto_select_ma("AAPL", "pos-456")
        
        assert ma_type == TrailingMAType.LOWER_20
    
    @pytest.mark.asyncio
    async def test_high_adr_uses_tight_ma(self, job):
        """High ADR% (>=5%) uses LOWER_10 (tight trailing)."""
        job.set_callbacks(
            get_adr_percent=AsyncMock(return_value=7.5),  # Fast mover
        )
        
        ma_type, adr = await job._auto_select_ma("TSLA", None)
        
        assert ma_type == TrailingMAType.LOWER_10
        assert adr == 7.5
    
    @pytest.mark.asyncio
    async def test_low_adr_uses_wide_ma(self, job):
        """Low ADR% (<5%) uses LOWER_20 (give more room)."""
        job.set_callbacks(
            get_adr_percent=AsyncMock(return_value=2.5),  # Slow mover
        )
        
        ma_type, adr = await job._auto_select_ma("KO", None)
        
        assert ma_type == TrailingMAType.LOWER_20
        assert adr == 2.5


# =============================================================================
# Get MA Value Tests
# =============================================================================

class TestGetMAValue:
    """Tests for _get_ma_value method."""
    
    @pytest.fixture
    def job(self):
        """Create job with mocked callbacks."""
        job = MACheckJob()
        job.set_callbacks(
            get_ema=AsyncMock(side_effect=lambda sym, period: 
                100.0 if period == 10 else 95.0),  # 10 EMA = 100, 20 EMA = 95
            get_sma=AsyncMock(side_effect=lambda sym, period: 
                102.0 if period == 10 else 97.0),  # 10 SMA = 102, 20 SMA = 97
        )
        return job
    
    @pytest.mark.asyncio
    async def test_ema_10(self, job):
        """Returns 10 EMA value."""
        val = await job._get_ma_value("NVDA", TrailingMAType.EMA_10)
        assert val == Decimal("100.0")
    
    @pytest.mark.asyncio
    async def test_ema_20(self, job):
        """Returns 20 EMA value."""
        val = await job._get_ma_value("NVDA", TrailingMAType.EMA_20)
        assert val == Decimal("95.0")
    
    @pytest.mark.asyncio
    async def test_lower_10(self, job):
        """LOWER_10 returns min of 10 EMA and 10 SMA."""
        val = await job._get_ma_value("NVDA", TrailingMAType.LOWER_10)
        # 10 EMA = 100, 10 SMA = 102 -> min = 100
        assert val == Decimal("100.0")
    
    @pytest.mark.asyncio
    async def test_lower_20(self, job):
        """LOWER_20 returns min of 20 EMA and 20 SMA."""
        val = await job._get_ma_value("NVDA", TrailingMAType.LOWER_20)
        # 20 EMA = 95, 20 SMA = 97 -> min = 95
        assert val == Decimal("95.0")


# =============================================================================
# Status Tests
# =============================================================================

class TestMACheckJobStatus:
    """Tests for get_status method."""
    
    def test_initial_status(self):
        """Status shows initial state."""
        job = MACheckJob()
        status = job.get_status()
        
        assert status["last_check"] is None
        assert status["total_checks"] == 0
        assert status["total_exits"] == 0
        assert status["min_days_for_trailing"] == 5
        assert status["default_ma_type"] == "ema_10"
