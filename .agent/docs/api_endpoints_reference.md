# Nexus 2 API Reference

**Version**: 0.2.9  
**Spec**: OAS 3.1  
**OpenAPI**: `/openapi.json`

## Analytics
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/analytics/by-setup` | Get By Setup |
| GET | `/analytics/quick-stats` | Get Quick Stats |
| GET | `/analytics/summary` | Get Summary |
| GET | `/analytics/trades` | Get Trade History |

## Audit
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/audit/approve/{symbol}/alpaca` | Approve Alpaca |
| POST | `/audit/approve/{symbol}/fmp` | Approve Fmp |
| GET | `/audit/blacklist` | Get Blacklist |
| POST | `/audit/blacklist/{symbol}` | Add To Blacklist |
| DELETE | `/audit/blacklist/{symbol}` | Remove From Blacklist |
| GET | `/audit/pending` | Get Pending Approvals |
| POST | `/audit/quotes/cleanup` | Trigger Cleanup |
| GET | `/audit/quotes/daily-summary` | Get Daily Summary |
| GET | `/audit/quotes/providers` | Get Provider Reliability |
| GET | `/audit/quotes/recent` | Get Recent Audits |
| GET | `/audit/quotes/recommend-source/{time_window}` | Recommend Source |
| GET | `/audit/quotes/stats` | Get Divergence Stats |
| GET | `/audit/quotes/status` | Get Audit Status |
| GET | `/audit/quotes/symbols/{symbol}` | Get Symbol Audits |

## Automation
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/automation/api-stats` | Get Api Stats |
| POST | `/automation/ema-check` | Run Ema Check |
| POST | `/automation/execute` | Execute Signal |
| POST | `/automation/ipo/refresh` | Refresh Ipo Calendar |
| GET | `/automation/ipo/status` | Get Ipo Status |
| POST | `/automation/liquidate-all` | Liquidate All Positions |
| POST | `/automation/ma-check` | Run Ma Check |
| GET | `/automation/ma-check/status` | Get Ma Check Status |
| POST | `/automation/monitor/check` | Manual Check |
| POST | `/automation/monitor/start` | Start Monitor |
| GET | `/automation/monitor/status` | Get Monitor Status |
| POST | `/automation/monitor/stop` | Stop Monitor |
| POST | `/automation/nac-sync` | Sync Nac With Broker |
| POST | `/automation/pause` | Pause Engine |
| GET | `/automation/positions` | Get Broker Positions |
| POST | `/automation/resume` | Resume Engine |
| POST | `/automation/reverse-splits/refresh` | Refresh Reverse Splits |
| GET | `/automation/reverse-splits/status` | Get Reverse Split Status |
| POST | `/automation/rs/refresh` | Refresh Rs Universe |
| GET | `/automation/rs/status` | Get Rs Status |
| POST | `/automation/scan` | Trigger Scan |
| POST | `/automation/scan-all` | Scan All |
| POST | `/automation/scan_and_execute` | Scan And Execute |
| PATCH | `/automation/scheduler/auto-execute` | Toggle Auto Execute |
| GET | `/automation/scheduler/diagnostics` | Get Scheduler Diagnostics |
| PATCH | `/automation/scheduler/eod-window` | Update Eod Window |
| POST | `/automation/scheduler/force_scan` | Force Scheduler Scan |
| PATCH | `/automation/scheduler/interval` | Update Scheduler Interval |
| GET | `/automation/scheduler/rejections` | Get Rejections |
| GET | `/automation/scheduler/settings` | Get Scheduler Settings |
| PATCH | `/automation/scheduler/settings` | Update Scheduler Settings |
| GET | `/automation/scheduler/signals` | Get Scheduler Signals |
| POST | `/automation/scheduler/start` | Start Scheduler |
| GET | `/automation/scheduler/status` | Get Scheduler Status |
| POST | `/automation/scheduler/stop` | Stop Scheduler |
| POST | `/automation/start` | Start Engine |
| GET | `/automation/status` | Get Status |
| POST | `/automation/stop` | Stop Engine |
| POST | `/automation/sync-positions` | Sync Positions From Broker |
| POST | `/automation/test-discord` | Test Discord |

## Simulation
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/automation/simulation/advance` | Advance Simulation |
| GET | `/automation/simulation/broker` | Get Simulation Broker |
| GET | `/automation/simulation/debug` | Debug Simulation |
| POST | `/automation/simulation/debug_execute_path` | Debug Execute Path |
| GET | `/automation/simulation/diagnostic_htf` | Diagnostic Htf |
| POST | `/automation/simulation/diagnostic_scan` | Diagnostic Scan |
| POST | `/automation/simulation/diagnostic_unified_scan` | Diagnostic Unified Scan |
| POST | `/automation/simulation/inject_position` | Inject Position |
| POST | `/automation/simulation/load_historical` | Load Historical Data |
| POST | `/automation/simulation/load_htf_pattern` | Load Htf Pattern |
| POST | `/automation/simulation/load_test_case` | Load Test Case |
| GET | `/automation/simulation/positions` | Get Sim Positions |
| POST | `/automation/simulation/reset` | Reset Simulation |
| POST | `/automation/simulation/run_eod` | Run Simulation Eod |
| GET | `/automation/simulation/status` | Get Simulation Status |
| GET | `/automation/simulation/test_cases` | List Test Cases |

