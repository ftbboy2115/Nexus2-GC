# Nexus 2 Changelog

All notable changes to this project are documented in this file.

Format: `[commit] YYYY-MM-DD - Description`

---

## 2026-01-07

- `f926f61` 2026-01-07 - Fix column editor: maximized view respects saved column order
- `a148070` 2026-01-07 - Fix column editor: call openEditor() when showing modal
- `548b21d` 2026-01-07 - Add all columns (today_pnl, days_held, stop_price) to layout editor
- `c301618` 2026-01-06 - Fix days calculation to use calendar days
- `bf16dad` 2026-01-06 - Update column headers, add Today's P/L ($), grey for 0 values

---

## 2026-01-06

- `[various]` 2026-01-06 - Zero Signal Anomaly fix: Hardened MA check maturity logic with `max(min_days, 5)`
- `[various]` 2026-01-06 - Added Today's P/L telemetry from Alpaca's `unrealized_intraday_pl`

---

## 2026-01-02

- `1c9f27a` 2026-01-02 - **CRITICAL:** Tighten breakout scanner: require MA stacking (price > SMA10 > SMA20 > SMA50)
  - Fixes: Rejects downtrend bounces that don't meet KK criteria
  - Note: Trades before this commit (same day) were taken without this check
- `6be7747` 2026-01-02 - Enforce price > 20 SMA for flag breakouts
- `9e0f0e2` 2026-01-02 - Add RS Percentile Service with true percentile ranking

---

## Earlier Commits

See `git log --oneline` for full history.

---

## Post-Mortem Notes

### Jan 7, 2026 - 7 Position Cleanup

**Affected positions:** CMCSA, CP, MDLZ, PBR, T, WBD, WMB

**Root cause:** These trades were entered on Jan 2, 2026 BEFORE commit `1c9f27a` added MA stacking enforcement. 6 of 7 did not have properly stacked MAs at entry.

**Resolution:** 
- Positions marked with `source: nac-pre-ma-fix`
- Queued for close at market open Jan 7
- Scanner now enforces MA stacking to prevent recurrence
