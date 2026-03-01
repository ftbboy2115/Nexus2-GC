# Handoff: Batch Settings Separation

**Agent:** Backend Specialist  
**Priority:** P1  
**Date:** 2026-03-01

---

## Problem

The batch runner (`sim_context.py`) loads settings from `data/warrior_settings.json` — the same file the live engine and GUI use. This caused a $139K batch divergence when Windows and VPS had different settings. The batch runner needs to use a committed, version-controlled settings file instead.

---

## Changes Required

### File: `nexus2/adapters/simulation/sim_context.py`

**At lines 64-72**, change the batch runner to load from `warrior_settings_batch.json` instead of `warrior_settings.json`:

**Before:**
```python
        # Load saved engine settings so concurrent runner uses same config as sequential
        try:
            from nexus2.db.warrior_settings import load_warrior_settings, apply_settings_to_config
            saved_engine_settings = load_warrior_settings()
```

**After:**
```python
        # Load BATCH settings (committed, version-controlled) — NOT the live settings
        try:
            from nexus2.db.warrior_settings import apply_settings_to_config
            import json
            from pathlib import Path
            batch_settings_file = Path(__file__).parent.parent.parent / "data" / "warrior_settings_batch.json"
            if batch_settings_file.exists():
                with open(batch_settings_file, 'r') as f:
                    saved_engine_settings = json.load(f)
                log.info(f"[SimContext] Loaded batch settings from {batch_settings_file}")
            else:
                log.warning(f"[SimContext] Batch settings not found at {batch_settings_file}, using defaults")
                saved_engine_settings = None
```

The rest of the block (`apply_settings_to_config(engine.config, saved_engine_settings)` and `engine.config.sim_only = True`) stays the same.

---

## Verification

```powershell
# 1. Run full test suite
python -m pytest nexus2/tests/ -x --tb=short -q

# 2. Verify batch settings file exists
Test-Path "data\warrior_settings_batch.json"

# 3. Run batch test and confirm total_pnl matches $437,558 baseline
# (Run locally — the committed batch file has 40K shares, 1min bars, 20 positions)
```

---

## Deliverable

Backend status report at `nexus2/reports/2026-03-01/backend_status_batch_settings_separation.md`
