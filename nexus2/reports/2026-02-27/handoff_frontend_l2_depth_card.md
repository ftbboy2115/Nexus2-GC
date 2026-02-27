# Handoff: Frontend Specialist — L2 Depth Card (Dashboard Widget)

## Task
Create an `L2DepthCard` component for the Warrior dashboard that shows real-time order book depth with bid/ask visualization and signal badges.

## Context
- Dashboard page: `nexus2/frontend/src/pages/warrior.tsx`
- Components: `nexus2/frontend/src/components/warrior/` (23 existing components)
- Pattern: Cards use `CollapsibleCard` wrapper — follow existing patterns like `WatchlistCard.tsx`
- Hooks: `useWarriorData.ts` for data fetching, `useWarriorActions.ts` for actions
- Types: `nexus2/frontend/src/components/warrior/types.ts`
- API base: `${API_BASE}/warrior/...`

## API Endpoints (being built by Backend Specialist in parallel)

### `GET /warrior/l2/status`
```json
{
    "enabled": true,
    "connected": true,
    "subscriptions": ["ALBT", "BATL", "CD"]
}
```

### `GET /warrior/l2/{symbol}`
```json
{
    "symbol": "AAPL",
    "timestamp": "2026-02-27T17:31:45Z",
    "best_bid": 263.76,
    "best_ask": 263.80,
    "spread": 0.04,
    "bids": [{"price": 263.76, "volume": 50, "num_entries": 1}, ...],
    "asks": [{"price": 263.80, "volume": 200, "num_entries": 1}, ...],
    "signals": {
        "bid_wall": null | {"price": 264.00, "volume": 15000, "side": "ask"},
        "ask_wall": null | {...},
        "thin_ask": null | {"levels_count": 2, "total_volume": 100},
        "spread_quality": {
            "spread_bps": 1.5,
            "quality": "tight" | "normal" | "wide",
            "bid_depth": 5000,
            "ask_depth": 8000,
            "imbalance": -0.23
        }
    }
}
```

---

## [NEW] `nexus2/frontend/src/components/warrior/L2DepthCard.tsx`

### Layout

```
┌─────────────────────────────────────────────┐
│ 📊 L2 Order Book          [ALBT ▼] [🔄]    │
├─────────────────────────────────────────────┤
│ Spread: $0.04 (1.5 bps)  Quality: ● Tight  │
│ Imbalance: ████████░░ +0.35 (Buyers)        │
├──────────────────┬──────────────────────────┤
│    BIDS          │    ASKS                   │
│ ██████ 263.76 50 │ 200 263.80 ████████      │
│ ████   263.71 30 │  75 263.85 ███           │
│ ██     263.65 15 │  40 263.90 ██            │
│ █      263.60 10 │ 15K 264.00 ████████████🧱│
├─────────────────────────────────────────────┤
│ Signals: 🧱 Ask Wall @ $264.00 (15K)       │
│          📉 Thin Ask: No                    │
└─────────────────────────────────────────────┘
```

### Key Features
1. **Symbol selector dropdown** — populated from L2 status `subscriptions` array
2. **Depth ladder** — horizontal bars for bids (left, green) and asks (right, red)
   - Bar width proportional to volume (relative to max volume in book)
   - Price in center, volume on edges
   - Wall levels highlighted with 🧱 icon and distinct color
3. **Signal badges** at bottom:
   - Bid Wall: 🧱 green badge with price x volume
   - Ask Wall: 🧱 red badge with price x volume
   - Thin Ask: ✅ green or ⚠️ amber
   - Spread Quality: colored dot (green=tight, yellow=normal, red=wide)
4. **Imbalance bar** — horizontal gradient bar showing bid/ask ratio
5. **Auto-refresh** — poll every 2 seconds
6. **Connection status** — show disconnected state gracefully

### Styling
- Follow existing card styles in the warrior dashboard
- Use the project's existing color scheme
- Green for bids, red for asks (standard order book convention)
- Dark background for the depth ladder area

### Integration with `warrior.tsx`
- Import and render `<L2DepthCard />` alongside other cards
- Add to card visibility toggle system (look at how other cards are toggled)
- Only render when L2 is enabled (check status endpoint first)

---

## Constraints
- Follow existing component patterns (check `WatchlistCard.tsx` for reference)
- No new npm dependencies — use existing CSS/styling approach
- Handle API errors gracefully (show "L2 Disabled" or "Not Connected")
- Poll-based, not WebSocket (keep it simple for now)
