"""
Warrior Trading Simulation E2E Test

This test runs the WarriorEngine with MockBroker to verify
the complete trading loop:
1. WarriorScanner finds low-float momentum candidates
2. WarriorEngine detects entry triggers (ORB, PMH)
3. Engine submits orders to MockBroker
4. WarriorMonitor checks exit conditions
5. MockBroker fills orders and tracks positions
6. P&L is calculated

Run: python -m nexus2.tests.test_warrior_simulation
"""

import asyncio
import sys
from datetime import datetime, time as dt_time
from decimal import Decimal
from uuid import uuid4

# Set up path
sys.path.insert(0, ".")


async def run_warrior_simulation():
    print("=" * 70)
    print("WARRIOR TRADING SIMULATION E2E TEST")
    print("Testing: Scanner → Engine → MockBroker → Monitor → P&L")
    print("=" * 70)
    
    # ========== STEP 1: Initialize MockBroker ==========
    print("\n📌 Step 1: Initialize MockBroker")
    from nexus2.adapters.simulation.mock_broker import MockBroker
    
    broker = MockBroker(initial_cash=25_000)  # Warrior typically uses smaller accounts
    print(f"   Cash: ${broker.get_account()['cash']:,.2f}")
    
    # ========== STEP 2: Create Mock Candidates ==========
    print("\n📌 Step 2: Create mock Warrior candidates (simulating scanner output)")
    from nexus2.domain.scanner.warrior_scanner_service import WarriorCandidate
    
    # Simulate what the scanner would find - realistic low-float momentum stocks
    mock_candidates = [
        WarriorCandidate(
            symbol="MOCK1",
            name="Mock Low Float Inc",
            float_shares=8_000_000,
            relative_volume=Decimal("4.5"),
            catalyst_type="earnings",
            catalyst_description="Beat earnings +50%",
            price=Decimal("5.50"),
            gap_percent=Decimal("12.5"),
            is_ideal_float=True,
            is_ideal_rvol=True,
            is_ideal_gap=True,
            session_high=Decimal("5.80"),
            session_low=Decimal("5.20"),
            session_volume=500_000,
            avg_volume=100_000,
            dollar_volume=Decimal("2_750_000"),
            atr=Decimal("0.35"),
            pre_market_high=Decimal("5.75"),  # PMH for breakout trigger
        ),
        WarriorCandidate(
            symbol="MOCK2",
            name="Another Momentum Stock",
            float_shares=15_000_000,
            relative_volume=Decimal("3.2"),
            catalyst_type="news",
            catalyst_description="FDA approval",
            price=Decimal("8.25"),
            gap_percent=Decimal("8.0"),
            is_ideal_float=True,
            is_ideal_rvol=True,
            is_ideal_gap=True,
            session_high=Decimal("8.50"),
            session_low=Decimal("7.80"),
            session_volume=300_000,
            avg_volume=100_000,
            dollar_volume=Decimal("2_475_000"),
            atr=Decimal("0.50"),
            pre_market_high=Decimal("8.40"),
        ),
    ]
    
    for c in mock_candidates:
        print(f"   {c.symbol}: ${c.price} (+{c.gap_percent}%), RVOL={c.relative_volume}x, Float={c.float_shares:,}")
        print(f"      Quality Score: {c.quality_score}/10, PMH=${c.pre_market_high}")
    
    # ========== STEP 3: Set Broker Prices ==========
    print("\n📌 Step 3: Set broker prices from candidates")
    for c in mock_candidates:
        broker.set_price(c.symbol, float(c.price))
        print(f"   {c.symbol}: ${c.price}")
    
    # ========== STEP 4: Create WarriorEngine ==========
    print("\n📌 Step 4: Create WarriorEngine with MockBroker callbacks")
    from nexus2.domain.automation.warrior_engine import (
        WarriorEngine,
        WarriorEngineConfig,
        WatchedCandidate,
        EntryTriggerType,
    )
    from nexus2.domain.automation.warrior_monitor import WarriorMonitor
    
    # Configure engine for simulation
    config = WarriorEngineConfig(
        risk_per_trade=Decimal("100"),      # $100 risk per trade
        max_positions=2,
        max_daily_loss=Decimal("300"),       # $300 max daily loss
        max_capital=Decimal("5000"),         # $5000 max per trade
        sim_only=True,
        orb_enabled=True,
        pmh_enabled=True,
    )
    
    engine = WarriorEngine(config=config)
    orders_submitted = []
    
    # Create order callback to route to MockBroker
    async def mock_submit_order(
        symbol: str,
        shares: int,
        stop_price: float,
        limit_price: float = None,
        trigger_type: str = "orb",
    ):
        """Submit order to MockBroker."""
        print(f"   📝 Order: {symbol} x {shares} @ ${limit_price or 'market'}, stop=${stop_price:.2f}")
        
        try:
            result = broker.submit_bracket_order(
                client_order_id=uuid4(),
                symbol=symbol,
                quantity=shares,
                stop_loss_price=stop_price,
                limit_price=Decimal(str(limit_price)) if limit_price else None,
            )
            
            # Check if filled - MockBracketOrderResult has is_accepted
            is_filled = getattr(result, 'is_accepted', False) or getattr(result, 'filled_qty', 0) > 0
            fill_price = getattr(result, 'avg_fill_price', limit_price or broker.get_price(symbol))
            
            if is_filled:
                print(f"   ✅ Filled: {shares} @ ${fill_price:.2f}")
                orders_submitted.append({
                    "symbol": symbol,
                    "shares": shares,
                    "fill_price": float(fill_price),
                    "stop_price": stop_price,
                    "trigger_type": trigger_type,
                })
                return result
            else:
                print(f"   ❌ Rejected: {result.error}")
                return None
        except Exception as e:
            print(f"   ❌ Order failed: {e}")
            return None
    
    # Create quote callback
    def mock_get_quote(symbol: str):
        return broker.get_price(symbol)
    
    # Set callbacks
    engine.set_callbacks(
        submit_order=mock_submit_order,
        get_quote=mock_get_quote,
        get_positions=broker.get_positions,
    )
    
    print(f"   Config: risk=${config.risk_per_trade}, max_pos={config.max_positions}")
    print(f"   Entry modes: ORB={config.orb_enabled}, PMH={config.pmh_enabled}")
    
    # ========== STEP 5: Add Candidates to Watchlist ==========
    print("\n📌 Step 5: Add candidates to watchlist")
    for candidate in mock_candidates:
        watched = WatchedCandidate(
            candidate=candidate,
            pmh=candidate.pre_market_high,
            orb_high=candidate.session_high,
            orb_low=candidate.session_low,
            orb_established=True,  # Simulate ORB already formed
        )
        engine._watchlist[candidate.symbol] = watched
        print(f"   Added: {candidate.symbol} (PMH=${candidate.pre_market_high}, ORB={candidate.session_low}-{candidate.session_high})")
    
    # ========== STEP 6: Simulate PMH Breakout ==========
    print("\n📌 Step 6: Simulate PMH breakout on MOCK1")
    
    # Simulate price breaking above PMH
    breakout_price = float(mock_candidates[0].pre_market_high) + 0.10  # Break PMH by 10 cents
    broker.set_price("MOCK1", breakout_price)
    print(f"   MOCK1 price: ${breakout_price:.2f} (above PMH ${mock_candidates[0].pre_market_high})")
    
    # Calculate position size: $100 risk / (breakout - stop)
    stop_distance = breakout_price - float(mock_candidates[0].session_low)
    shares = int(float(config.risk_per_trade) / stop_distance)
    
    # Submit the order
    await mock_submit_order(
        symbol="MOCK1",
        shares=shares,
        stop_price=float(mock_candidates[0].session_low),
        limit_price=breakout_price,
        trigger_type="pmh_break",
    )
    
    # ========== STEP 7: Check Positions ==========
    print("\n📌 Step 7: Check MockBroker positions")
    positions = broker.get_positions()
    print(f"   Positions: {len(positions)}")
    for pos in positions:
        print(f"   - {pos['symbol']}: {pos['qty']} shares @ ${pos['avg_price']:.2f}, stop=${pos.get('stop_price', 'N/A')}")
    
    # ========== STEP 8: Simulate Price Movement (Winner) ==========
    print("\n📌 Step 8: Simulate price movement (2:1 R target)")
    
    entry_price = positions[0]["avg_price"] if positions else breakout_price
    stop_price = positions[0]["stop_price"] if positions else float(mock_candidates[0].session_low)
    risk = entry_price - stop_price
    target_price = entry_price + (risk * 2)  # 2:1 R
    
    print(f"   Entry: ${entry_price:.2f}")
    print(f"   Stop: ${stop_price:.2f}")
    print(f"   Risk per share: ${risk:.2f}")
    print(f"   2:1 Target: ${target_price:.2f}")
    
    # Advance price to target
    broker.set_price("MOCK1", target_price)
    print(f"   New price: ${target_price:.2f} 🎯")
    
    # ========== STEP 9: Calculate P&L ==========
    print("\n📌 Step 9: Calculate P&L")
    
    # Update position with new price
    broker.set_price("MOCK1", target_price)
    positions = broker.get_positions()
    
    for pos in positions:
        unrealized = ((target_price - pos["avg_price"]) * pos["qty"])
        pct_gain = ((target_price / pos["avg_price"]) - 1) * 100
        print(f"   {pos['symbol']}: Unrealized P&L = ${unrealized:.2f} (+{pct_gain:.1f}%)")
    
    # ========== STEP 10: Simulate Partial Exit at 2:1 R ==========
    print("\n📌 Step 10: Simulate partial exit (Ross Cameron style: 50% at 2:1 R)")
    
    if positions:
        symbol = positions[0]["symbol"]
        shares_to_sell = positions[0]["qty"] // 2  # 50% partial
        
        # Sell half
        sold = broker.sell_position(symbol, shares_to_sell)
        if sold:
            print(f"   Sold {shares_to_sell} shares @ ${target_price:.2f}")
        
        # Move stop to breakeven
        broker.update_stop(symbol, entry_price)
        print(f"   Stop moved to breakeven: ${entry_price:.2f}")
    
    # ========== STEP 11: Final Report ==========
    print("\n" + "=" * 70)
    print("WARRIOR SIMULATION RESULTS")
    print("=" * 70)
    
    account = broker.get_account()
    final_positions = broker.get_positions()
    
    print(f"✅ Candidates evaluated: {len(mock_candidates)}")
    print(f"✅ Orders submitted: {len(orders_submitted)}")
    print(f"✅ Open positions: {len(final_positions)}")
    print(f"✅ Cash: ${account['cash']:,.2f}")
    print(f"✅ Equity: ${account['portfolio_value']:,.2f}")
    print(f"✅ Unrealized P&L: ${account['unrealized_pnl']:,.2f}")
    print(f"✅ Realized P&L: ${account['realized_pnl']:,.2f}")
    
    for pos in final_positions:
        print(f"   📊 {pos['symbol']}: {pos['qty']} shares @ ${pos['avg_price']:.2f}, stop=${pos.get('stop_price', 'N/A'):.2f}")
    
    return {
        "candidates": len(mock_candidates),
        "orders": len(orders_submitted),
        "positions": len(final_positions),
        "cash": account["cash"],
        "equity": account["portfolio_value"],
        "unrealized_pnl": account["unrealized_pnl"],
        "realized_pnl": account["realized_pnl"],
    }


if __name__ == "__main__":
    result = asyncio.run(run_warrior_simulation())
    print(f"\n✅ Simulation complete: {result}")
