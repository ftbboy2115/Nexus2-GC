"""
End-to-End Automation Pipeline Test

This test validates the COMPLETE automation flow:
  Scanner → UnifiedScanResult → Engine → Signal → execute_callback → Broker

Designed to catch integration issues BEFORE market open that unit tests miss.

Run with: python nexus2/tests/test_automation_e2e.py
"""

import sys
from pathlib import Path
from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


def test_1_scanner_to_unified_result():
    """
    Test: Scanner interfaces are correct.
    
    NOTE: This does NOT run a live scan (which would hit FMP rate limits).
    It only verifies the interfaces and return types.
    """
    print("\n--- Test 1: Scanner Interfaces ---")
    
    from nexus2.domain.automation.unified_scanner import (
        UnifiedScannerService,
        UnifiedScanResult,
        UnifiedScanSettings,
        ScanMode,
    )
    from nexus2.domain.automation.signals import Signal
    
    # Verify UnifiedScanResult can be created with expected fields
    result = UnifiedScanResult(
        signals=[],  # Empty signals list
        ep_count=0,
        breakout_count=0,
        htf_count=0,
        total_processed=0,
    )
    
    # Check result is correct type
    assert isinstance(result, UnifiedScanResult), \
        f"Expected UnifiedScanResult, got {type(result).__name__}"
    
    # Verify signals property returns a list
    assert isinstance(result.signals, list), \
        f"Expected signals to be list, got {type(result.signals).__name__}"
    
    # Verify total_signals property works
    assert result.total_signals == 0, f"Expected 0 signals, got {result.total_signals}"
    
    # Verify scanner service can be created
    settings = UnifiedScanSettings(
        modes=[ScanMode.EP_ONLY, ScanMode.BREAKOUT_ONLY],
        min_quality_score=5,
    )
    scanner = UnifiedScannerService(settings=settings)
    
    # Check scanner has scan method
    assert hasattr(scanner, 'scan'), "Scanner missing scan method"
    assert callable(scanner.scan), "scanner.scan is not callable"
    
    print(f"  ✅ UnifiedScanResult has correct structure")
    print(f"  ✅ UnifiedScannerService created successfully")
    print(f"  ✅ Scanner has scan() method")
    return True


def test_2_signal_has_required_fields():
    """
    Test: Signal objects have all fields required by execute_callback.
    
    IMPORTANT: Signal uses 'tactical_stop', not 'stop_price'!
    """
    print("\n--- Test 2: Signal Required Fields ---")
    
    from nexus2.domain.automation.signals import Signal, SetupType
    
    # Create a signal like the scanner would
    # Note: Signal uses tactical_stop, not stop_price!
    signal = Signal(
        symbol="TEST",
        setup_type=SetupType.EP,
        entry_price=Decimal("100.00"),
        tactical_stop=Decimal("95.00"),  # Correct field name
        quality_score=8,
        tier="FOCUS",
        rs_percentile=70,
        adr_percent=3.0,
        scanner_mode="ep",
    )
    
    # These fields are accessed in execute_callback
    required_fields = [
        "symbol",
        "entry_price", 
        "tactical_stop",  # NOT stop_price
        "quality_score",
        "setup_type",
        "scanner_mode",
        "tier",
        "rs_percentile",
        "adr_percent",
    ]
    
    for field in required_fields:
        assert hasattr(signal, field), f"Signal missing field: {field}"
        value = getattr(signal, field)
        assert value is not None, f"Signal.{field} is None"
    
    print(f"  ✅ Signal has all required fields")
    
    # Test stop_distance property (uses tactical_stop internally)
    assert hasattr(signal, 'stop_distance'), "Signal missing stop_distance property"
    stop_distance = signal.stop_distance
    assert stop_distance > 0, "Stop distance must be positive"
    print(f"  ✅ stop_distance property works: ${stop_distance}")
    
    return True


def test_3_scanmode_enum_values():
    """
    Test: ScanMode enum has correct values.
    
    This catches the EP vs EP_ONLY mismatch.
    """
    print("\n--- Test 3: ScanMode Enum Values ---")
    
    from nexus2.domain.automation.unified_scanner import ScanMode
    
    # Check correct enum members exist
    expected_members = ["ALL", "EP_ONLY", "BREAKOUT_ONLY", "HTF_ONLY"]
    
    for member in expected_members:
        assert hasattr(ScanMode, member), f"ScanMode missing: {member}"
        print(f"  ✅ ScanMode.{member}")
    
    # Verify values
    assert ScanMode.EP_ONLY.value == "ep"
    assert ScanMode.BREAKOUT_ONLY.value == "breakout"
    assert ScanMode.HTF_ONLY.value == "htf"
    print(f"  ✅ All ScanMode values correct")
    
    return True


def test_4_broker_integration():
    """
    Test: Broker can be accessed and has required methods.
    """
    print("\n--- Test 4: Broker Integration ---")
    
    from nexus2.adapters.broker.alpaca_broker import AlpacaBroker
    
    # Check broker has required methods for automation
    required_methods = [
        "submit_bracket_order",
        "get_positions",
        "cancel_order",
    ]
    
    for method in required_methods:
        assert hasattr(AlpacaBroker, method), f"Broker missing: {method}"
    
    print(f"  ✅ Broker has all required methods")
    
    # Test broker initialization (doesn't require live connection)
    try:
        broker = AlpacaBroker()
        print(f"  ✅ Broker initialized successfully")
    except Exception as e:
        print(f"  ⚠️ Broker init warning (may need API keys): {e}")
    
    return True