## Data Explorer
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/data/nac-trades` | Get Nac Trades |
| GET | `/data/scan-history` | Get Scan History |
| GET | `/data/trade-events` | Get Trade Events |
| GET | `/data/warrior-trades` | Get Warrior Trades |

## Health
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health Check |

## Lab
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/lab/agents/code` | Generate Code |
| POST | `/lab/agents/evaluate` | Evaluate Results |
| POST | `/lab/agents/research` | Generate Hypothesis |
| POST | `/lab/backtest` | Run Backtest |
| DELETE | `/lab/cache/clear` | Clear Cache |
| GET | `/lab/cache/status` | Lab Cache Status |
| POST | `/lab/compare` | Compare Strategies |
| POST | `/lab/experiment` | Run Experiment |
| GET | `/lab/experiment/{experiment_id}/status` | Get Experiment Status |
| GET | `/lab/health` | Lab Health |
| POST | `/lab/history/backfill` | Backfill Historical Gappers |
| GET | `/lab/history/stats` | Get Scan History Stats |
| GET | `/lab/strategies` | List Strategies |
| POST | `/lab/strategies` | Create Strategy |
| GET | `/lab/strategies/{name}` | Get Strategy |
| GET | `/lab/strategies/{name}/{version}` | Get Strategy Version |

## Orders
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/orders` | Create Order |
| GET | `/orders` | List Orders |
| GET | `/orders/{order_id}` | Get Order |
| DELETE | `/orders/{order_id}` | Cancel Order |
| POST | `/orders/{order_id}/submit` | Submit Order |

## Positions
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/positions` | List Positions |
| GET | `/positions/closed` | List Closed Positions |
| GET | `/positions/count` | Get Positions Count |
| POST | `/positions/sync` | Sync Positions |
| GET | `/positions/{position_id}` | Get Position |
| POST | `/positions/{position_id}/close` | Close Position |
| POST | `/positions/{position_id}/partial-exit` | Partial Exit |
| GET | `/positions/{position_id}/performance` | Get Position Performance |

## Preferences
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/preferences/{key}` | Get Preference |
| PUT | `/preferences/{key}` | Set Preference |

## Scanner
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/scanner/breakouts` | Scan Breakouts |
| POST | `/scanner/htf` | Scan Htf |
| GET | `/scanner/htf/{symbol}` | Get Htf Trend |
| GET | `/scanner/rate-stats` | Get Rate Stats |
| GET | `/scanner/results` | Get Scanner Results |
| POST | `/scanner/run` | Run Scanner |

## Settings
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/settings` | Read Settings |
| PUT | `/settings` | Update Settings |
| GET | `/settings/broker-status` | Get Broker Status |

## Trade
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/trade` | Quick Trade |

