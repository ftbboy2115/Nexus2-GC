"""Debug script to evaluate LULU through scanner criteria step by step."""

import sys
sys.path.insert(0, '.')

from decimal import Decimal
from nexus2.adapters.market_data import UnifiedMarketData
from nexus2.domain.scanner.rs_service import get_rs_service

def debug_lulu():
    print("=" * 60)
    print("LULU SCANNER DEBUG")
    print("=" * 60)
    
    symbol = "LULU"
    market_data = UnifiedMarketData()
    
    # Settings from scanner
    min_price = Decimal("5.0")
    min_dollar_vol = Decimal("5000000")
    min_rs_percentile = 50
    max_pullback_pct = Decimal("15.0")
    tightness_threshold = Decimal("0.50")
    volume_contraction = Decimal("0.95")
    consolidation_days = 10
    prior_trend_days = 20
    
    # Get data
    print("\n[1] Fetching price data...")
    bars = market_data.fmp.get_daily_bars(symbol, limit=60)
    if not bars or len(bars) < 30:
        print(f"  ❌ FAIL: Not enough bars ({len(bars) if bars else 0})")
        return
    print(f"  ✅ PASS: Got {len(bars)} daily bars")
    
    quote = market_data.fmp.get_quote(symbol)
    if not quote:
        print("  ❌ FAIL: No quote")
        return
    
    current_price = Decimal(str(quote.price))
    print(f"  Current price: ${current_price}")
    
    # Check price
    print("\n[2] Checking price filter...")
    if current_price < min_price:
        print(f"  ❌ FAIL: Price ${current_price} < ${min_price}")
        return
    print(f"  ✅ PASS: Price ${current_price} >= ${min_price}")
    
    # Calculate metrics
    closes = [Decimal(str(b.close)) for b in bars]
    highs = [Decimal(str(b.high)) for b in bars]
    lows = [Decimal(str(b.low)) for b in bars]
    volumes = [b.volume for b in bars]
    
    # Check dollar volume
    print("\n[3] Checking dollar volume...")
    avg_volume = sum(volumes[-20:]) / 20
    dollar_vol = current_price * Decimal(str(avg_volume))
    if dollar_vol < min_dollar_vol:
        print(f"  ❌ FAIL: Dollar vol ${dollar_vol:,.0f} < ${min_dollar_vol:,.0f}")
        return
    print(f"  ✅ PASS: Dollar vol ${dollar_vol:,.0f} >= ${min_dollar_vol:,.0f}")
    
    # Check MA alignment
    print("\n[4] Checking MA stacking...")
    sma10 = sum(closes[-10:]) / 10
    sma20 = sum(closes[-20:]) / 20
    sma50 = sum(closes[-50:]) / 50 if len(closes) >= 50 else sma20
    ma_stacked = current_price > sma10 > sma20 > sma50
    
    print(f"  Price: ${current_price:.2f}")
    print(f"  SMA10: ${sma10:.2f}")
    print(f"  SMA20: ${sma20:.2f}")
    print(f"  SMA50: ${sma50:.2f}")
    
    if not ma_stacked:
        print(f"  ❌ FAIL: MAs not stacked (price > sma10 > sma20 > sma50)")
        print(f"    price > sma10: {current_price > sma10}")
        print(f"    sma10 > sma20: {sma10 > sma20}")
        print(f"    sma20 > sma50: {sma20 > sma50}")
        return
    print(f"  ✅ PASS: MAs stacked")
    
    # Check RS
    print("\n[5] Checking RS percentile...")
    rs_percentile = get_rs_service().get_rs_percentile(symbol)
    if rs_percentile < min_rs_percentile:
        print(f"  ❌ FAIL: RS {rs_percentile} < {min_rs_percentile}")
        return
    print(f"  ✅ PASS: RS {rs_percentile} >= {min_rs_percentile}")
    
    # Consolidation detection
    print("\n[6] Checking consolidation pattern...")
    recent_highs = highs[-consolidation_days:]
    recent_lows = lows[-consolidation_days:]
    consolidation_high = max(recent_highs)
    consolidation_low = min(recent_lows)
    recent_range = consolidation_high - consolidation_low
    
    print(f"  Consolidation high: ${consolidation_high:.2f}")
    print(f"  Consolidation low: ${consolidation_low:.2f}")
    print(f"  Recent range: ${recent_range:.2f}")
    
    prior_highs = highs[-(consolidation_days + prior_trend_days):-consolidation_days]
    prior_lows = lows[-(consolidation_days + prior_trend_days):-consolidation_days]
    prior_range = max(prior_highs) - min(prior_lows) if prior_highs and prior_lows else recent_range
    
    print(f"  Prior range: ${prior_range:.2f}")
    
    tightness_score = recent_range / prior_range if prior_range > 0 else Decimal("1")
    print(f"  Tightness score: {float(tightness_score):.2f} (threshold: {float(tightness_threshold):.2f})")
    
    if tightness_score > tightness_threshold:
        print(f"  ❌ FAIL: Not tight enough ({float(tightness_score):.2f} > {float(tightness_threshold):.2f})")
    else:
        print(f"  ✅ PASS: Tight consolidation")
    
    # Volume contraction
    print("\n[7] Checking volume contraction...")
    recent_avg_vol = sum(volumes[-consolidation_days:]) / consolidation_days
    prior_avg_vol = sum(volumes[-(consolidation_days + prior_trend_days):-consolidation_days]) / prior_trend_days
    volume_ratio = Decimal(str(recent_avg_vol / prior_avg_vol)) if prior_avg_vol > 0 else Decimal("1")
    
    print(f"  Recent avg vol: {recent_avg_vol:,.0f}")
    print(f"  Prior avg vol: {prior_avg_vol:,.0f}")
    print(f"  Volume ratio: {float(volume_ratio):.2f} (threshold: {float(volume_contraction):.2f})")
    
    if volume_ratio > volume_contraction:
        print(f"  ❌ FAIL: Volume not contracting ({float(volume_ratio):.2f} > {float(volume_contraction):.2f})")
    else:
        print(f"  ✅ PASS: Volume contracting")
    
    # Pullback check
    print("\n[8] Checking pullback from high...")
    high_20d = max(highs[-20:])
    pullback_from_high = ((high_20d - current_price) / high_20d) * 100
    
    print(f"  20-day high: ${high_20d:.2f}")
    print(f"  Pullback: {float(pullback_from_high):.1f}%")
    
    if pullback_from_high < Decimal("2"):
        print(f"  ⚠️  EXTENDED: Pullback {float(pullback_from_high):.1f}% < 2%")
    elif pullback_from_high > max_pullback_pct:
        print(f"  ❌ FAIL: Pullback {float(pullback_from_high):.1f}% > {float(max_pullback_pct):.1f}%")
    else:
        print(f"  ✅ PASS: Pullback in range")
    
    # Final status
    print("\n" + "=" * 60)
    print("FINAL STATUS DETERMINATION")
    print("=" * 60)
    
    is_tight = tightness_score <= tightness_threshold
    is_vol_contracting = volume_ratio <= volume_contraction
    pullback_ok = pullback_from_high <= max_pullback_pct
    extended = pullback_from_high < Decimal("2")
    above_consol = current_price >= consolidation_high
    
    if extended:
        print("STATUS: EXTENDED - Too close to highs, no pullback entry")
    elif is_tight and is_vol_contracting and pullback_ok:
        print("STATUS: CONSOLIDATING - Valid flag pattern, ready for breakout")
    elif above_consol:
        today_vol = volumes[-1] if volumes else 0
        vol_multiple = today_vol / avg_volume if avg_volume > 0 else 0
        print(f"  Today's volume: {today_vol:,.0f}")
        print(f"  Volume multiple: {vol_multiple:.1f}x (need 1.5x)")
        if vol_multiple > 1.5:
            print("STATUS: BREAKING_OUT - Breakout with volume!")
        else:
            print("STATUS: EXTENDED - Above consolidation but no volume surge")
    else:
        print("STATUS: INVALID - Doesn't meet pattern criteria")
        print(f"  - Tight: {is_tight}")
        print(f"  - Volume contracting: {is_vol_contracting}")  
        print(f"  - Pullback OK: {pullback_ok}")


if __name__ == "__main__":
    debug_lulu()
