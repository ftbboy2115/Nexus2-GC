# L2 (Order Book Depth) Data Research Report

**Date:** 2026-02-27  
**Status:** Research Complete  
**Your Tier:** Massive (Polygon) Stocks Advanced — $199/mo

---

## Executive Summary

> [!CAUTION]
> **Polygon (now "Massive") does NOT provide Level 2 market depth for stocks.**
> Their knowledge base explicitly states: *"No, we currently do not provide level 2 market depth information for stocks."*

> [!TIP]
> **Schwab Trader API already supports L2 streaming — and `schwab_adapter.py` already exists in Nexus.**
> This is the lowest-friction, lowest-cost path to L2 data. The `schwab-py` library your adapter is built on has explicit L2 support via `NYSE_BOOK`, `NASDAQ_BOOK`, and `OPTIONS_BOOK` streaming services.

---

## 1. Polygon/Massive: L2 Not Available

Your $199/mo Stocks Advanced plan includes real-time trades, quotes, LULD, NOI, FMV, and 20+ years of history — but **no Level 2 / order book depth**. The legacy `XL2` WebSocket channel no longer exists. Crypto L2 was sunset Aug 2025. This is a platform limitation, not a tier limitation.

---

## 2. Schwab Trader API L2 (⭐ Recommended)

### Why Schwab Is the Best Path

| Advantage | Detail |
|-----------|--------|
| **Already integrated** | `schwab_adapter.py` exists with OAuth flow, token management, and NBBO quotes |
| **Free** | Included with standard Schwab account market data entitlements |
| **Full stock L2** | `NYSE_BOOK` (listed stocks) + `NASDAQ_BOOK` (NASDAQ stocks) |
| **Options L2** | `OPTIONS_BOOK` also available |
| **Python SDK** | `schwab-py` has explicit `Level Two Order Book` streaming support |
| **No new subscription** | $0 incremental cost |

### Technical Details

**Services:**
- `NYSE_BOOK` — Listed/NYSE equity symbols
- `NASDAQ_BOOK` — NASDAQ equity symbols  
- `OPTIONS_BOOK` — Option contracts

**L2 Data Fields:**

| Field ID | Name | Description |
|----------|------|-------------|
| 0 | `PRICE` | Bid or ask price level |
| 1 | `TOTAL_VOLUME` | Aggregate volume at this price level |
| 2 | `NUM_ENTRIES` | Number of individual bids/asks at this price |
| 3 | `DATA_LIST` | Per-exchange breakdown: `[Exchange ID, Volume, Sequence]` |

**Python Code Example (from `schwab-py` docs):**
```python
from schwab.streaming import StreamClient

stream_client = StreamClient(client, account_id=1234567890)

async def read_stream():
    await stream_client.login()
    stream_client.add_nasdaq_book_handler(print_message)
    await stream_client.nasdaq_book_subs(['GOOG'])
    while True:
        await stream_client.handle_message()
```

**Connection Flow:**
1. Call `get user preferences` → retrieve streamer credentials
2. Establish WebSocket to streamer URL
3. Send `LOGON` with access token
4. Send `SUBS` for `NYSE_BOOK` / `NASDAQ_BOOK` with symbol list

### Known Limitations

| Concern | Detail |
|---------|--------|
| **Concurrent symbols** | Likely limited (1-10 symbols at once for L2, vs hundreds for L1) |
| **Depth model** | Price-aggregated with per-exchange breakdown (not full MBO/individual orders) |
| **Auth friction** | 7-day token refresh cycle (already handled by `schwab_auth.py`) |
| **Historical** | Live-only — no historical L2 replay for backtesting |
| **Market hours** | L2 streaming may be limited to regular trading hours |

### Implementation Effort (Low)

Since `schwab_adapter.py` already exists with auth/token management:

1. **Extend adapter** — Add L2 WebSocket streaming methods (~100 lines)
2. **L2 data model** — Add bid/ask level types to `warrior_types.py`
3. **L2 signal module** — Wall detection, absorption, thin-ask logic
4. **Integration point** — Feed L2 signals into `warrior_monitor.py` decision loop

---

## 3. Alternative Providers (For Reference)

### Databento MBP-10 (Premium Alternative)

| Aspect | Detail |
|--------|--------|
| **Quality** | Best-in-class — 10 levels depth, nanosecond timestamps |
| **Historical** | Full market replay for backtesting ✅ |
| **Cost** | ~$199/mo extra |
| **SDK** | Python, C++, Rust |
| **Advantage** | Historical L2 data for testing against Ross's cases |
| **Disadvantage** | New subscription + new adapter required |

### IBKR (Cheap Alternative)

| Aspect | Detail |
|--------|--------|
| **Cost** | $10–75/mo (waivable with volume) |
| **Quality** | Filtered (~20% of TotalView data) |
| **Limit** | 60 concurrent symbols |
| **Disadvantage** | TWS required, mediocre API docs |

### Alpaca (Not Recommended)

Limited to BBO or own order book. Not institutional-grade L2.

---

## 4. L2 Use Cases for Warrior Bot

| Use Case | Description | Impact |
|----------|-------------|--------|
| **Bid Wall Detection** | Large resting buy orders = stronger support | Entry confidence |
| **Ask Wall Detection** | Large sell walls above price = resistance | Exit/scale timing |
| **Absorption** | Asks absorbed without price drop | Breakout confirmation |
| **Thin Ask** | Low liquidity above price | Entry urgency |
| **Spread Analysis** | Wide spread = low liquidity | Trade quality filter |

---

## 5. Recommendation

### Phase 1: Schwab L2 (Start Here — $0 cost)
- Extend existing `schwab_adapter.py` with L2 streaming
- Build initial wall detection and thin-ask signals
- Test live during market hours with Warrior bot candidates
- **Estimated effort: 2-3 sessions**

### Phase 2 (Optional): Databento for Backtesting
- If L2 signals show promise in live testing, add Databento for historical replay
- Test L2 signals against Ross's historical cases
- **Only if Phase 1 proves L2 is valuable**

### Cost Summary

| Path | Incremental Cost | Total Monthly |
|------|-----------------|---------------|
| **Schwab L2** (recommended) | **$0** | $199/mo (Polygon only) |
| + Databento (Phase 2) | +$199/mo | $398/mo |
| IBKR alternative | +$10–75/mo | $209–274/mo |

---

*Research verified via Massive docs browser inspection, Schwab developer portal, `schwab-py` documentation (ReadTheDocs), YouTube video analysis, and web search.*
