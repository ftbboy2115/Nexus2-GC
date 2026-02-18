# Handoff: Code Auditor — Exit Quote Data Freshness Investigation

@.agent/rules/agent-code-auditor.md

## Context

The Warrior bot is submitting exit sell orders with limit prices far below the actual market price, indicating the bot's quote data is stale or fundamentally incorrect at the time of exit decisions.

## Evidence: LRHC Trade (2026-02-18)

| Order | Limit Price | Avg Fill | Gap | Source |
|-------|------------|----------|-----|--------|
| BUY 10 shares | $2.08 | $2.06 | 2¢ | access_key (bot) |
| SELL 5 shares | $2.23 | $2.232 | ~0¢ | access_key (bot) |
| SELL 5 shares | $1.76 | $2.17 | **41¢ (23%)** | - (unknown) |

The sell at limit $1.76 proves the bot computed `current_price ≈ $1.78` when the actual price was $2.17.

### Earlier trades (same day)

| Symbol | Sell Limit | Alpaca Fill | Gap |
|--------|-----------|-------------|-----|
| BENF | $5.67 | $5.70 | 3¢ |
| BENF | $5.72 | $5.75 | 3¢ |
| UGRO | $4.05 | $4.08 | 3¢ |
| AUUD | $1.60 | $1.61 | 1¢ |

For BENF/UGRO/AUUD, the gap was small (1-3¢) — these might just be the 0.5% offset working as designed. But LRHC's 41¢ gap is orders of magnitude larger and cannot be explained by the offset alone.

---

## Open Questions (Investigate From Scratch)

> [!CAUTION]
> The coordinator does NOT know the answers to these questions. Do NOT confirm assumptions — investigate the actual code.

### Q1: How does `get_quote_fn` work in the exit path?

**Starting points:**
- `warrior_callbacks.py:106-116` — `create_get_quote()` creates the callback
- `warrior_callbacks.py:434` — `current_price = await get_quote_fn(symbol)`
- `warrior_callbacks.py:109` — uses `UnifiedMarketData()`

**Investigate:**
- What does `UnifiedMarketData.get_quote()` return?
- Does it use caching? What's the TTL?
- What data source(s) does it use? (Alpaca, FMP, etc.)
- Is there a fallback chain? Could one source return a stale price?

### Q2: Could the LRHC $1.78 quote come from a different data source than the $2.17 actual?

- LRHC might be thinly traded with different prices across providers
- Check if `UnifiedMarketData` cross-validates sources or returns the first one
- Check if the premarket vs RTH price might explain the gap (sell was at 8:00:04 AM, right at market open)

### Q3: Is there a race condition around market open?

- LRHC sell 2 was at 8:00:04 AM (1 second after market open)
- Could `get_quote_fn` be returning a pre-market price when the market just opened?
- Does the quote source differentiate between premarket and RTH quotes?

### Q4: What does `signal.exit_price` represent?

**Starting points:**
- `warrior_callbacks.py:432` — `current_price = float(signal.exit_price)` used as fallback
- `warrior_callbacks.py:434` — `current_price = await get_quote_fn(symbol)` used normally

**Investigate:**
- Where is `signal.exit_price` set? Is it the price when the exit was decided (could be seconds old)?
- The code at L436-439 guards against stale quotes — but does it handle the REVERSE case (quote too LOW)?
  ```python
  if current_price is None:
      current_price = signal_price
  elif current_price > signal_price * 1.05:  # ← Only guards UPWARD stale
      current_price = signal_price
  # ← NO guard for current_price << signal_price (LRHC case!)
  ```

### Q5: Check the exit_offset logic for stop exits

**Starting points:**
- `warrior_callbacks.py:442-449`

```python
if hasattr(signal, 'exit_offset_percent') and signal.exit_offset_percent > 0.01:
    offset = 1.0 - signal.exit_offset_percent
elif reason in ("mental_stop", "technical_stop", ...):
    offset = 0.99  # 1% below
else:
    offset = 0.995  # 0.5% below
```

For LRHC sell 2 at limit $1.76:
- If offset = 0.99 → `current_price = $1.7778`
- If offset = 0.995 → `current_price = $1.7688`

Both are far below $2.17. So the `current_price` itself was wrong, not just the offset.

### Q6: Is there a data adapter issue for LRHC specifically?

- LRHC is a very small ticker — might have poor quote coverage
- Check if `UnifiedMarketData` handles symbols with missing or delayed quotes
- Check what happens when quotes return `None` or $0

---

## Output Requirements

Create a report at `nexus2/reports/2026-02-18/audit_exit_quote_freshness.md` with:

1. **Quote path trace**: Complete call chain from exit decision to limit price calculation
2. **Data source analysis**: Which provider(s) `UnifiedMarketData.get_quote()` uses, caching/TTL config
3. **LRHC reconstruction**: Best hypothesis for why the bot saw $1.78 when price was $2.17
4. **Downward stale guard**: Analysis of the missing guard for `current_price << signal_price`
5. **Recommendations**: Specific code changes to prevent this class of error

### Evidence Format

Every finding MUST include:
```
**Finding:** [description]
**File:** [absolute path]:[line number]
**Code:** [exact copy-pasted snippet]
**Conclusion:** [reasoning]
```

---

## Implementation Plan Reference

See: `nexus2/reports/2026-02-18/plan_exit_fill_and_pnl_fixes.md`
