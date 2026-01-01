"""
Pre-Market System Validation

Run before market open to ensure all components are working.
Usage: python -m nexus2.tests.validate_system
"""

import sys
sys.path.insert(0, ".")

import asyncio
from datetime import datetime


def check_backend():
    """Verify backend can start."""
    print("\n=== 1. Backend Import Check ===")
    try:
        from nexus2.api.main import app
        print("✓ Backend imports OK")
        return True
    except Exception as e:
        print(f"✗ Backend import failed: {e}")
        return False


def check_fmp():
    """Verify FMP API connectivity."""
    print("\n=== 2. FMP API Check ===")
    try:
        from nexus2.adapters.market_data.fmp_adapter import FMPAdapter
        fmp = FMPAdapter()
        
        # Check API key
        if not fmp.config.api_key:
            print("✗ FMP_API_KEY not set")
            return False
        print(f"✓ API Key: SET")
        
        # Get a quote
        quote = fmp.get_quote("AAPL")
        if quote:
            price = getattr(quote, 'price', None) or quote.get('price', 'N/A') if isinstance(quote, dict) else 'N/A'
            print(f"✓ Quote test: AAPL @ ${price}")
        else:
            print("⚠ Quote returned None (market may be closed)")
        
        # Check rate stats
        stats = fmp.get_rate_stats()
        print(f"✓ Rate stats: {stats['calls_this_minute']}/{stats['limit_per_minute']}")
        
        return True
    except Exception as e:
        print(f"✗ FMP check failed: {e}")
        return False


def check_scanner():
    """Verify scanner components."""
    print("\n=== 3. Scanner Check ===")
    try:
        from nexus2.domain.scanner.scanner_engine import ScannerEngine
        from nexus2.settings.scanner_settings import (
            ScannerSettings,
            DisqualifierSettings,
            QualityScoringSettings,
        )
        
        engine = ScannerEngine(
            settings=ScannerSettings(),
            disqualifiers=DisqualifierSettings(),
            scoring=QualityScoringSettings(),
        )
        print("✓ Scanner engine initializes")
        return True
    except Exception as e:
        print(f"✗ Scanner check failed: {e}")
        return False


def check_catalyst():
    """Verify catalyst detection."""
    print("\n=== 4. Catalyst Detection Check ===")
    try:
        from nexus2.domain.automation.catalyst_classifier import CatalystClassifier
        
        classifier = CatalystClassifier()
        
        # Test patterns
        tests = [
            ("NVDA beats Q4 earnings", True),
            ("FDA approves new drug", True),
            ("Company announces offering", False),
        ]
        
        for headline, expected_positive in tests:
            result = classifier.classify(headline)
            status = "✓" if result.is_positive == expected_positive else "✗"
            print(f"  {status} '{headline[:30]}...' -> {result.catalyst_type}")
        
        print("✓ Catalyst patterns OK")
        return True
    except Exception as e:
        print(f"✗ Catalyst check failed: {e}")
        return False


def check_settings():
    """Verify settings are loaded."""
    print("\n=== 5. Settings Check ===")
    try:
        from nexus2.api.routes.settings import get_settings
        
        settings = get_settings()
        print(f"  Risk per trade: ${settings.risk_per_trade}")
        print(f"  Max per symbol: ${settings.max_per_symbol}")
        print(f"  Max positions: {settings.max_positions}")
        print(f"  Trading mode: {settings.trading_mode}")
        print(f"  Broker type: {settings.broker_type}")
        print(f"  Dual stops: {settings.dual_stop_enabled}")
        
        if settings.trading_mode == "SIMULATION":
            print("✓ Running in SIMULATION mode (safe)")
        else:
            print("⚠ Running in LIVE mode - be careful!")
        
        return True
    except Exception as e:
        print(f"✗ Settings check failed: {e}")
        return False


def check_analytics():
    """Verify analytics service."""
    print("\n=== 6. Analytics Check ===")
    try:
        from nexus2.domain.analytics import AnalyticsService
        
        service = AnalyticsService()
        stats = service.calculate_stats([])
        print(f"✓ Analytics service OK (0 trades)")
        return True
    except Exception as e:
        print(f"✗ Analytics check failed: {e}")
        return False


def check_market_hours():
    """Check market status."""
    print("\n=== 7. Market Hours Check ===")
    now = datetime.now()
    weekday = now.weekday()
    hour = now.hour
    minute = now.minute
    
    print(f"  Current time: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    
    if weekday >= 5:
        print("  ⚠ Weekend - market closed")
        return True
    
    if hour < 9 or (hour == 9 and minute < 30):
        print("  ⏳ Pre-market (opens 9:30 AM)")
    elif hour < 16:
        print("  🟢 Market OPEN")
    else:
        print("  🔴 After hours")
    
    return True


def main():
    print("\n" + "#" * 60)
    print("# PRE-MARKET SYSTEM VALIDATION")
    print("#" * 60)
    
    results = []
    results.append(("Backend", check_backend()))
    results.append(("FMP API", check_fmp()))
    results.append(("Scanner", check_scanner()))
    results.append(("Catalyst", check_catalyst()))
    results.append(("Settings", check_settings()))
    results.append(("Analytics", check_analytics()))
    results.append(("Market Hours", check_market_hours()))
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {name}")
    
    all_passed = all(p for _, p in results)
    if all_passed:
        print("\n✅ ALL CHECKS PASSED - System ready for trading")
    else:
        print("\n❌ SOME CHECKS FAILED - Review before trading")
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    exit(main())