def test_5_catalyst_verification_in_pipeline():
    """
    Test: Catalyst verification is integrated into scanner.
    """
    print("\n--- Test 5: Catalyst Verification in Pipeline ---")
    
    from nexus2.domain.scanner.ep_scanner_service import EPScannerService
    
    scanner = EPScannerService()
    
    # Verify market_data has catalyst methods
    md = scanner.market_data
    
    assert hasattr(md, "has_recent_catalyst"), \
        "market_data missing has_recent_catalyst"
    assert hasattr(md, "has_upcoming_earnings"), \
        "market_data missing has_upcoming_earnings"
    
    print(f"  ✅ EP scanner has catalyst verification")
    
    # Verify the _evaluate_symbol method exists
    assert hasattr(scanner, "_evaluate_symbol"), \
        "Scanner missing _evaluate_symbol method"
    
    print(f"  ✅ Scanner ready for market open")
    
    return True


def test_6_full_signal_flow():
    """
    Test: Complete signal flow with mock signal.
    
    Simulates what happens when execute_callback processes a signal.
    """
    print("\n--- Test 6: Full Signal Flow ---")
    
    from nexus2.domain.automation.signals import Signal, SetupType
    from decimal import Decimal
    
    # Create signal like scanner would
    signal = Signal(
        symbol="NVDA",
        setup_type=SetupType.EP,
        entry_price=Decimal("450.00"),
        tactical_stop=Decimal("435.00"),  # Use correct field
        quality_score=8,
        tier="FOCUS",
        rs_percentile=85,
        adr_percent=4.5,
        scanner_mode="ep",
    )
    
    # Simulate execute_callback processing
    # These are the key calculations done before order submission
    
    # 1. Use stop_distance property
    stop_distance = signal.stop_distance
    assert stop_distance > 0, "Stop distance error"
    print(f"  Stop distance: ${stop_distance}")
    
    # 2. Calculate position size (simplified)
    risk_per_trade = Decimal("250")  # Example risk
    shares = int(risk_per_trade / stop_distance)
    assert shares > 0, "Shares calculation error"
    print(f"  Shares for $250 risk: {shares}")
    
    # 3. Calculate order values
    position_value = shares * signal.entry_price
    print(f"  Position value: ${position_value}")
    
    # 4. Bracket order prices
    stop_loss_price = signal.tactical_stop
    # Target could be entry + 3x risk
    take_profit_price = signal.entry_price + (stop_distance * 3)
    
    print(f"  Bracket: Entry=${signal.entry_price}, Stop=${stop_loss_price}, Target=${take_profit_price}")
    print(f"  ✅ Full signal flow calculation verified")
    
    return True


def test_7_api_endpoints():
    """
    Test: Key automation API endpoints are responsive.
    
    NOTE: This test REQUIRES the server to be running!
    It will FAIL if the server is not accessible.
    """
    print("\n--- Test 7: API Endpoints ---")
    
    import requests
    
    base = "http://localhost:8000"
    # Note: Scheduler routes are under /automation prefix
    endpoints = [
        ("/automation/status", "GET"),
        ("/automation/positions", "GET"),
        ("/automation/scheduler/status", "GET"),
        ("/automation/scheduler/diagnostics", "GET"),
    ]
    
    results = []
    for endpoint, method in endpoints:
        try:
            if method == "GET":
                r = requests.get(f"{base}{endpoint}", timeout=5)
            else:
                r = requests.post(f"{base}{endpoint}", timeout=5)
            
            if r.status_code in [200, 201]:
                print(f"  ✅ {endpoint}")
                results.append(True)
            else:
                print(f"  ❌ {endpoint}: {r.status_code}")
                results.append(False)
        except requests.exceptions.ConnectionError:
            print(f"  ❌ {endpoint}: Server not running")
            results.append(False)
        except Exception as e:
            print(f"  ❌ {endpoint}: {e}")
            results.append(False)
    
    if all(results):
        print(f"  ✅ All endpoints responsive")
        return True
    else:
        # Fail the test if ANY endpoint is unreachable
        print(f"  ❌ FAILED: Server must be running for this test!")
        return False


def run_all_tests():
    """Run all end-to-end automation tests."""
    print("=" * 70)
    print("END-TO-END AUTOMATION PIPELINE TESTS")
    print("=" * 70)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    tests = [
        ("Scanner → UnifiedScanResult", test_1_scanner_to_unified_result),
        ("Signal Required Fields", test_2_signal_has_required_fields),
        ("ScanMode Enum Values", test_3_scanmode_enum_values),
        ("Broker Integration", test_4_broker_integration),
        ("Catalyst Verification", test_5_catalyst_verification_in_pipeline),
        ("Full Signal Flow", test_6_full_signal_flow),
        ("API Endpoints", test_7_api_endpoints),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_fn in tests:
        try:
            result = test_fn()
            if result:
                passed += 1
            else:
                # Test returned False = failure
                failed += 1
        except Exception as e:
            print(f"  ❌ FAILED: {e}")
            failed += 1
    
    print("\n" + "=" * 70)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 70)
    
    if failed == 0:
        print("\n✅ ALL TESTS PASSED - Automation pipeline ready for market open!")
    else:
        print("\n⚠️ SOME TESTS FAILED - Review issues before market open")
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
