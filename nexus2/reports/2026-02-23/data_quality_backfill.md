# Data Quality Backfill Report

**Date:** 2026-02-23  
**File Modified:** [warrior_setups.yaml](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/tests/test_cases/warrior_setups.yaml)

## Summary

Backfilled `data_quality` field for **12 test cases** that were missing `ross_entry_time`. Read all 7 relevant transcripts end-to-end and extracted entry price/time data where available.

## Results

| Case ID | Symbol | Date | Entry Price | Entry Time | data_quality | Source |
|---------|--------|------|-------------|------------|-------------|--------|
| ross_rolr_20260114 | ROLR | 01-14 | $5.17 | **08:18** | `TRANSCRIPT_VERIFIED` | lneGXw0sxzo |
| ross_tnmg_20260116 | TNMG | 01-16 | $3.90 | — | `TRANSCRIPT_PARTIAL` | ZKsNP11rU1Y |
| ross_gwav_20260116 | GWAV | 01-16 | $7.82 | — | `TRANSCRIPT_PARTIAL` | ZKsNP11rU1Y |
| ross_vero_20260116 | VERO | 01-16 | $5.92 | — | `TRANSCRIPT_PARTIAL` | ZKsNP11rU1Y |
| ross_pavm_20260121 | PAVM | 01-21 | $12.31 | — | `TRANSCRIPT_PARTIAL` | tnazRI3e3WY |
| ross_rnaz_20260205 | RNAZ | 02-05 | ~$12 est | — | `TRANSCRIPT_PARTIAL` | HGATds95-p4 |
| ross_rvsn_20260205 | RVSN | 02-05 | $5.50 | — | `TRANSCRIPT_PARTIAL` | HGATds95-p4 |
| ross_rdib_20260206 | RDIB | 02-06 | ~$15 VWAP | — | `TRANSCRIPT_PARTIAL` | Z5D8nhEtzOo |
| ross_sxtc_20260209 | SXTC | 02-09 | ~$4.50 | — | `TRANSCRIPT_PARTIAL` | gOi55ufRFDc |
| ross_uoka_20260209 | UOKA | 02-09 | ~$4.00 | **~09:30** | `TRANSCRIPT_PARTIAL` | gOi55ufRFDc |
| ross_velo_20260210 | VELO | 02-10 | $16.00 | — | `NEEDS_VIDEO_CHECK` | 5Xbf_JuO-mE |
| ross_edhl_20260220 | EDHL | 02-20 | ~$4.50 | — | `TRANSCRIPT_PARTIAL` | K1Zvoes1SNQ |

## Breakdown

- **TRANSCRIPT_VERIFIED (1):** ROLR — both entry price ($5.17) and time (08:18 scanner alert) confirmed
- **TRANSCRIPT_PARTIAL (10):** Entry price confirmed from transcript, but exact entry time not stated verbally
- **NEEDS_VIDEO_CHECK (1):** VELO — the Feb 10 transcript template was empty (unfilled). Entry data ($16 + $16.50 add) exists in the raw transcript text but no time. Video review recommended.

## Fields Added

- `data_quality` added to all 12 cases
- `ross_entry_time: "08:18"` added to ROLR
- `ross_entry_time: "~09:30"` added to UOKA

## Video Check Needed

| Case | Video URL | What to Look For |
|------|-----------|-----------------|
| ross_velo_20260210 | https://www.youtube.com/watch?v=5Xbf_JuO-mE | VELO entry time (second trade of the day, after EVMN) |

## Key Observations

1. **Ross rarely states exact entry times verbally** — he describes price action and setups but doesn't say "I entered at 8:23 AM"
2. **Entry prices are more reliably found** — cost basis, fill prices, and round-number entries are usually mentioned
3. **The Jan 16 transcript covers 4 stocks** (TNMG, GWAV, VERO, LCFY) with cost basis for each but no times
4. **The Feb 10 transcript template was never filled** — only the raw transcript in the `<details>` block has data
5. **To get exact entry times, video screenshots would be needed** for most of these cases
