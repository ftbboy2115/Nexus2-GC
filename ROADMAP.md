# Nexus 2 Roadmap

Last updated: 2026-01-18

> **Note:** This roadmap syncs with the Knowledge Item at `~/.gemini/antigravity/knowledge/nexus2_core_systems/`. AI should keep both in sync when making updates.

## Legend
- [ ] Not started
- [/] In progress
- [x] Completed

---

## 🚨 Priority: Unit Tests

> These are critical path items that prevent bugs in production.

- [x] **Auto-Start Scheduler Tests** — Prevent weekend/holiday auto-start bugs (commit `695009a`)
  - Test with mocked weekend date → expect skip ✅
  - Test with mocked holiday date → expect skip ✅
  - Test with mocked trading day → expect start ✅
- [x] **Position Sizing Tests** — Validate risk calculations (existing `test_position_sizing.py`)
  - Test stop distance calculation ✅
  - Test share count capping ✅
  - Test ATR constraint validation ✅
- [x] **Trade Event Logging Tests** — Ensure audit trail integrity (commit `695009a`)
  - Test entry events capture market context ✅
  - Test exit events capture P&L correctly ✅
- [x] **Warrior API Route Tests** — Largest API file coverage (commit `97d05bb`)
  - Engine control (start/stop/pause/resume) ✅
  - Simulation mode (enable/reset/order/price) ✅
  - Scanner and monitor settings ✅

---

## 🔧 Features

- [x] **VPS Deployment** — DigitalOcean NYC, $6/mo, Tailscale secured (Jan 8)
- [x] **HTF Simulation Testing** — Verified: scanner works, added configurable extended threshold
- [x] **Liquidate All Button** — Quick exit for paper mode testing
  - Backend: `POST /automation/liquidate-all` endpoint
  - GUI: Button in Quick Actions with confirmation modal
- [x] **Project README** — Startup instructions (backend, frontend, env setup)
- [ ] **User Guide / Wiki** — How to use the system, operational playbook
- [ ] **MarketAux News Integration** — Secondary news source for catalyst detection
  - FMP missed ROLR's Crypto.com partnership (Jan 14) that caused 279% surge
  - MarketAux: 5000+ sources, 100 req/day free tier, built-in sentiment
  - Fallback when FMP headline doesn't contain the actual catalyst
  - Add `MARKETAUX_API_KEY` to config
- [ ] **Market Conditions Tracking** — Dedicated `market_snapshots` table for correlation analysis
  - Periodic capture of SPY, QQQ, VIX, sector ETFs
  - Link to trade events for win/loss correlation
  - Dashboard widget showing market health

---

## 🛠 Technical Debt

- [x] **Graceful Shutdown** — Two-stage Ctrl+C, FMP rate limit interruptible
- [x] **Ctrl+C x3 not stopping server — FIXED** — Counter-based approach with `sys.exit(0)` (commit `83b3f18`)
- [x] **Singleton Cleanup** — Removed duplicate `global _monitor`, use `get_monitor()`
- [x] **Extract `execute_callback`** — Moved to `execution_handler.py` + 3 more modules (65% reduction)
- [x] **`_sim_broker` thread safety** — Centralized in automation_state.py with threading.Lock
- [x] **Refactor `automation.tsx`** — Extracted 7 components to `components/automation/`, reduced from 2141 to 1283 lines (40% reduction)
  - Phase 1: SchedulerCard, EngineCard, MonitorCard, ApiUsageCard
  - Phase 2: QuickActionsCard, SignalsCard
  - Phase 3: PositionsCard
