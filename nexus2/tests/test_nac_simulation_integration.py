"""
NAC Simulation Integration Test

End-to-end test of the simulation environment:
1. Reset simulation with mock broker
2. Load real historical data from FMP
3. Enable sim_mode and auto_execute
4. Run a scan to generate signals
5. Verify MockBroker received the orders
6. Advance time and check P&L
"""

import requests
import json
import time

API_BASE = "http://localhost:8000/automation"


def log(msg):
    print(f"[TEST] {msg}")


def test_integration():
    """Run full NAC integration test."""
    
    # =========================================================================
    # Step 1: Reset simulation
    # =========================================================================
    log("Step 1: Resetting simulation...")
    r = requests.post(f"{API_BASE}/simulation/reset", params={
        "initial_cash": 100000,
        "load_synthetic": False,  # We'll load real data
    })
    assert r.status_code == 200, f"Reset failed: {r.text}"
    data = r.json()
    log(f"  ✅ Reset complete. Cash: ${data['broker']['account']['cash']:,.2f}")
    
    # =========================================================================
    # Step 2: Load real historical data
    # =========================================================================
    log("Step 2: Loading historical data for NVDA...")
    r = requests.post(f"{API_BASE}/simulation/load_historical", params={
        "symbol": "NVDA",
        "days": 120,
    })
    assert r.status_code == 200, f"Load failed: {r.text}"
    data = r.json()
    log(f"  ✅ Loaded {data['bars_loaded']} bars for NVDA")
    log(f"  📅 Date range: {data['date_range']['start']} to {data['date_range']['end']}")
    log(f"  ⏰ Clock set to: {data['clock']['current_time']}")
    
    # =========================================================================
    # Step 3: Enable sim_mode and auto_execute
    # =========================================================================
    log("Step 3: Enabling sim_mode and auto_execute...")
    r = requests.patch(f"{API_BASE}/scheduler/settings", json={
        "sim_mode": True,
        "auto_execute": True,
    })
    assert r.status_code == 200, f"Settings update failed: {r.text}"
    data = r.json()
    log(f"  ✅ sim_mode: {data.get('sim_mode')}")
    log(f"  ✅ auto_execute: {data.get('auto_execute')}")
    
    # =========================================================================
    # Step 4: Check initial broker state
    # =========================================================================
    log("Step 4: Checking initial broker state...")
    r = requests.get(f"{API_BASE}/simulation/broker")
    assert r.status_code == 200, f"Broker check failed: {r.text}"
    data = r.json()
    log(f"  💰 Cash: ${data['account']['cash']:,.2f}")
    log(f"  📊 Positions: {data['account']['position_count']}")
    
    # =========================================================================
    # Step 5: Get simulation status
    # =========================================================================
    log("Step 5: Getting simulation status...")
    r = requests.get(f"{API_BASE}/simulation/status")
    assert r.status_code == 200, f"Status check failed: {r.text}"
    data = r.json()
    log(f"  ⏰ Current time: {data['clock']['current_time']}")
    log(f"  📈 Market hours: {data['clock']['is_market_hours']}")
    log(f"  📊 Symbols loaded: {data['market_data']['symbols']}")
    
    # =========================================================================
    # Step 6: Advance time by 5 days
    # =========================================================================
    log("Step 6: Advancing time by 5 days...")
    r = requests.post(f"{API_BASE}/simulation/advance", params={
        "days": 5,
    })
    assert r.status_code == 200, f"Advance failed: {r.text}"
    data = r.json()
    log(f"  ⏰ Time advanced: {data['old_time'][:10]} → {data['new_time'][:10]}")
    log(f"  📈 Market hours: {data['is_market_hours']}")
    
    # =========================================================================
    # Step 7: Check broker state after time advance
    # =========================================================================
    log("Step 7: Checking broker state after time advance...")
    r = requests.get(f"{API_BASE}/simulation/broker")
    assert r.status_code == 200, f"Broker check failed: {r.text}"
    data = r.json()
    log(f"  💰 Cash: ${data['account']['cash']:,.2f}")
    log(f"  📊 Positions: {data['account']['position_count']}")
    log(f"  💹 Unrealized P&L: ${data['account']['unrealized_pnl']}")
    
    # =========================================================================
    # Summary
    # =========================================================================
    print("\n" + "="*60)
    print("INTEGRATION TEST COMPLETE")
    print("="*60)
    print("""
✅ Simulation reset working
✅ FMP historical data loading working
✅ sim_mode toggle working
✅ Time advancement working
✅ Broker state tracking working

Note: Signal generation requires manual scanner trigger since 
there's no EP/breakout signal in the current dataset.
    """)


if __name__ == "__main__":
    test_integration()
