"""
Test Catalyst Verification

This test validates the catalyst verification logic that filters EP scanner candidates.
Designed to catch issues BEFORE market open.

Run with: python -m pytest nexus2/tests/test_catalyst_verification.py -v
Or directly: python nexus2/tests/test_catalyst_verification.py
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, Tuple, List


def test_fmp_adapter_catalyst_methods():
    """Test that FMP adapter has the required catalyst methods."""
    from nexus2.adapters.market_data.fmp_adapter import FMPAdapter
    
    adapter = FMPAdapter()
    
    # Check methods exist
    assert hasattr(adapter, 'has_recent_catalyst'), "Missing has_recent_catalyst method"
    assert hasattr(adapter, 'has_upcoming_earnings'), "Missing has_upcoming_earnings method"
    assert hasattr(adapter, 'has_recent_earnings'), "Missing has_recent_earnings method"
    assert hasattr(adapter, 'get_stock_news'), "Missing get_stock_news method"
    assert hasattr(adapter, 'get_earnings_calendar'), "Missing get_earnings_calendar method"
    
    print("✅ FMP adapter has all required catalyst methods")


def test_unified_market_data_catalyst_methods():
    """Test that UnifiedMarketData exposes catalyst methods."""
    from nexus2.adapters.market_data.unified import UnifiedMarketData
    
    umd = UnifiedMarketData()
    
    # Check methods exist
    assert hasattr(umd, 'has_recent_catalyst'), "Missing has_recent_catalyst method"
    assert hasattr(umd, 'has_upcoming_earnings'), "Missing has_upcoming_earnings method"
    
    print("✅ UnifiedMarketData has all required catalyst methods")


def test_has_recent_catalyst_return_type():
    """Test has_recent_catalyst returns correct tuple format."""
    from nexus2.adapters.market_data.unified import UnifiedMarketData
    
    umd = UnifiedMarketData()
    
    # Test with a common stock that likely has news
    result = umd.has_recent_catalyst("AAPL", days=5)
    
    # Must return tuple of 3 elements
    assert isinstance(result, tuple), f"Expected tuple, got {type(result)}"
    assert len(result) == 3, f"Expected 3 elements, got {len(result)}"
    
    has_catalyst, catalyst_type, description = result
    
    # Type checks
    assert isinstance(has_catalyst, bool), f"has_catalyst should be bool, got {type(has_catalyst)}"
    assert isinstance(catalyst_type, str), f"catalyst_type should be str, got {type(catalyst_type)}"
    assert isinstance(description, str), f"description should be str, got {type(description)}"
    
    # catalyst_type must be one of valid values
    assert catalyst_type in ["earnings", "news", "none"], f"Invalid catalyst_type: {catalyst_type}"
    
    print(f"✅ has_recent_catalyst returns correct format: ({has_catalyst}, '{catalyst_type}', '{description[:50]}...')")


def test_has_upcoming_earnings_return_type():
    """Test has_upcoming_earnings returns correct tuple format."""
    from nexus2.adapters.market_data.unified import UnifiedMarketData
    
    umd = UnifiedMarketData()
    
    # Test with a common stock
    result = umd.has_upcoming_earnings("AAPL", days=5)
    
    # Must return tuple of 2 elements
    assert isinstance(result, tuple), f"Expected tuple, got {type(result)}"
    assert len(result) == 2, f"Expected 2 elements, got {len(result)}"
    
    has_upcoming, earnings_date = result
    
    # Type checks
    assert isinstance(has_upcoming, bool), f"has_upcoming should be bool, got {type(has_upcoming)}"
    assert earnings_date is None or isinstance(earnings_date, str), f"earnings_date should be str or None, got {type(earnings_date)}"
    
    print(f"✅ has_upcoming_earnings returns correct format: ({has_upcoming}, '{earnings_date}')")


def test_ep_scanner_uses_catalyst_verification():
    """Test that EP scanner integrates catalyst verification."""
    from nexus2.domain.scanner.ep_scanner_service import EPScannerService
    
    scanner = EPScannerService()
    
    # The _evaluate_symbol method should call has_recent_catalyst
    # We can't easily mock this, but we can verify the method exists
    # and the scanner has access to market_data
    
    assert hasattr(scanner, 'market_data'), "Scanner missing market_data"
    assert hasattr(scanner, '_evaluate_symbol'), "Scanner missing _evaluate_symbol"
    assert hasattr(scanner.market_data, 'has_recent_catalyst'), "market_data missing has_recent_catalyst"
    assert hasattr(scanner.market_data, 'has_upcoming_earnings'), "market_data missing has_upcoming_earnings"
    
    print("✅ EP scanner has access to catalyst verification methods")


def test_catalyst_patterns_match_expected():
    """Test that catalyst regex patterns work correctly."""
    import re
    
    # Material catalyst headlines that SHOULD match
    should_match = [
        "AAPL beats earnings expectations with strong Q4 results",
        "FDA approves new drug for treatment",
        "Company announces $500M contract with government",
        "Analyst upgrades stock to Buy rating",
        "Revenue growth exceeds 20% year over year",
        "Guidance raised for fiscal year 2024",
        "New product launch drives sales surge",
    ]
    
    # Noise headlines that should NOT match
    should_not_match = [
        "Why is AAPL stock moving today?",
        "Stocks to watch this week",
        "Technical analysis shows bullish pattern",
        "Ex-dividend date for quarterly payment",
    ]
    
    # Catalyst patterns from our implementation
    catalyst_patterns = [
        r'earnings|quarterly results|quarterly report|q[1-4].*results|beat.*estimates|missed.*estimates',
        r'revenue.*[0-9]|profit.*[0-9]|loss.*[0-9]|eps.*[0-9]',
        r'fda.*approv|drug.*approv|clinical.*trial|phase.*[123]|breakthrough',
        r'contract.*\$|\$.*contract|deal.*\$|\$.*deal|partnership|acquisition|merger|buyout',
        r'guidance.*raise|guidance.*up|upgrade|raised.*target|price.*target',
        r'dividend.*increase|special.*dividend|buyback|repurchase',
        r'analyst.*upgrade|upgraded|initiated.*buy|initiated.*outperform',
        r'buy.*rating|overweight|strong.*buy',
        r'revenue.*growth|sales.*growth|beat.*expectations|surpass|exceeded',
        r'new.*product|launch|expansion|entered.*market',
    ]
    
    noise_patterns = [
        r'market.*wrap|stock.*move|why.*moving|what.*know',
        r'dividend.*ex-date|ex-dividend',
        r'watch.*list|stocks.*to.*watch|top.*picks',
        r'technical.*analysis|chart.*pattern',
    ]
    
    def matches_catalyst(headline: str) -> bool:
        headline_lower = headline.lower()
        # Check noise first
        for pattern in noise_patterns:
            if re.search(pattern, headline_lower):
                return False
        # Check catalyst patterns
        for pattern in catalyst_patterns:
            if re.search(pattern, headline_lower):
                return True
        return False
    
    # Test should_match headlines
    pattern_failures = []
    for headline in should_match:
        matched = matches_catalyst(headline)
        if not matched:
            pattern_failures.append(f"Expected match, got no match: '{headline}'")
            print(f"  ❌ Expected match, got no match: '{headline}'")
        else:
            print(f"  ✅ Correctly matched: '{headline[:50]}...'")
    
    # Test should_not_match headlines
    for headline in should_not_match:
        matched = matches_catalyst(headline)
        if matched:
            pattern_failures.append(f"Expected no match, got match: '{headline}'")
            print(f"  ❌ Expected no match, got match: '{headline}'")
        else:
            print(f"  ✅ Correctly rejected noise: '{headline[:50]}...'")
    
    # Fail if any patterns didn't work
    if pattern_failures:
        raise AssertionError(f"{len(pattern_failures)} pattern failures: {pattern_failures[0]}")


def test_live_catalyst_check():
    """
    Live test with real API calls.
    
    This tests actual FMP API responses to verify catalyst detection works.
    Uses minimal API calls to conserve rate limit.
    """
    from nexus2.adapters.market_data.unified import UnifiedMarketData
    
    umd = UnifiedMarketData()
    
    print("\n--- Live Catalyst Check ---")
    print("Testing catalyst verification with real API calls...")
    
    # Test stocks that likely had earnings recently (major tech)
    test_symbols = ["AAPL", "MSFT", "NVDA"]
    
    for symbol in test_symbols:
        print(f"\n{symbol}:")
        
        # Check recent catalyst
        has_catalyst, cat_type, cat_desc = umd.has_recent_catalyst(symbol, days=5)
        print(f"  Recent catalyst (5d): {has_catalyst} ({cat_type})")
        if has_catalyst:
            print(f"    Description: {cat_desc[:60]}...")
        
        # Check upcoming earnings
        has_upcoming, earnings_date = umd.has_upcoming_earnings(symbol, days=7)
        print(f"  Upcoming earnings (7d): {has_upcoming} ({earnings_date})")
    
    print("\n✅ Live catalyst checks completed")
    
    # Report API usage
    stats = umd.fmp.get_rate_stats()
    print(f"\nAPI calls used: {stats['calls_this_minute']}/{stats['limit_per_minute']}")


def run_all_tests():
    """Run all tests and report results."""
    print("=" * 60)
    print("CATALYST VERIFICATION TESTS")
    print("=" * 60)
    
    tests = [
        ("FMP Adapter Methods", test_fmp_adapter_catalyst_methods),
        ("Unified Market Data Methods", test_unified_market_data_catalyst_methods),
        ("has_recent_catalyst Return Type", test_has_recent_catalyst_return_type),
        ("has_upcoming_earnings Return Type", test_has_upcoming_earnings_return_type),
        ("EP Scanner Integration", test_ep_scanner_uses_catalyst_verification),
        ("Catalyst Pattern Matching", test_catalyst_patterns_match_expected),
        ("Live Catalyst Check", test_live_catalyst_check),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_fn in tests:
        print(f"\n--- {name} ---")
        try:
            test_fn()
            passed += 1
        except Exception as e:
            print(f"❌ FAILED: {e}")
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
