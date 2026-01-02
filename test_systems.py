"""
Quick test script for Nexus 2 systems
Run from the Nexus directory (parent of nexus2)
"""

print("=" * 60)
print("NEXUS 2 SYSTEM TEST")
print("=" * 60)

# Test 1: FMP Intraday Data
print("\n[1] FMP Adapter - Intraday Bars")
print("-" * 40)
try:
    from nexus2.adapters.market_data.fmp_adapter import get_fmp_adapter
    
    fmp = get_fmp_adapter()
    print(f"Rate stats: {fmp.get_rate_stats()}")
    
    bars = fmp.get_intraday_bars("NVDA", timeframe="5min")
    if bars:
        print(f"✅ Got {len(bars)} intraday 5min bars for NVDA")
        print(f"   First bar: {bars[0].timestamp} - H:{bars[0].high} L:{bars[0].low}")
        print(f"   Last bar: {bars[-1].timestamp} - H:{bars[-1].high} L:{bars[-1].low}")
    else:
        print("⚠️  No intraday data (market closed or pre-market)")
        
    # Opening range
    or_result = fmp.get_opening_range("NVDA", timeframe_minutes=5)
    if or_result:
        print(f"✅ Opening Range: High={or_result[0]}, Low={or_result[1]}")
    else:
        print("⚠️  No opening range data")
except Exception as e:
    print(f"❌ Error: {e}")

# Test 2: Scheduler Settings
print("\n[2] Scheduler Settings")
print("-" * 40)
try:
    from nexus2.db import SessionLocal, SchedulerSettingsRepository
    
    db = SessionLocal()
    repo = SchedulerSettingsRepository(db)
    settings = repo.get()
    
    print(f"✅ Settings loaded:")
    print(f"   min_quality: {settings.min_quality}")
    print(f"   stop_mode: {settings.stop_mode}")
    print(f"   max_stop_atr: {settings.max_stop_atr}")
    print(f"   scan_modes: {settings.scan_modes}")
    print(f"   htf_frequency: {settings.htf_frequency}")
    db.close()
except Exception as e:
    print(f"❌ Error: {e}")

# Test 3: EP Scanner
print("\n[3] EP Scanner Service")
print("-" * 40)
try:
    from nexus2.domain.scanner.ep_scanner_service import get_ep_scanner_service
    
    ep = get_ep_scanner_service()
    print(f"✅ EP Scanner initialized")
    print(f"   Opening range minutes: {ep.ep_service.settings.opening_range_minutes}")
except Exception as e:
    print(f"❌ Error: {e}")

print("\n" + "=" * 60)
print("TEST COMPLETE")
print("=" * 60)
