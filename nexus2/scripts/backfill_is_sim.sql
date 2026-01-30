-- Backfill is_sim flag with multi-layer heuristics
-- Run: sqlite3 ~/Nexus2/data/warrior.db < backfill_is_sim.sql
-- 
-- HEURISTICS:
-- 1. Mock Market implemented Jan 1, 2026
-- 2. Trades BEFORE Jan 1 = definitely LIVE
-- 3. Trades after 8pm EST = definitely SIM (market closed)
-- 4. Trades matching Alpaca orders = LIVE
-- 5. Known test case runs = SIM
-- 6. Everything else = NULL (unknown)

-- Step 1: Reset all to NULL
UPDATE warrior_trades SET is_sim = NULL;

-- Step 2: Pre-Jan 1, 2026 = LIVE (Mock Market didn't exist)
UPDATE warrior_trades SET is_sim = 0 WHERE date(entry_time) < '2026-01-01';

-- Step 3: After 8pm EST = SIM (market closed, must be simulation)
-- entry_time is stored in UTC, 8pm EST = 01:00 UTC next day (winter) or midnight
-- Being conservative: anything with time > 01:00 UTC on same day is after-hours
UPDATE warrior_trades SET is_sim = 1 
WHERE time(entry_time) > '01:00:00' 
  AND date(entry_time) >= '2026-01-01';

-- Step 4: Mark LIVE trades (Alpaca ground truth) - OVERRIDES after-hours if needed
-- Jan 29, 2026
UPDATE warrior_trades SET is_sim = 0 WHERE symbol IN ('TNMG', 'HIND', 'VERO', 'PAVM', 'OCC', 'LCFY') AND date(entry_time) = '2026-01-29';

-- Jan 28, 2026
UPDATE warrior_trades SET is_sim = 0 WHERE symbol IN ('GXAI', 'UAVS', 'CXAI', 'LODE', 'XPON', 'AI') AND date(entry_time) = '2026-01-28';

-- Jan 27, 2026
UPDATE warrior_trades SET is_sim = 0 WHERE symbol IN ('PLUR', 'MTC', 'FLYE', 'GV', 'MVO') AND date(entry_time) = '2026-01-27';

-- Jan 26, 2026
UPDATE warrior_trades SET is_sim = 0 WHERE symbol IN ('ALLR', 'RVSN', 'PRTG', 'TTNP') AND date(entry_time) = '2026-01-26';

-- Jan 24, 2026
UPDATE warrior_trades SET is_sim = 0 WHERE symbol IN ('TTNP', 'CLOV') AND date(entry_time) = '2026-01-24';

-- Jan 23, 2026
UPDATE warrior_trades SET is_sim = 0 WHERE symbol IN ('CLOV', 'TTNP', 'PRTG', 'ELEV') AND date(entry_time) = '2026-01-23';

-- Jan 22, 2026
UPDATE warrior_trades SET is_sim = 0 WHERE symbol IN ('DPRO', 'TTNP', 'PRTG', 'CLOV', 'ELEV') AND date(entry_time) = '2026-01-22';

-- Jan 21, 2026
UPDATE warrior_trades SET is_sim = 0 WHERE symbol IN ('LGMK', 'ARQQ', 'ELEV', 'PRTG') AND date(entry_time) = '2026-01-21';

-- Jan 17, 2026
UPDATE warrior_trades SET is_sim = 0 WHERE symbol IN ('BNZI', 'CTNT', 'TTNP', 'ZENA', 'LUNR') AND date(entry_time) = '2026-01-17';

-- Jan 16, 2026
UPDATE warrior_trades SET is_sim = 0 WHERE symbol IN ('TTNP', 'ZENA', 'BNZI', 'LUNR', 'FCEL') AND date(entry_time) = '2026-01-16';

-- Jan 15, 2026
UPDATE warrior_trades SET is_sim = 0 WHERE symbol IN ('EVTV', 'BNKK', 'IBRX', 'RFIL', 'SYPR') AND date(entry_time) = '2026-01-15';

-- Jan 14, 2026
UPDATE warrior_trades SET is_sim = 0 WHERE symbol IN ('SYPR', 'RPID', 'CLSK', 'CRML', 'CERS', 'KULR', 'YYAI', 'ALTS', 'ROLR', 'INFY', 'CLOV', 'IBRX', 'RCT', 'BEEM', 'ERAS') AND date(entry_time) = '2026-01-14';

-- Jan 13, 2026
UPDATE warrior_trades SET is_sim = 0 WHERE symbol IN ('MVO', 'GV', 'ERAS', 'BDSX', 'IPST', 'IOTR', 'AHMA', 'XAIR', 'BCTX', 'PMAX', 'EVTV', 'DBGI', 'RCAT', 'ATON', 'PDYN', 'UAVS', 'ASTI', 'MRNO', 'TE', 'OESX', 'RVYL', 'NCNA', 'OSS', 'HIVE', 'HSDT', 'NVA', 'SIDU', 'ONDS', 'IMSR', 'NUKK', 'VLN', 'IRE', 'WATT', 'NUAI', 'BITF', 'MPL', 'ALTS', 'IBRX') AND date(entry_time) = '2026-01-13';

-- Jan 12, 2026
UPDATE warrior_trades SET is_sim = 0 WHERE symbol IN ('SOGP', 'EVTV', 'IMSR', 'OSS', 'SDOT', 'BKKT', 'BIOA', 'DAWN', 'IRE', 'BDSX', 'ZBIO', 'AIRS', 'LVLU', 'IPWR', 'CLRB', 'AMPG', 'SLS', 'OPTX', 'UUU', 'GNPX', 'MVO', 'VLN') AND date(entry_time) = '2026-01-12';

-- Jan 9, 2026
UPDATE warrior_trades SET is_sim = 0 WHERE symbol IN ('ZNTL', 'ASPI', 'COMP', 'MLTX', 'ERAS', 'NBY', 'VLN', 'OKYO', 'SGMT', 'CETX', 'OPAD') AND date(entry_time) = '2026-01-09';

-- Step 5: Verification
SELECT 
    CASE 
        WHEN is_sim = 0 THEN 'LIVE'
        WHEN is_sim = 1 THEN 'SIM'
        ELSE 'UNKNOWN'
    END as mode,
    COUNT(*) as trade_count
FROM warrior_trades 
GROUP BY is_sim;
