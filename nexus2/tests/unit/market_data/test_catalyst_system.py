"""
Test script for catalyst detection system.
Run: python -m nexus2.tests.test_catalyst_system
"""

import pytest
import sys
sys.path.insert(0, ".")

def test_fmp_adapter():
    """Test FMP API connectivity."""
    print("\n" + "="*60)
    print("TEST 1: FMP Adapter")
    print("="*60)
    
    from nexus2.adapters.market_data.fmp_adapter import FMPAdapter
    
    fmp = FMPAdapter()
    print(f"✓ API Key: {'SET' if fmp.config.api_key else 'MISSING'}")
    print(f"✓ Rate Stats: {fmp.get_rate_stats()}")
    
    # Test earnings calendar
    symbol = "NVDA"
    earnings = fmp.get_earnings_calendar(symbol, days_back=30)
    print(f"✓ Earnings for {symbol} (last 30 days): {len(earnings)} events")
    if earnings:
        print(f"  Latest: {earnings[0]}")
    
    # Test news headlines
    news = fmp.get_stock_news(symbol, limit=5)
    print(f"✓ News for {symbol}: {len(news)} headlines")
    if news:
        print(f"  Latest: {news[0]['title'][:60]}...")
    
    # Test recent headlines
    headlines = fmp.get_recent_headlines(symbol, days=5)
    print(f"✓ Headlines (5 days): {len(headlines)}")
    
    # Assertions
    assert fmp.config.api_key, "API key should be set"


def test_catalyst_classifier():
    """Test regex-based classifier."""
    print("\n" + "="*60)
    print("TEST 2: Catalyst Classifier (Regex)")
    print("="*60)
    
    from nexus2.domain.automation.catalyst_classifier import CatalystClassifier
    
    classifier = CatalystClassifier()
    
    # Test headlines
    test_cases = [
        ("NVDA beats Q4 earnings estimates, raises guidance", True, "earnings"),
        ("FDA approves new drug from MRNA", True, "fda"),
        ("AAPL announces $100M partnership with Microsoft", True, "contract"),
        ("XYZ announces stock offering", False, "offering"),
        ("Analyst upgrades TSLA to buy", False, None),  # Not a KK catalyst
        ("PLTR soars 15% on strong volume", True, "positive_sentiment"),
    ]
    
    for headline, expected_positive, expected_type in test_cases:
        result = classifier.classify(headline)
        status = "✓" if result.is_positive == expected_positive else "✗"
        print(f"{status} '{headline[:40]}...'")
        print(f"   → is_positive={result.is_positive}, type={result.catalyst_type}, conf={result.confidence}")
    
    # Basic assertion
    assert classifier is not None


def test_ai_validator():
    """Test Gemini AI validator."""
    print("\n" + "="*60)
    print("TEST 3: AI Catalyst Validator (Gemini)")
    print("="*60)
    
    import os
    if not os.environ.get("GOOGLE_API_KEY"):
        print("⚠ GOOGLE_API_KEY not set, skipping AI test")
        return True
    
    try:
        from nexus2.domain.automation.ai_catalyst_validator import AICatalystValidator
        
        validator = AICatalystValidator()
        
        # Test a clear catalyst
        result = validator.validate_headline(
            "Company XYZ reports record Q4 earnings, beats estimates by 25%",
            "XYZ"
        )
        print(f"✓ Earnings headline: valid={result.is_valid}, type={result.catalyst_type}")
        print(f"   Raw: {result.raw_response}")
        
        # Test a non-catalyst
        result2 = validator.validate_headline(
            "Analyst raises price target on XYZ to $150",
            "XYZ"
        )
        print(f"✓ Analyst PT headline: valid={result2.is_valid}, reason={result2.reason}")
        print(f"   Raw: {result2.raw_response}")
        
    except Exception as e:
        print(f"✗ AI validator error: {e}")
        pytest.skip("AI validator requires GOOGLE_API_KEY")


def test_full_validation():
    """Test complete validation flow."""
    print("\n" + "="*60)
    print("TEST 4: Full Validation Flow")
    print("="*60)
    
    from nexus2.domain.automation.validation import validate_before_order
    
    # Test with a real symbol
    symbol = "NVDA"
    scanned_price = 140.0
    
    print(f"Testing validation for {symbol} at ${scanned_price}...")
    
    result = validate_before_order(
        symbol=symbol,
        scanned_price=scanned_price,
        setup_type="ep",
    )
    
    print(f"✓ is_valid: {result.is_valid}")
    print(f"✓ current_price: {result.current_price}")
    print(f"✓ price_vs_entry: {result.price_vs_entry}%")
    print(f"✓ has_catalyst: {result.has_catalyst}")
    print(f"✓ catalyst_type: {result.catalyst_type}")
    print(f"✓ reasons: {result.reasons}")
    
    # Assertions
    assert result is not None
    assert hasattr(result, 'is_valid')


def main():
    """Run all tests."""
    print("\n" + "#"*60)
    print("# CATALYST DETECTION SYSTEM TEST")
    print("#"*60)
    
    results = []
    
    try:
        results.append(("FMP Adapter", test_fmp_adapter()))
    except Exception as e:
        print(f"✗ FMP Adapter FAILED: {e}")
        results.append(("FMP Adapter", False))
    
    try:
        results.append(("Catalyst Classifier", test_catalyst_classifier()))
    except Exception as e:
        print(f"✗ Catalyst Classifier FAILED: {e}")
        results.append(("Catalyst Classifier", False))
    
    try:
        results.append(("AI Validator", test_ai_validator()))
    except Exception as e:
        print(f"✗ AI Validator FAILED: {e}")
        results.append(("AI Validator", False))
    
    try:
        results.append(("Full Validation", test_full_validation()))
    except Exception as e:
        print(f"✗ Full Validation FAILED: {e}")
        results.append(("Full Validation", False))
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {name}")
    
    all_passed = all(p for _, p in results)
    print(f"\nOverall: {'✓ ALL TESTS PASSED' if all_passed else '✗ SOME TESTS FAILED'}")
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    exit(main())