- [x] **Refactor `warrior.tsx`** — Reduced from 1845 to ~481 lines (74% reduction, Jan 18)
  - Extracted 12 card components to `components/warrior/`
  - Created `useWarriorData` and `useWarriorActions` hooks
  - Added `formatters.ts` and `types.ts` utilities
  - See [modular_dashboard_pattern.md](file:///C:/Users/ftbbo/.gemini/antigravity/knowledge/nexus2_core_systems/artifacts/implementation/modular_dashboard_pattern.md)

---

## 📋 Audit Items

- [x] **ADR showing 0.0% — FIXED** — Root cause: `unified.py:75` had `>= 50` threshold
  - **Fix (Jan 7):** Changed to dynamic `>= min(10, limit//2)` - commit `14eb988`
  - FMP was returning valid 25-bar data but unified adapter incorrectly fell back to Alpaca (1 bar)
- [x] **DB session context managers — COMPLETE** — All routes now use `with get_session() as db:`
  - Created `get_session()` in database.py
  - Refactored all 29 instances across routes/
- [x] **`orders_filled` increment timing — FIXED** — Implemented Position State Machine (Jan 11)
  - Created `PositionStatus` enum with 6 states: `pending_fill`, `open`, `scaling`, `partial`, `closed`, `rejected`
  - Orders now start as `pending_fill`, transition to `open` only on confirmed fill
  - `orders_filled` only incremented when `result.status == "filled"`
  - Added 30-test suite for state transitions
- [ ] **API server restart** — Test ability to restart uvicorn from API without manual intervention
- [x] **Hardcoded values to settings** — max_trades_per_cycle, sim_initial_cash now configurable
- [x] **Scanner version tracking — ALREADY IMPLEMENTED** — Git hash captured in `scanner_settings` JSON
  - `execution_handler.py:120-137` captures commit hash at trade time
  - Stored in `PositionModel.scanner_settings` for each position
- [x] **Rejection logging — COMPLETE (v0.1.1)** — File-based logging with API endpoint
  - `rejection_tracker.py` - thread-safe, persists last 500 rejections
  - EP scanner integrated; `/automation/scheduler/rejections` endpoint added
- [ ] **Warrior/Broker Sync Audit** — Multiple edge cases discovered (Jan 16)
  - [x] Ghost positions in DB (EVTV) — Fixed: `close_orphaned_trades` now called on startup
  - [ ] Position below stop on sync skipped but not exited (RIOT $19.06 < $19.07)
  - [ ] Frontend shows stale positions (cache issue) — needs hard refresh
  - [ ] P&L discrepancy between UI (-$2.70) vs Alpaca (-$25.02)
  - [x] **Order ID Linkage Fix** — Root cause of data loss (Jan 17)
    - Sync now recovers existing position_id from warrior_db
    - Preserves original trigger_type through restarts
    - See [order_id_linkage_plan.md](file:///C:/Users/ftbbo/.gemini/antigravity/brain/0f443798-c140-4d29-99fc-fc284a48b8cf/order_id_linkage_plan.md)
  - Root cause: Multiple data sources (in-memory monitor vs warrior_db vs broker)

---

## 📝 UI / UX

- [x] **API Usage card sync** — Verified: shows real FMP rate limit stats
- [x] **Total P&L % in Open Positions** — Already implemented (per-row + total)
- [ ] **Simulation Control Page** — Mock market GUI with clock, scenarios, event log → [Plan](docs/simulation_plan.md)
- [x] **Countdown Timer to Next Scan** — Shows time until next scan, smart weekend/holiday labels (Jan 10)
- [x] **Score Breakdown Display** — Hover tooltip on quality score shows RS%, stop%, tier (Jan 10)
- [ ] **Trade Details Deep Link** — Discord notifications link to `/trade/{id}` page with full trade history
  - Entry/exit timeline, scanner settings at entry, P/L breakdown by partial
- [x] **API Usage card not showing on VPS — FIXED** — Used Next.js proxy for API routing (commit `f199f7d`)
- [x] **Column totals on Open Positions table** — Footer row with Cost Basis, Value, P/L totals (Jan 10)
- [x] **Scheduler Last Run shows UTC — FIXED** — Now displays ET with label (Jan 10)
- [ ] **Account-Strategy Locking** — Lock navbar account dropdown to specific strategies (e.g., Account A for NAC, Account B for Warrior) to prevent accidental mixing
- [ ] **Connection Status Indicator** — Visual badge + smart event logging for backend connectivity
  - Show 🟢/🔴 badge near Refresh button for current connection state
  - Only log transitions: "❌ Failed to connect" → "✅ Connection restored"
  - Avoids log spam from repeated poll failures
- [x] **Trade History / Events Log Pagination** — Scrollable container (400px max-height) for Trade History table (Jan 14)
  - Fixed-height scrollable container shows all trades without long page scroll
- [ ] **Quality Indicator Lights** — Traffic light indicators for Warrior Watchlist & Positions cards (Jan 17)
  - Watchlist: 6 indicators (Float, RVol, Gap, Catalyst, VWAP, Entry) with tooltips
  - Positions: 8 health indicators (MACD, 9/20/200 EMA, VWAP, Volume, Stop, Target)
  - Based on Ross Cameron's methodology from "7 Candlestick Patterns" video
  - See [implementation_plan.md](file:///C:/Users/ftbbo/.gemini/antigravity/brain/0f443798-c140-4d29-99fc-fc284a48b8cf/implementation_plan.md)
  - Prevents needing to scroll past long event lists to see AI analysis
- [ ] **Smart Scheduler Interval Change** — When interval is reduced, run scan immediately if time_remaining > new_interval
- [ ] **GUI Interval Validation Fix** — Frontend rejects 5-minute interval but backend accepts [5, 10, 15, 30]

---

## 🧪 Scanner Improvements

- [x] **RS percentile calculation** — Added 6M (126d) per KK methodology
- [ ] **Setup classification tags** — Each scanner tags its type: ep, breakout, htf, flag
- [ ] **Full E2E simulation test** — After fixing HTF signal conversion
- [ ] **RVOL filtering for Breakout scanner** — Per KK methodology, breakouts should require 2-3x average volume
  - Currently only EP scanner uses RVOL; Breakout/HTF do not check volume
- [x] **ERAS miss (Jan 7) — FIXED** — Added healthcare/investor conference catalyst patterns (commit `7779556`)
  - Root cause: "Present at J.P. Morgan Healthcare Conference" didn't match catalyst regex
  - Solution: Added patterns for healthcare/investor conferences, presenting at conferences
- [ ] **FMP Rate Limit Retry Queue** — Symbols that fail due to 429 errors should be queued for retry
  - Priority retry when rate limits clear
  - Staggered API requests to avoid hitting limits
  - Cross-strategy rate limit awareness (VPS KK + local Warrior share quota)
- [x] **Former Runner Score Boost** — Use former runner as score boost, not catalyst bypass (Jan 13)
  - Require real catalyst (news/earnings) to pass scanner ✅
  - If stock also has former-runner status → add +1 to quality score ✅
  - Former runner alone → still reject (no catalyst bypass) ✅
  - Per Ross Cameron research: former runner increases conviction when catalyst exists
- [x] **NAC P&L Calculation Fix** — NAC positions now correctly record realized_pnl on close (Jan 14)
  - Fixed broker sync and execute_monitor_exit to calculate P&L
- [ ] **IPO Calendar Integration** — Detect and trade newly-listed stocks (Ross Cameron trades IPOs)
  - Add FMP `/api/v3/ipo_calendar` endpoint to `fmp_adapter.py`
  - IPO catalyst score: Day 1 = +2, Days 2-7 = +1, Days 8-14 = +0
  - Tiered stop logic based on days since IPO
- [ ] **S-3 Shelf Filing Detection** — Score penalty for dilution risk (not disqualifier)
  - Add FMP `/api/v3/sec_filings/{SYMBOL}?type=S-3` endpoint
  - Recent S-3 (< 30 days) = -2, Active (30-365 days) = -1
  - News about shelf offering = still hard reject (existing behavior)
- [ ] **NAC P&L Backfill Script** — Recalculate P&L for Jan 2-14 positions from stored entry/exit prices
- [ ] **Dedicated Log Files** — Separate logs for easier debugging (append mode, persist across restarts)
  - `warrior_trades.log` - All entries/exits/P&L events
  - `warrior_scaling.log` - Scale operations with PSM transitions
  - `errors.log` - All errors across strategies

---

## 🎯 Warrior Trading Strategy (Ross Cameron)

> Day trading methodology: Low-float momentum, gap-and-go setups. [Full Guide](~/.gemini/antigravity/knowledge/trading_strategies_reference/artifacts/strategies/warrior_trading/warrior_trading_strategy_guide.md)

- [ ] **WarriorScanner** — Low-float momentum scanner
  - [ ] Float filtering (requires FMP extension)
  - [ ] RVOL calculation (time-of-day adjusted)
  - [ ] Pre-market highs monitoring
  - [ ] MACD (12, 26, 9) indicator
  - [ ] VWAP for pullback entries
- [ ] **WarriorMonitor** — Day trade management (different from KK swing)
  - [ ] 1-minute ORB at 9:30 AM
  - [ ] Multi-session ORB (4am, 6am, 7am)
  - [ ] 10:00 AM exit time priority
  - [ ] First red 5-min candle exit signal
- [x] **Spread Management** — Bid/ask spread considerations for cleaner execution (Jan 12)
  - [x] Spread exit trigger (exit if spread > 3% after grace period)
  - [x] Bid-based limit exits for illiquid stocks
  - [x] Escalating exit ladder for after-hours (2-10% below bid)
  - [x] Wide spread filter at entry (reject if spread > 3% of price) ✅ Jan 13
  - [x] Slippage tracking — `[Warrior Slippage]` logging + event service support (Jan 13)
- [ ] **Manual Close Button (GUI)** — Add close button to position cards for manual liquidation
- [ ] **Multi-Account Support** — Alpaca Account B isolation for day trades
- [x] **Full Auto-Enable on Startup** — Callbacks, position sync, and recently_exited now auto-wire on server start (Jan 12)
- [x] **Settings Persistence** — Persists to `data/warrior_settings.json` (scan interval, risk/trade, max_positions, etc.)
- [x] **Trade Log Persistence** — Store entry/exit events to DB for restart recovery with accurate metrics
- [x] **Integrate Warrior with Position State Machine** — Commits `164ebab`, `910f2f8`, `6196dbe`
  - [x] Add PENDING_EXIT state to prevent duplicate exits (Jan 11)
  - [x] PositionStatus enum with SCALING, PARTIAL, PENDING_EXIT states
  - [x] Valid transition matrix enforces lifecycle invariants
  - [x] Unit tests in `test_position_state_machine.py`
  - [x] `warrior_db.py` uses PSM status values (Jan 13)
  - [x] **Full refactor**: removed `_pending_exits` dict, DB is single source of truth (Jan 13)
- [x] **Trade Event Log** — Audit trail for all position changes (stop moves, partials, breakeven adjustments) (Jan 13)
  - [x] `trade_events` table with event_type, old_value, new_value, timestamp
  - [x] Persist stop updates to DB when monitor moves stop
  - [x] Event replay for full state recovery after restart
  - [x] `/trade-events/position/{id}` and `/trade-events/symbol/{symbol}` endpoints
- [x] **Scaling In** — Add to winners on first pullback (Ross Cameron methodology) (Jan 13)
  - [x] Detection logic and settings (v1)
  - [x] Order execution and PSM integration (v2)
  - [x] Callback wiring for sim/broker (v3)
  - [x] API endpoints: GET/PUT /monitor/settings
  - [x] GUI toggle (clickable Scale badge) + persistence
  - [ ] Improve toggle UX: proper checkbox/switch instead of clickable ❌/✅ badge
- [x] **Cancel Orders Endpoint** — `DELETE /warrior/orders/{symbol}` for manual cancellation (Jan 13)
- [x] **Prevent Duplicate Entries** — Track `_pending_entries` to block re-entry while buy order pending (Jan 13)
- [x] **Fix Startup Callback Wiring** — `object of type 'decimal.Decimal' has no len()` blocks auto-start (Jan 13)
- [x] **Performance Dashboard** — `/warrior-performance` page with PSM status badges (Jan 13)
  - [x] Summary stats (wins, losses, win rate, total P&L)
  - [x] Active positions with PSM badges
  - [x] Trade history table with symbol, date, status filters
  - [x] Expandable rows with trade event timeline
  - [x] Schwab-style metrics: Total Proceeds, Cost Basis, Gain/Loss Ratio gauge (Jan 13)
- [x] **Schwab API for Quotes** — Use Schwab Market Data API for bid/ask fallback when Alpaca fails
  - [x] Create SchwabAdapter with OAuth 2.0 token management (Jan 13)
  - [x] Add `/schwab/auth-url`, `/schwab/callback`, `/schwab/status` endpoints
  - [x] Harden Monitor Price Checks: Schwab fallback for exit/stop price checks (Jan 13)
  - [x] 3-Source Quote Verification: Alpaca + FMP + Schwab cross-validation (Jan 16)
  - [ ] Seamless OAuth: Auto-refresh reminder (Discord/email alert before 7-day expiry)
  - [ ] Seamless OAuth: OAuth proxy via nginx HTTPS for direct VPS callback
  - [ ] Seamless OAuth: One-click weekly re-auth workflow
- [ ] **Refactor warrior_routes.py** — Split 2000+ line file for maintainability
  - [ ] Extract sim mode callbacks to `warrior_sim_routes.py`
  - [ ] Extract broker callbacks to `warrior_broker_routes.py`
  - [ ] Keep core endpoints (status, start, stop, config) in main file
- [x] **Refactor warrior.tsx** — DONE (see Technical Debt section above)
- [ ] **Configure Gemini MCP** — Set up Gemini API key for AI-assisted UI generation

---

## 🧪 R&D Labs (Low Priority)

> Experimental multi-agent AI system for autonomous strategy discovery and optimization.

- [ ] **Strategy Discovery Engine** — Multi-Agent AI system with feedback loop
  - Autonomous exploration of alternative scan modes and strategies
  - Self-evaluating agents that test, score, and iterate on trading patterns
  - Feedback loop from live/sim results to refine discovery
- [ ] **User-Defined Momentum Screener** — TradingView-style filter (RSI>80, 1M>25%, stacked MAs)
  - [Spec](.agent/rules/user-defined-momentum-screener.md)
- [ ] **Backtesting Framework** — Historical signal validation with P&L simulation

---

## 🔮 Future / Low Priority

- [ ] **Equity Curve & Drawdown Charts** — Visualize portfolio performance over time
- [ ] **Calendar Heatmap** — Daily P&L visualization
- [ ] **Async RS Refresh** — Background job for RS universe refresh (non-blocking)

---

## ✅ Completed (Recent)

### Jan 16, 2026 — Timezone Compliance & Quote Verification
- [x] **3-Source Quote Verification** — Alpaca + FMP + Schwab cross-validation
  - Detects >20% price divergence, uses Schwab as trusted source
  - Prevents phantom trades from stale/corrupt Alpaca pre-market quotes
  - Batch quote callback now uses UnifiedMarketData with validation
- [x] **Timezone Compliance Sweep** — 6 fixes across codebase
  - `warrior_monitor.py`: Schwab fallback comparison
  - `trade_event_service.py`: SPY MA OHLCV attribute access
  - `schwab_adapter.py`: Token expiry timezone-aware when loaded
  - `monitor.py`: NAC opened_at timezone-aware for days_held calc
- [x] **Schwab Token Refresh** — Fixed expired token detection during pre-market

### Jan 8, 2026 — v0.1.1 through v0.1.13
- [x] **v0.1.13** — EOD timezone fix + observability improvements
  - Fixed `is_eod_window` to use Eastern Time (VPS runs on UTC)
  - `/health` now shows actual broker mode instead of hardcoded "sim"
  - Added `eastern_time` to `/health` and `/scheduler/status`
  - New `PATCH /scheduler/eod-window` endpoint for testing EOD window
- [x] **v0.1.12** — Diagnostics visible without scheduler, collapse states persist, scanner log export
- [x] **v0.1.11** — CSV export for Open Positions and Trade Log (📥 buttons)
- [x] **v0.1.10** — Scanner progress indicators (25%/50%/75% logging)
- [x] **v0.1.9** — DB-backed re-entry cooldown (restart resilient)
- [x] **v0.1.8** — Hybrid cooldown (30 min + price recovery)
- [x] **v0.1.7** — NAC settings exposed in status endpoint (transparency fix)
- [x] **v0.1.6** — `scanner_version` + `tag` columns in positions table
- [x] **v0.1.5** — No trailing stop on Day 0 (require entry to be D+1 before trailing)
- [x] **v0.1.4** — Exit deduplication (prevent double-counting partials)
- [x] **v0.1.3** — Position sync endpoint (`POST /positions/sync`)
- [x] **v0.1.2** — Monitor callbacks for position updates
- [x] **v0.1.1** — Rejection logging with file-based tracker

### Earlier
- [x] **MA Check Exit Logic** — Fixed order submission, broker reference, character change exits
- [x] **Position Enrichment Script** — `scripts/enrich_positions.py` repairs orphaned position metadata
- [x] **Simulation Entry Time Tracking** — MockPosition tracks actual opened_at for correct days_held
- [x] Sim mode display on page load
- [x] MA stacking filter in breakout scanner (price > SMA10 > SMA20 > SMA50)
- [x] Monitor auto-start with scheduler (await fix + singleton unification)
- [x] Button alignment on control cards (flexbox)
- [x] Graceful shutdown (Ctrl+C handling)
- [x] Singleton cleanup
- [x] EP Scanner infrastructure (catalyst patterns, CatalystType.NEWS, opening range)

