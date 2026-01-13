"""
Unit tests for slippage calculation logic.
"""

from decimal import Decimal


class TestSlippageCalculation:
    """Test slippage calculation logic."""
    
    def test_slippage_cents_positive(self):
        """Test positive slippage (fill higher than intended)."""
        entry_price = Decimal("10.00")
        fill_price = Decimal("10.05")
        slippage_cents = (fill_price - entry_price) * 100
        
        assert slippage_cents == Decimal("5.0")
    
    def test_slippage_cents_negative(self):
        """Test negative slippage (fill lower than intended - good!)."""
        entry_price = Decimal("10.00")
        fill_price = Decimal("9.95")
        slippage_cents = (fill_price - entry_price) * 100
        
        assert slippage_cents == Decimal("-5.0")
    
    def test_slippage_bps(self):
        """Test slippage in basis points."""
        entry_price = Decimal("10.00")
        fill_price = Decimal("10.05")
        slippage_bps = (fill_price / entry_price - 1) * 10000
        
        assert slippage_bps == Decimal("50")  # 50 bps = 0.5%
    
    def test_slippage_zero(self):
        """Test zero slippage (perfect fill)."""
        entry_price = Decimal("10.00")
        fill_price = Decimal("10.00")
        slippage_cents = (fill_price - entry_price) * 100
        
        assert slippage_cents == Decimal("0")
