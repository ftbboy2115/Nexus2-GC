# Nexus 2 Logging Structure

This document describes the logging files used by the Nexus 2 platform.

## Active Logs

| Log File | Location | Purpose | Rotation |
|----------|----------|---------|----------|
| `automation.log` | `nexus2/logs/` | NAC (KK-style) automation: scanner results, position sizing, trade execution | Daily, 7 days |
| `warrior_scan.log` | Root + `data/` | Warrior Trading scanner: PASS/FAIL results with gap%, RVOL, score | None |
| `startup.log` | Root | Server startup and initialization | Overwritten on restart |
| `lab.log` | `nexus2/logs/` | R&D Lab: backtest runner, historical loader, orchestrator, agents | **(Planned)** |

## Archived/Orphaned Logs

These files exist but have **no active code references**. Safe to delete or ignore:

- `data/ep_auto.log` - Legacy EP scanner log
- `data/scanner_auto.log` - Legacy general scanner log  
- `data/sniper.log` - Legacy sniper mode log
- `data/strategy_errors.log` - Legacy strategy error log

## Log Locations

```
nexus2/
├── logs/                    # Primary log directory
│   └── automation.log       # NAC automation
├── data/
│   └── warrior_scan.log     # Warrior scanner (copy)
├── warrior_scan.log         # Warrior scanner (primary)
└── startup.log              # Server startup
```

## Log Formats

### automation.log (NAC)
```
2026-01-22 09:35:01 | INFO | SCAN_START | modes=['ep','breakout'] | min_quality=6
2026-01-22 09:35:02 | INFO | SCAN_COMPLETE | signals=3 (EP:2, BO:1, HTF:0) | duration=1200ms
2026-01-22 09:35:02 | INFO |   SIGNAL | AAPL | type=ep | entry=$150.25 | stop=$149.50 | quality=8
2026-01-22 09:35:05 | INFO | TRADE_EXECUTED | AAPL x 100 @ stop=$149.50 | order_id=abc123
```

### warrior_scan.log (Warrior)
```
2026-01-22 07:30:15 | PASS | XAIR | Gap:142.0% | RVOL:753.0x | Score:4
2026-01-22 07:30:16 | FAIL | TEST | Reason: float_too_high | Float: 150,000,000 > 100,000,000
2026-01-22 07:30:20 | SCAN END | Processed: 31 | Passed: 15 | Candidates: PDYN,AHMA,...
```

## Usage

### View NAC automation logs
```bash
tail -f nexus2/logs/automation.log
```

### View Warrior scanner logs  
```bash
tail -f warrior_scan.log
```

### View logs on VPS
```bash
ssh root@<VPS_IP> "tail -f ~/Nexus2/warrior_scan.log"
```

---
*Last updated: Jan 22, 2026*
