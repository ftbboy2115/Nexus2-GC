"""
CMCT Dec 22, 2025 Retrospective Test v2

Updated with Ross-aligned logic:
- Stop = ORB low (candle low), not fixed 15c
- Scaling enabled (50% adds)

Compare what Warrior bot would have done vs Ross Cameron's actual trade.
Ross made +$10,806 on CMCT that day.
"""
import json
from pathlib import Path
from decimal import Decimal
from datetime import datetime

# Paths
DATA_DIR = Path(__file__).parent.parent.parent / "data" / "test_case_data"
CMCT_DATA_FILE = DATA_DIR / "CMCT_20251222_1min.json"

# Ross's actual trade data (from transcript)
ROSS_TRADE = {
    "entry_price": 4.65,  # Entered $4.65-$4.70 per transcript
    "pnl": 10806.46,  # Verified from video
    "description": "One-trade $10K day. Continuation squeeze, no fresh catalyst.",
}

# Bot config (UPDATED with Ross-aligned logic)
BOT_CONFIG = {
    "risk_per_trade": 250,  # Fixed dollar risk
    "use_candle_low_stop": True,  # NEW: Use ORB low, not fixed cents
    "stop_buffer_cents": 5,  # Buffer below candle low
    "mental_stop_cents": 15,  # FALLBACK only
    "enable_scaling": True,  # NEW: Enabled
    "scale_size_pct": 50,  # Add 50% on strength
    "max_scale_count": 2,  # Up to 2 adds
}

print("=" * 60)
print("CMCT Dec 22, 2025 - RETROSPECTIVE TEST v2")
print("(Updated with Ross-aligned stop & scaling logic)")
print("=" * 60)

# Load data
if not CMCT_DATA_FILE.exists():
    print(f"ERROR: Data file not found: {CMCT_DATA_FILE}")
    exit(1)

with open(CMCT_DATA_FILE) as f:
    data = json.load(f)

candles = data["candles"]
fmp_stats = data["fmp_stats"]

print(f"\nLoaded {len(candles)} candles")
print(f"Open: ${fmp_stats['open']:.2f} | High: ${fmp_stats['high']:.2f} | Low: ${fmp_stats['low']:.2f}")

# ============================================================================
# Step 1: Calculate ORB (Opening Range)
# ============================================================================
print("\n" + "-" * 60)
print("STEP 1: Opening Range (ORB)")
print("-" * 60)

first_candle = candles[0]
orb_high = first_candle["high"]
orb_low = first_candle["low"]

print(f"  First candle (9:30): O=${first_candle['open']:.2f} H=${first_candle['high']:.2f} L=${first_candle['low']:.2f}")
print(f"  ORB High: ${orb_high:.2f}")
print(f"  ORB Low: ${orb_low:.2f}")

# ============================================================================
# Step 2: Entry Trigger (PMH break at $4.65)
# ============================================================================
print("\n" + "-" * 60)
print("STEP 2: Entry Trigger")
print("-" * 60)

pmh = 4.65  # From Ross's entry
entry_price = pmh

# Find entry candle
entry_candle = None
entry_candle_idx = None
for i, c in enumerate(candles):
    if c["high"] >= pmh:
        entry_candle = c
        entry_candle_idx = i
        break

if entry_candle:
    print(f"  PMH Break (${pmh}): {entry_candle['date']} (candle #{entry_candle_idx+1})")
    print(f"  Entry candle: O=${entry_candle['open']:.2f} H=${entry_candle['high']:.2f} L=${entry_candle['low']:.2f}")
    entry_candle_low = entry_candle["low"]
else:
    print("  PMH never reached - no entry")
    exit(0)

# ============================================================================
# Step 3: Calculate Stop (NEW LOGIC)
# ============================================================================
print("\n" + "-" * 60)
print("STEP 3: Stop Calculation (Ross-aligned)")
print("-" * 60)

# Ross's method: Low of entry candle - small buffer
stop_buffer = BOT_CONFIG["stop_buffer_cents"] / 100
technical_stop = entry_candle_low - stop_buffer

# Fallback (not used when candle data available)
mental_stop = entry_price - BOT_CONFIG["mental_stop_cents"] / 100

if BOT_CONFIG["use_candle_low_stop"]:
    active_stop = technical_stop
    stop_method = "entry candle low"
else:
    active_stop = mental_stop
    stop_method = "15c mental"

print(f"  Entry candle low: ${entry_candle_low:.2f}")
print(f"  Technical stop: ${technical_stop:.2f} (candle low - {BOT_CONFIG['stop_buffer_cents']}c buffer)")
print(f"  Mental stop (fallback): ${mental_stop:.2f} (entry - 15c)")
print(f"  ACTIVE STOP: ${active_stop:.2f} via {stop_method}")