## Trade Events
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/trade-events/analyze-day` | Analyze Day Trades |
| POST | `/trade-events/analyze/{position_id}` | Analyze Trade |
| GET | `/trade-events/position/{position_id}` | Get Position Events |
| GET | `/trade-events/recent` | Get Recent Events |
| GET | `/trade-events/symbol/{symbol}` | Get Symbol Events |

## Warrior
| Method | Endpoint | Description |
|--------|----------|-------------|
| PATCH | `/warrior/auto-enable` | Set Warrior Auto Enable |
| POST | `/warrior/broker/close/{symbol}` | Close Warrior Position |
| POST | `/warrior/broker/enable` | Enable Warrior Broker |
| GET | `/warrior/broker/status` | Get Warrior Broker Status |
| POST | `/warrior/broker/test` | Test Warrior Broker |
| PUT | `/warrior/config` | Update Warrior Config |
| POST | `/warrior/db/backfill` | Backfill Warrior Trades |
| GET | `/warrior/diagnostics` | Get Warrior Diagnostics |
| GET | `/warrior/exit-mode` | Get Exit Mode |
| POST | `/warrior/exit-mode` | Set Exit Mode |
| POST | `/warrior/manual_exit` | Manual Exit Position |
| GET | `/warrior/monitor/settings` | Get Warrior Monitor Settings |
| PUT | `/warrior/monitor/settings` | Update Warrior Monitor Settings |
| GET | `/warrior/monitor/status` | Get Warrior Monitor Status |
| DELETE | `/warrior/orders/{symbol}` | Cancel Orders For Symbol |
| POST | `/warrior/pause` | Pause Warrior Engine |
| GET | `/warrior/positions` | Get Warrior Positions |
| GET | `/warrior/positions/count` | Get Warrior Positions Count |
| GET | `/warrior/positions/health` | Get Positions Health |
| POST | `/warrior/resume` | Resume Warrior Engine |
| GET | `/warrior/scanner/catalyst-audit` | Get Catalyst Audit Entries |
| GET | `/warrior/scanner/logs` | Get Warrior Scanner Logs |
| POST | `/warrior/scanner/run` | Run Warrior Scan |
| GET | `/warrior/scanner/settings` | Get Warrior Scanner Settings |
| PUT | `/warrior/scanner/settings` | Update Warrior Scanner Settings |
| GET | `/warrior/schwab/auth-url` | Get Schwab Auth Url |
| POST | `/warrior/schwab/callback` | Schwab Oauth Callback |
| GET | `/warrior/schwab/status` | Get Schwab Status |
| GET | `/warrior/sim/clock` | Get Clock Status |
| POST | `/warrior/sim/disable` | Disable Warrior Sim |
| POST | `/warrior/sim/enable` | Enable Warrior Sim |
| POST | `/warrior/sim/load_historical` | Load Historical Test Case |
| POST | `/warrior/sim/load_test_case` | Load Warrior Test Case |
| POST | `/warrior/sim/order` | Submit Warrior Sim Order |
| GET | `/warrior/sim/orders` | Get Sim Orders |
| PUT | `/warrior/sim/price` | Set Warrior Sim Price |
| POST | `/warrior/sim/reset` | Reset Warrior Sim |
| POST | `/warrior/sim/reset_clock` | Reset Clock To Open |
| POST | `/warrior/sim/sell` | Sell Warrior Sim Position |
| POST | `/warrior/sim/speed` | Set Playback Speed |
| GET | `/warrior/sim/status` | Get Warrior Sim Status |
| POST | `/warrior/sim/step` | Step Clock |
| POST | `/warrior/sim/step_back` | Step Clock Back |
| GET | `/warrior/sim/test_cases` | List Warrior Test Cases |
| POST | `/warrior/start` | Start Warrior Engine |
| GET | `/warrior/status` | Get Warrior Status |
| POST | `/warrior/stop` | Stop Warrior Engine |
| GET | `/warrior/trades` | Get Trade History |
| GET | `/warrior/trades/analytics` | Get Trade Analytics |
| GET | `/warrior/trades/discrepancies/report` | Get Discrepancies Report |
| GET | `/warrior/trades/{trade_id}` | Get Trade Detail |
| GET | `/warrior/watchlist` | Get Warrior Watchlist |

## Watchlist
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/watchlist` | Get Watchlist |
| POST | `/watchlist/add` | Add Candidate |
| DELETE | `/watchlist/clear/all` | Clear All Candidates |
| GET | `/watchlist/today` | Get Today Candidates |
| DELETE | `/watchlist/{symbol}` | Delete Candidate |
| PUT | `/watchlist/{symbol}/status` | Update Candidate Status |
