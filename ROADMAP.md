# Nexus 2 Roadmap

Last updated: 2026-01-08

> **Note:** This roadmap syncs with the Knowledge Item at `~/.gemini/antigravity/knowledge/nexus2_core_systems/`. AI should keep both in sync when making updates.

## Legend
- [ ] Not started
- [/] In progress
- [x] Completed

---

## 🔧 Features

- [x] **VPS Deployment** — DigitalOcean NYC, $6/mo, Tailscale secured (Jan 8)
- [x] **HTF Simulation Testing** — Verified: scanner works, added configurable extended threshold
- [x] **Liquidate All Button** — Quick exit for paper mode testing
  - Backend: `POST /automation/liquidate-all` endpoint
  - GUI: Button in Quick Actions with confirmation modal
- [x] **Project README** — Startup instructions (backend, frontend, env setup)
- [ ] **User Guide / Wiki** — How to use the system, operational playbook

---

## 🛠 Technical Debt

- [x] **Graceful Shutdown** — Two-stage Ctrl+C, FMP rate limit interruptible
- [x] **Ctrl+C x3 not stopping server — FIXED** — Counter-based approach with `sys.exit(0)` (commit `83b3f18`)
- [x] **Singleton Cleanup** — Removed duplicate `global _monitor`, use `get_monitor()`
- [x] **Extract `execute_callback`** — Moved to `execution_handler.py` + 3 more modules (65% reduction)
- [x] **`_sim_broker` thread safety** — Centralized in automation_state.py with threading.Lock

---

## 📋 Audit Items

- [x] **ADR showing 0.0% — FIXED** — Root cause: `unified.py:75` had `>= 50` threshold
  - **Fix (Jan 7):** Changed to dynamic `>= min(10, limit//2)` - commit `14eb988`
  - FMP was returning valid 25-bar data but unified adapter incorrectly fell back to Alpaca (1 bar)
- [x] **DB session context managers — COMPLETE** — All routes now use `with get_session() as db:`
  - Created `get_session()` in database.py
  - Refactored all 29 instances across routes/
- [ ] **`orders_filled` increment timing** — Verify correct increment logic
- [ ] **API server restart** — Test ability to restart uvicorn from API without manual intervention
- [x] **Hardcoded values to settings** — max_trades_per_cycle, sim_initial_cash now configurable
- [x] **Scanner version tracking — ALREADY IMPLEMENTED** — Git hash captured in `scanner_settings` JSON
  - `execution_handler.py:120-137` captures commit hash at trade time
  - Stored in `PositionModel.scanner_settings` for each position
- [x] **Rejection logging — COMPLETE (v0.1.1)** — File-based logging with API endpoint
  - `rejection_tracker.py` - thread-safe, persists last 500 rejections
  - EP scanner integrated; `/automation/scheduler/rejections` endpoint added

---

## 📝 UI / UX

- [x] **API Usage card sync** — Verified: shows real FMP rate limit stats
- [x] **Total P&L % in Open Positions** — Already implemented (per-row + total)
- [ ] **Simulation Control Page** — Mock market GUI with clock, scenarios, event log → [Plan](docs/simulation_plan.md)
- [ ] **Countdown Timer to Next Scan** — Show time remaining until next scheduler cycle
- [ ] **Score Breakdown Display** — Show how each signal got its quality score (which criteria contributed)
- [ ] **Trade Details Deep Link** — Discord notifications link to `/trade/{id}` page with full trade history
  - Entry/exit timeline, scanner settings at entry, P/L breakdown by partial
- [x] **API Usage card not showing on VPS — FIXED** — Used Next.js proxy for API routing (commit `f199f7d`)
- [ ] **Column totals on Open Positions table** — Sum columns (Value, P/L $, Today P/L $) in footer row, especially in maximized view
- [ ] **Scheduler Last Run shows UTC** — Should display ET for consistency

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
- [ ] **Multi-Account Support** — Alpaca Account B isolation for day trades
- [ ] **Settings Persistence** — Persist Warrior config to DB (scan interval, risk/trade, etc.)
- [ ] **Scaling In** — Add to winners on first pullback or intraday consolidation break

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