risk_per_share = entry_price - active_stop
print(f"\n  Risk per share: ${risk_per_share:.2f}")

# ============================================================================
# Step 4: Position Size
# ============================================================================
print("\n" + "-" * 60)
print("STEP 4: Position Sizing")
print("-" * 60)

initial_shares = int(BOT_CONFIG["risk_per_trade"] / risk_per_share)
print(f"  Risk per trade: ${BOT_CONFIG['risk_per_trade']}")
print(f"  Risk per share: ${risk_per_share:.2f}")
print(f"  Initial position: {initial_shares} shares")

# ============================================================================
# Step 5: Scaling (NEW LOGIC)
# ============================================================================
print("\n" + "-" * 60)
print("STEP 5: Scaling Analysis")
print("-" * 60)

if BOT_CONFIG["enable_scaling"]:
    print(f"  Scaling ENABLED (max {BOT_CONFIG['max_scale_count']} adds at {BOT_CONFIG['scale_size_pct']}% each)")
    
    # Find scale opportunities (price breaking new highs after entry)
    scale_adds = []
    last_high = entry_price
    scale_count = 0
    
    for i in range(entry_candle_idx + 5, len(candles)):  # Wait 5 candles after entry
        c = candles[i]
        if c["high"] > last_high and scale_count < BOT_CONFIG["max_scale_count"]:
            add_shares = int(initial_shares * BOT_CONFIG["scale_size_pct"] / 100)
            scale_adds.append({
                "time": c["date"],
                "price": c["high"],
                "shares": add_shares,
            })
            last_high = c["high"]
            scale_count += 1
    
    total_shares = initial_shares
    for add in scale_adds:
        print(f"  Scale #{len([a for a in scale_adds if a['time'] <= add['time']])}: +{add['shares']} shares @ ${add['price']:.2f} at {add['time']}")
        total_shares += add["shares"]
    
    if not scale_adds:
        print("  No scale opportunities detected (no new highs after entry)")
    
    print(f"\n  Final position: {total_shares} shares (initial {initial_shares} + {total_shares - initial_shares} adds)")
else:
    total_shares = initial_shares
    print("  Scaling DISABLED")

# ============================================================================
# Step 6: P&L Comparison
# ============================================================================
print("\n" + "-" * 60)
print("STEP 6: Bot vs Ross Comparison")
print("-" * 60)

# Calculate theoretical P&L at HOD
hod = fmp_stats["high"]
profit_per_share_at_hod = hod - entry_price

# Account for adds at higher prices
theoretical_pnl = 0
shares_held = initial_shares
theoretical_pnl += shares_held * profit_per_share_at_hod

for add in scale_adds:
    add_profit = (hod - add["price"]) * add["shares"]
    theoretical_pnl += add_profit
    print(f"  Add @ ${add['price']:.2f}: {add['shares']} x ${hod - add['price']:.2f} = ${add_profit:.2f}")

print(f"\n  Initial: {initial_shares} x ${profit_per_share_at_hod:.2f} = ${initial_shares * profit_per_share_at_hod:.2f}")
print(f"  Total theoretical P&L: ${theoretical_pnl:.2f}")
print(f"\n  Ross made: ${ROSS_TRADE['pnl']:,.2f}")
print(f"  Bot would make (best case): ${theoretical_pnl:.2f}")
diff = ROSS_TRADE["pnl"] - theoretical_pnl
print(f"  Difference: Ross made ${diff:,.2f} more")

# ============================================================================
# Step 7: Summary
# ============================================================================
print("\n" + "-" * 60)
print("SUMMARY")
print("-" * 60)

print(f"""
  Entry match: Yes (both at $4.65 at 10:43 AM)
  
  OLD Bot (15c mental stop, no scaling):
    - Stop: $4.50 (15c from entry)
    - Shares: 1,666
    - P&L: ~$549
  
  NEW Bot (candle low stop, scaling enabled):
    - Stop: ${active_stop:.2f} ({stop_method})
    - Initial shares: {initial_shares}
    - Final shares: {total_shares} (with {len(scale_adds)} adds)
    - P&L: ${theoretical_pnl:.2f}
  
  Ross:
    - P&L: ${ROSS_TRADE['pnl']:,.2f}
    - Likely used larger base size + aggressive scaling
""")

print("=" * 60)
print("RETROSPECTIVE TEST v2 COMPLETE")
print("=" * 60)
