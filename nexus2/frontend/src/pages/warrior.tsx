import { useState, useEffect, useCallback } from 'react'
import Head from 'next/head'
import Link from 'next/link'
import styles from '@/styles/Warrior.module.css'
import {
    CollapsibleCard,
    WarriorCandidate,
    ScanResult,
    PositionHealth,
    useWarriorData,
    useWarriorActions,
    formatCurrency,
    formatPnL,
    formatFloat,
    formatTime,
    sortData,
    toggleSort,
    SortHeader,
    SortConfig,
    EventLogCard,
    MockMarketCard,
    ExitRulesCard,
    SettingsCard,
    ScannerCard,
    EngineCard,
} from '@/components/warrior'

// ============================================================================
// Main Component
// ============================================================================


export default function Warrior() {
    // Core data from custom hook
    const {
        status,
        positions,
        positionHealth,
        scanResult,
        setScanResult,
        loading,
        simStatus,
        brokerStatus,
        tradeEvents,
        addToLog,
        eventLog,
        setEventLog,
        refetch,
    } = useWarriorData()

    // Action handlers from custom hook
    const {
        actionLoading,
        setActionLoading,
        startEngine,
        stopEngine,
        pauseEngine,
        resumeEngine,
        enableSim,
        resetSim,
        disableSim,
        enableBroker,
        toggleAutoEnable,
        updateConfig,
        handleAction,
    } = useWarriorActions({ addToLog, refetch, status })

    // Mock Market state
    const [testCases, setTestCases] = useState<{ id: string, symbol: string, description: string }[]>([])
    const [selectedTestCase, setSelectedTestCase] = useState<string>('')
    const [loadedTestCase, setLoadedTestCase] = useState<{ symbol: string, price: number } | null>(null)

    // Sorting state for tables
    const [watchlistSort, setWatchlistSort] = useState<{ key: string, dir: 'asc' | 'desc' }>({ key: 'gap_percent', dir: 'desc' })
    const [engineScanSort, setEngineScanSort] = useState<{ key: string, dir: 'asc' | 'desc' }>({ key: 'gap_percent', dir: 'desc' })

    // Countdown timer state
    const [countdown, setCountdown] = useState<string>('')

    // Trade events visibility
    const [showTradeEvents, setShowTradeEvents] = useState(() => {
        if (typeof window !== 'undefined') {
            return localStorage.getItem('warrior_showTradeEvents') === 'true'
        }
        return false
    })

    // Trade History (closed trades) with AI analysis
    const [tradeHistory, setTradeHistory] = useState<any[]>([])
    const [showTradeHistory, setShowTradeHistory] = useState(() => {
        if (typeof window !== 'undefined') {
            return localStorage.getItem('warrior_showTradeHistory') === 'true'
        }
        return false
    })
    const [analyzingTrade, setAnalyzingTrade] = useState<string | null>(null)
    const [tradeAnalysis, setTradeAnalysis] = useState<any | null>(null)


    // Monitor settings (including scaling)
    const [monitorSettings, setMonitorSettings] = useState<{
        enable_scaling?: boolean
        max_scale_count?: number
        scale_size_pct?: number
        min_rvol_for_scale?: number
        allow_scale_below_entry?: boolean
        move_stop_to_breakeven_after_scale?: boolean
    } | null>(null)

    // Update countdown every second when engine is running
    useEffect(() => {
        const isRunning = status?.state === 'running' || status?.state === 'premarket'
        const nextScan = status?.stats?.next_scan

        if (!isRunning || !nextScan) {
            setCountdown('')
            return
        }

        const updateCountdown = () => {
            // If market is closed (backend checks holidays, weekends, hours)
            if (!status.market_hours) {
                const now = new Date()
                const dayOfWeek = now.getDay()
                // Weekend - show Monday
                if (dayOfWeek === 0 || dayOfWeek === 6) {
                    setCountdown('📅 Next: Mon 9:30 AM ET')
                } else {
                    // Weekday but market closed (holiday or after hours)
                    setCountdown('📅 Next: Market Open')
                }
                return
            }

            // During market hours - show countdown
            const next = new Date(nextScan)
            const now = new Date()
            const diffMs = next.getTime() - now.getTime()

            if (diffMs <= 0) {
                setCountdown('scanning...')
                return
            }

            const mins = Math.floor(diffMs / 60000)
            const secs = Math.floor((diffMs % 60000) / 1000)
            setCountdown(`${mins}m ${secs}s`)
        }

        updateCountdown()
        const interval = setInterval(updateCountdown, 1000)
        return () => clearInterval(interval)
    }, [status?.state, status?.stats?.next_scan, status?.market_hours])

    // Open TradingView chart in new tab
    const openChart = (symbol: string) => {
        window.open(`https://www.tradingview.com/chart/?symbol=${symbol}`, '_blank')
    }

    // Use relative URLs - Next.js rewrites proxy to backend
    const API_BASE = ''

    // Fetch monitor settings on mount (not on interval - rarely changes)
    useEffect(() => {
        fetchMonitorSettings()
    }, [])

    // Fetch trade history on mount (for Trade History section)
    useEffect(() => {
        fetchTradeHistory()
    }, [])

    // Fetch test cases on mount
    useEffect(() => {
        const fetchTestCases = async () => {
            try {
                const res = await fetch(`${API_BASE}/warrior/sim/test_cases`)
                if (res.ok) {
                    const data = await res.json()
                    setTestCases(data.test_cases || [])
                }
            } catch (err) {
                console.error('Error fetching test cases:', err)
            }
        }
        fetchTestCases()
    }, [])

    // ========================================================================
    // Action Handlers
    // ========================================================================

    // Fetch closed trades for history
    const fetchTradeHistory = async () => {
        try {
            const res = await fetch(`${API_BASE}/warrior/trades?status=closed&limit=50`)
            if (res.ok) {
                const data = await res.json()
                setTradeHistory(data.trades || [])
            }
        } catch (err) {
            console.error('Error fetching trade history:', err)
        }
    }

    // Analyze a trade with AI
    const analyzeTradeWithAI = async (positionId: string) => {
        setAnalyzingTrade(positionId)
        setTradeAnalysis(null)
        try {
            const res = await fetch(`${API_BASE}/trade-events/analyze/${positionId}`, { method: 'POST' })
            if (res.ok) {
                const data = await res.json()
                if (data.success) {
                    setTradeAnalysis(data.analysis)
                } else {
                    addToLog(`❌ Analysis failed: ${data.error}`)
                }
            }
        } catch (err) {
            console.error('Error analyzing trade:', err)
            addToLog('❌ Failed to analyze trade')
        } finally {
            setAnalyzingTrade(null)
        }
    }

    // Fetch Monitor Settings (including scaling)
    const fetchMonitorSettings = async () => {
        try {
            const res = await fetch(`${API_BASE}/warrior/monitor/settings`)
            if (res.ok) {
                const data = await res.json()
                setMonitorSettings(data)
            }
        } catch (err) {
            console.error('Failed to fetch monitor settings:', err)
        }
    }

    // Update Monitor Settings (scaling toggle)
    const updateMonitorSettings = async (field: string, value: boolean | number) => {
        setActionLoading(`monitor-${field}`)
        try {
            const res = await fetch(`${API_BASE}/warrior/monitor/settings`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ [field]: value }),
            })
            if (res.ok) {
                const data = await res.json()
                setMonitorSettings(data.settings)
                addToLog(`⚙️ Scaling: ${field} = ${value}`)
            }
        } catch (err) {
            addToLog(`❌ Failed to update ${field}`)
        } finally {
            setActionLoading(null)
        }
    }

    // Run Scanner
    const runScan = async () => {
        setActionLoading('scan')
        try {
            const res = await fetch(`${API_BASE}/warrior/scanner/run`, { method: 'POST' })
            if (res.ok) {
                const data = await res.json()
                setScanResult(data)
                addToLog(`🔍 Scan complete: ${data.candidates.length} candidates found`)
            }
        } catch (err) {
            addToLog('❌ Scan failed')
        } finally {
            setActionLoading(null)
        }
    }

    // Mock Market: Load Test Case
    const loadTestCase = async () => {
        if (!selectedTestCase) return
        setActionLoading('loadTest')
        try {
            const res = await fetch(`${API_BASE}/warrior/sim/load_test_case?case_id=${selectedTestCase}`, {
                method: 'POST'
            })
            if (res.ok) {
                const data = await res.json()
                // API returns current_sim_price, entry_price in expected, or fall back to premarket_data
                const price = data.current_sim_price || data.expected?.entry_near || data.premarket_data?.premarket_high
                setLoadedTestCase({
                    symbol: data.symbol,
                    price: price
                })
                addToLog(`📦 Loaded test case: ${data.symbol} @ $${price?.toFixed(2) || 'N/A'}`)
                await refetch()
            }
        } catch (err) {
            addToLog('❌ Failed to load test case')
        } finally {
            setActionLoading(null)
        }
    }

    // Mock Market: Set Price
    const setMockPrice = async (symbol: string, price: number) => {
        setActionLoading('setPrice')
        try {
            const res = await fetch(`${API_BASE}/warrior/sim/price?symbol=${symbol}&price=${price}`, {
                method: 'PUT'
            })
            if (res.ok) {
                setLoadedTestCase(prev => prev ? { ...prev, price } : null)
                addToLog(`💹 Set ${symbol} price: $${price.toFixed(2)}`)
            }
        } catch (err) {
            addToLog('❌ Failed to set price')
        } finally {
            setActionLoading(null)
        }
    }

    // ========================================================================
    // Render
    // ========================================================================

    const isRunning = status?.state === 'running' || status?.state === 'premarket'
    const isPaused = status?.state === 'paused'

    return (
        <>
            <Head>
                <title>Warrior Trading | Nexus 2</title>
            </Head>

            <main className={styles.container}>
                {/* Header */}
                <header className={styles.header}>
                    <div className={styles.headerLeft}>
                        <Link href="/automation" className={styles.backLink}>← Automation</Link>
                        <h1>⚔️ Warrior Trading</h1>
                        <span className={styles.subtitle}>Ross Cameron Strategy</span>
                    </div>
                    <div className={styles.headerRight}>
                        <Link href="/warrior-performance" className={styles.refreshBtn} style={{ textDecoration: 'none' }}>
                            📊 Performance
                        </Link>
                        <span className={`${styles.badge} ${status?.config?.sim_only ? styles.badgeSim : styles.badgeLive}`}>
                            {status?.config?.sim_only ? '🧪 SIM' : '🔴 LIVE'}
                        </span>
                        <span className={`${styles.badge} ${status?.trading_window ? styles.badgeGreen : styles.badgeGray}`}>
                            {status?.trading_window ? '🟢 Trading Window' : '⚫ Outside Window'}
                        </span>
                        <button onClick={refetch} className={styles.refreshBtn}>
                            🔄 Refresh
                        </button>
                    </div>
                </header>

                {loading ? (
                    <div className={styles.loading}>Loading Warrior status...</div>
                ) : (
                    <>
                        {/* Main Grid */}
                        <div className={styles.grid}>
                            {/* Engine Control Card */}
                            <CollapsibleCard
                                id="engine"
                                title="🎛️ Engine Control"
                                badge={
                                    <span className={`${styles.stateBadge} ${styles[`state${status?.state}`]}`}>
                                        {status?.state?.toUpperCase() || 'UNKNOWN'}
                                    </span>
                                }
                            >
                                <div className={styles.cardBody}>
                                    {/* Stats */}
                                    <div className={styles.statsGrid}>
                                        <div className={styles.statBox}>
                                            <div className={styles.statValue}>{status?.stats.scans_run || 0}</div>
                                            <div className={styles.statLabel}>Scans</div>
                                        </div>
                                        <div className={styles.statBox}>
                                            <div className={styles.statValue}>{status?.stats.candidates_found || 0}</div>
                                            <div className={styles.statLabel}>Candidates</div>
                                        </div>
                                        <div className={styles.statBox}>
                                            <div className={styles.statValue}>{status?.stats.entries_triggered || 0}</div>
                                            <div className={styles.statLabel}>Entries</div>
                                        </div>
                                        <div className={styles.statBox}>
                                            <div className={`${styles.statValue} ${((brokerStatus?.broker_enabled ? brokerStatus?.total_daily_pnl : status?.stats.daily_pnl) || 0) >= 0 ? styles.pnlPositive : styles.pnlNegative}`}>
                                                {formatPnL((brokerStatus?.broker_enabled ? brokerStatus?.total_daily_pnl : status?.stats.daily_pnl) || 0)}
                                                {brokerStatus?.broker_enabled && brokerStatus?.daily_pnl_percent !== undefined && (
                                                    <span style={{ fontSize: '0.7em', marginLeft: '4px', opacity: 0.8 }}>
                                                        ({brokerStatus.daily_pnl_percent > 0 ? '+' : ''}{brokerStatus.daily_pnl_percent.toFixed(1)}%)
                                                    </span>
                                                )}
                                            </div>
                                            <div className={styles.statLabel}>
                                                Daily P&L
                                                {brokerStatus?.broker_enabled && brokerStatus?.peak_exposure && brokerStatus.peak_exposure > 0 && (
                                                    <span style={{ fontSize: '0.85em', opacity: 0.7 }}>
                                                        {' '}on ${(brokerStatus.peak_exposure / 1000).toFixed(1)}K
                                                    </span>
                                                )}
                                            </div>
                                        </div>
                                    </div>

                                    {/* Config Display */}
                                    <div className={styles.configRow}>
                                        <span>Risk/Trade: {formatCurrency(status?.config.risk_per_trade || 100)}</span>
                                        <span>Max Positions: {status?.config.max_positions || 3}</span>
                                        <span>Daily Loss Limit: {formatCurrency(status?.config.max_daily_loss || 300)}</span>
                                    </div>

                                    {/* Entry Modes */}
                                    <div className={styles.entryModes}>
                                        <span className={status?.config.orb_enabled ? styles.modeEnabled : styles.modeDisabled}>
                                            {status?.config.orb_enabled ? '✅' : '❌'} ORB
                                        </span>
                                        <span className={status?.config.pmh_enabled ? styles.modeEnabled : styles.modeDisabled}>
                                            {status?.config.pmh_enabled ? '✅' : '❌'} PMH
                                        </span>
                                        <span
                                            className={monitorSettings?.enable_scaling ? styles.modeEnabled : styles.modeDisabled}
                                            onClick={() => updateMonitorSettings('enable_scaling', !monitorSettings?.enable_scaling)}
                                            style={{ cursor: 'pointer' }}
                                            title="Click to toggle scaling (add to winners on pullback)"
                                        >
                                            {actionLoading === 'monitor-enable_scaling' ? '...' : (monitorSettings?.enable_scaling ? '✅' : '❌')} Scale
                                        </span>
                                    </div>

                                    {/* Countdown to next scan */}
                                    {isRunning && countdown && (
                                        <div style={{
                                            padding: '8px 12px',
                                            background: 'rgba(59, 130, 246, 0.15)',
                                            borderRadius: '6px',
                                            display: 'flex',
                                            justifyContent: 'space-between',
                                            alignItems: 'center',
                                            marginTop: '8px'
                                        }}>
                                            <span style={{ color: '#9ca3af' }}>⏱️ Next Scan:</span>
                                            <span style={{ color: '#60a5fa', fontFamily: 'monospace', fontWeight: 600 }}>{countdown}</span>
                                        </div>
                                    )}
                                </div>
                                <div className={styles.cardActions}>
                                    {!isRunning && !isPaused && (
                                        <button
                                            onClick={startEngine}
                                            className={styles.btnPrimary}
                                            disabled={actionLoading !== null}
                                        >
                                            {actionLoading === 'Start Engine' ? '...' : '▶️ Start'}
                                        </button>
                                    )}
                                    {isRunning && (
                                        <>
                                            <button
                                                onClick={pauseEngine}
                                                className={styles.btnSecondary}
                                                disabled={actionLoading !== null}
                                            >
                                                ⏸️ Pause
                                            </button>
                                            <button
                                                onClick={stopEngine}
                                                className={styles.btnDanger}
                                                disabled={actionLoading !== null}
                                            >
                                                ⏹️ Stop
                                            </button>
                                        </>
                                    )}
                                    {isPaused && (
                                        <>
                                            <button
                                                onClick={resumeEngine}
                                                className={styles.btnPrimary}
                                                disabled={actionLoading !== null}
                                            >
                                                ▶️ Resume
                                            </button>
                                            <button
                                                onClick={stopEngine}
                                                className={styles.btnDanger}
                                                disabled={actionLoading !== null}
                                            >
                                                ⏹️ Stop
                                            </button>
                                        </>
                                    )}
                                </div>
                            </CollapsibleCard>

                            {/* Simulation Mode Card */}
                            <CollapsibleCard
                                id="simulation"
                                title="🧪 Trading Mode"
                                badge={
                                    <>
                                        {brokerStatus?.broker_enabled && (
                                            <span className={`${styles.badge} ${styles.badgeBlue}`} style={{ marginRight: '4px' }}>
                                                📈 Broker
                                            </span>
                                        )}
                                        <span className={`${styles.badge} ${simStatus?.sim_enabled ? styles.badgeGreen : styles.badgeGray}`}>
                                            {simStatus?.sim_enabled ? '🧪 Sim' : 'Off'}
                                        </span>
                                    </>
                                }
                            >
                                <div className={styles.cardBody}>
                                    {simStatus?.sim_enabled && simStatus.account ? (
                                        <>
                                            <div className={styles.statsGrid}>
                                                <div className={styles.statBox}>
                                                    <div className={styles.statValue}>{formatCurrency(simStatus.account.cash)}</div>
                                                    <div className={styles.statLabel}>Cash</div>
                                                </div>
                                                <div className={styles.statBox}>
                                                    <div className={styles.statValue}>{formatCurrency(simStatus.account.portfolio_value)}</div>
                                                    <div className={styles.statLabel}>Equity</div>
                                                </div>
                                                <div className={styles.statBox}>
                                                    <div className={`${styles.statValue} ${simStatus.account.unrealized_pnl >= 0 ? styles.pnlPositive : styles.pnlNegative}`}>
                                                        {formatPnL(simStatus.account.unrealized_pnl)}
                                                    </div>
                                                    <div className={styles.statLabel}>Unrealized</div>
                                                </div>
                                                <div className={styles.statBox}>
                                                    <div className={`${styles.statValue} ${simStatus.account.realized_pnl >= 0 ? styles.pnlPositive : styles.pnlNegative}`}>
                                                        {formatPnL(simStatus.account.realized_pnl)}
                                                    </div>
                                                    <div className={styles.statLabel}>Realized</div>
                                                </div>
                                            </div>

                                            {simStatus.positions && simStatus.positions.length > 0 && (
                                                <div className={styles.simPositions}>
                                                    <h4>Sim Positions ({simStatus.position_count})</h4>
                                                    <table>
                                                        <thead>
                                                            <tr>
                                                                <th>Symbol</th>
                                                                <th>Qty</th>
                                                                <th>Avg</th>
                                                                <th>P&L</th>
                                                            </tr>
                                                        </thead>
                                                        <tbody>
                                                            {simStatus.positions.map((p) => (
                                                                <tr key={p.symbol}>
                                                                    <td className={styles.symbol}>{p.symbol}</td>
                                                                    <td>{p.qty}</td>
                                                                    <td>${p.avg_price.toFixed(2)}</td>
                                                                    <td className={p.unrealized_pnl >= 0 ? styles.pnlPositive : styles.pnlNegative}>
                                                                        {formatPnL(p.unrealized_pnl)}
                                                                    </td>
                                                                </tr>
                                                            ))}
                                                        </tbody>
                                                    </table>
                                                </div>
                                            )}
                                        </>
                                    ) : (
                                        <p className={styles.emptyMessage}>Simulation not active. Click Enable to start.</p>
                                    )}

                                    {/* Auto-enable on startup toggle */}
                                    <div style={{
                                        display: 'flex',
                                        justifyContent: 'space-between',
                                        alignItems: 'center',
                                        padding: '10px 0',
                                        borderTop: '1px solid rgba(255,255,255,0.1)',
                                        marginTop: '12px'
                                    }}>
                                        <div>
                                            <span style={{ color: '#e5e7eb' }}>Auto-start on restart</span>
                                            <span style={{ color: '#9ca3af', fontSize: '0.8em', marginLeft: '8px' }}>
                                                (Wire broker on server startup)
                                            </span>
                                        </div>
                                        <button
                                            onClick={toggleAutoEnable}
                                            className={status?.auto_enable ? styles.btnSuccess : styles.btnSecondary}
                                            disabled={actionLoading === 'autoEnable'}
                                            style={{ padding: '4px 12px', fontSize: '0.9em' }}
                                        >
                                            {actionLoading === 'autoEnable' ? '...' : (status?.auto_enable ? '✅ ON' : '❌ OFF')}
                                        </button>
                                    </div>
                                </div>
                                <div className={styles.cardActions}>
                                    {!simStatus?.sim_enabled ? (
                                        <>
                                            <button
                                                onClick={enableSim}
                                                className={styles.btnPrimary}
                                                disabled={actionLoading !== null}
                                            >
                                                {actionLoading === 'Enable Sim' ? '...' : '🚀 Enable Sim'}
                                            </button>
                                            <button
                                                onClick={enableBroker}
                                                className={styles.btnSuccess}
                                                disabled={actionLoading !== null}
                                                title="Enable Alpaca Paper for live trading"
                                            >
                                                {actionLoading === 'Enable Broker' ? '...' : '📈 Enable Broker'}
                                            </button>
                                        </>
                                    ) : (
                                        <>
                                            <button
                                                onClick={resetSim}
                                                className={styles.btnSecondary}
                                                disabled={actionLoading !== null}
                                            >
                                                {actionLoading === 'Reset Sim' ? '...' : '🔄 Reset Sim'}
                                            </button>
                                            <button
                                                onClick={disableSim}
                                                className={styles.btnDanger}
                                                disabled={actionLoading !== null}
                                            >
                                                {actionLoading === 'Disable Sim' ? '...' : '🛑 Disable Sim'}
                                            </button>
                                        </>
                                    )}
                                </div>
                            </CollapsibleCard>

                            {/* Mock Market Card */}
                            <MockMarketCard
                                testCases={testCases}
                                selectedTestCase={selectedTestCase}
                                setSelectedTestCase={setSelectedTestCase}
                                loadedTestCase={loadedTestCase}
                                loadTestCase={loadTestCase}
                                setMockPrice={setMockPrice}
                                actionLoading={actionLoading}
                            />

                            {/* Exit Rules Card */}
                            <ExitRulesCard monitor={status?.monitor} />

                            {/* Settings Card */}
                            <SettingsCard config={status?.config} updateConfig={updateConfig} />

                            {/* Note: Main Open Positions table with Health/Current/P&L is below in the positions section */}
                            {/* Scanner Card */}
                            <ScannerCard
                                scanResult={scanResult}
                                runScan={runScan}
                                openChart={openChart}
                                actionLoading={actionLoading}
                            />

                            {/* Last Engine Scan Card */}
                            <EngineCard
                                lastScanResult={status?.last_scan_result}
                                engineScanSort={engineScanSort}
                                setEngineScanSort={setEngineScanSort}
                                openChart={openChart}
                            />

                            {/* Watchlist Card */}
                            <CollapsibleCard
                                id="watchlist"
                                title="👁️ Watchlist"
                                badge={<span className={styles.countBadge}>{status?.watchlist_count || 0}</span>}
                            >
                                <div className={styles.cardBody}>
                                    {status?.watchlist && status.watchlist.length > 0 ? (
                                        <div className={styles.watchlistTable}>
                                            <table>
                                                <thead>
                                                    <tr>
                                                        <SortHeader label="Symbol" sortKey="symbol" sortConfig={watchlistSort} onSort={() => toggleSort('symbol', watchlistSort, setWatchlistSort)} />
                                                        <th title="Quality indicators: Gap, RVol, Entry">Quality</th>
                                                        <SortHeader label="RVOL" sortKey="rvol" sortConfig={watchlistSort} onSort={() => toggleSort('rvol', watchlistSort, setWatchlistSort)} />
                                                        <SortHeader label="PMH" sortKey="pmh" sortConfig={watchlistSort} onSort={() => toggleSort('pmh', watchlistSort, setWatchlistSort)} />
                                                        <th>ORB High</th>
                                                        <th>Status</th>
                                                    </tr>
                                                </thead>
                                                <tbody>
                                                    {sortData(status.watchlist, watchlistSort).map((w) => (
                                                        <tr key={w.symbol} className={w.entry_triggered ? styles.triggered : ''}>
                                                            <td className={styles.symbol}>
                                                                <span
                                                                    className={styles.clickableSymbol}
                                                                    onClick={() => openChart(w.symbol)}
                                                                    title="Open TradingView chart"
                                                                >
                                                                    {w.symbol}
                                                                </span>
                                                            </td>
                                                            <td>
                                                                <div className={styles.indicatorRow}>
                                                                    <span className={`${styles.indicatorDot} ${w.gap_percent >= 15 ? styles.dotGreen : w.gap_percent >= 10 ? styles.dotYellow : styles.dotRed}`} title={`Gap: +${w.gap_percent.toFixed(1)}%`}>●</span>
                                                                    <span className={`${styles.indicatorDot} ${w.rvol >= 3 ? styles.dotGreen : w.rvol >= 2 ? styles.dotYellow : styles.dotRed}`} title={`RVol: ${w.rvol.toFixed(1)}x`}>●</span>
                                                                    <span className={`${styles.indicatorDot} ${w.entry_triggered ? styles.dotGreen : w.orb_established ? styles.dotYellow : styles.dotRed}`} title={w.entry_triggered ? 'Entered' : w.orb_established ? 'Watching' : 'Setup'}>●</span>
                                                                </div>
                                                            </td>
                                                            <td>{w.rvol.toFixed(1)}x</td>
                                                            <td>${w.pmh.toFixed(2)}</td>
                                                            <td>{w.orb_high ? `$${w.orb_high.toFixed(2)}` : '-'}</td>
                                                            <td>
                                                                {w.entry_triggered ? '✅ Entered' :
                                                                    w.orb_established ? '⏳ Watching' : '📊 Setup'}
                                                            </td>
                                                        </tr>
                                                    ))}
                                                </tbody>
                                            </table>
                                        </div>
                                    ) : (
                                        <p className={styles.emptyMessage}>No symbols being watched</p>
                                    )}
                                </div>
                            </CollapsibleCard>
                        </div>

                        {/* Positions Table */}
                        {positions.length > 0 && (
                            <div className={styles.positionsCard}>
                                <div className={styles.cardHeader}>
                                    <h2>📈 Open Positions</h2>
                                </div>
                                <div className={styles.positionsTable}>
                                    <table>
                                        <thead>
                                            <tr>
                                                <th>Symbol</th>
                                                <th>Shares</th>
                                                <th>Entry</th>
                                                <th>Stop</th>
                                                <th>Target</th>
                                                <th>Current</th>
                                                <th>P&L</th>
                                                <th>High</th>
                                                <th>Health</th>
                                                <th>Partial?</th>
                                                <th>Time</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {positions.map((p) => (
                                                <tr key={p.position_id}>
                                                    <td className={styles.symbol}>
                                                        <span
                                                            className={styles.clickableSymbol}
                                                            onClick={() => openChart(p.symbol)}
                                                            title="Open TradingView chart"
                                                        >
                                                            {p.symbol}
                                                        </span>
                                                    </td>
                                                    <td>{p.shares}</td>
                                                    <td>${p.entry_price.toFixed(2)}</td>
                                                    <td className={styles.stopPrice}>${p.current_stop.toFixed(2)}</td>
                                                    <td className={styles.targetPrice}>${p.profit_target.toFixed(2)}</td>
                                                    <td>{p.current_price ? `$${p.current_price.toFixed(2)}` : '-'}</td>
                                                    <td style={{ color: p.current_price ? ((p.current_price - p.entry_price) >= 0 ? '#22c55e' : '#ef4444') : '#888' }}>
                                                        {p.current_price ? `${(p.current_price - p.entry_price) >= 0 ? '+' : ''}$${((p.current_price - p.entry_price) * p.shares).toFixed(2)}` : '-'}
                                                    </td>
                                                    <td>${p.high_since_entry.toFixed(2)}</td>
                                                    <td>
                                                        {positionHealth[p.position_id] ? (
                                                            <div className={styles.indicatorRow} style={{ gap: '2px' }}>
                                                                {(['macd', 'ema9', 'ema20', 'ema200', 'vwap', 'volume', 'stop', 'target'] as const).map((key) => {
                                                                    const ind = positionHealth[p.position_id]?.[key]
                                                                    if (!ind) return null
                                                                    const dotClass = ind.status === 'green' ? styles.dotGreen
                                                                        : ind.status === 'yellow' ? styles.dotYellow
                                                                            : ind.status === 'red' ? styles.dotRed
                                                                                : styles.dotGray
                                                                    return (
                                                                        <span
                                                                            key={key}
                                                                            className={`${styles.indicatorDot} ${dotClass}`}
                                                                            title={ind.tooltip}
                                                                        >●</span>
                                                                    )
                                                                })}
                                                            </div>
                                                        ) : (
                                                            <span style={{ color: '#666' }}>...</span>
                                                        )}
                                                    </td>
                                                    <td>{p.partial_taken ? '✅' : '-'}</td>
                                                    <td>{formatTime(p.entry_time)}</td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        )}

                        {/* Trade Events Log - Collapsible */}
                        <div className={styles.card} style={{ marginTop: '1rem' }}>
                            <div
                                className={styles.cardHeader}
                                style={{ cursor: 'pointer' }}
                                onClick={() => {
                                    const next = !showTradeEvents
                                    setShowTradeEvents(next)
                                    localStorage.setItem('warrior_showTradeEvents', String(next))
                                }}
                            >
                                <h2>📋 Trade Events Log {showTradeEvents ? '▼' : '▶'}</h2>
                                <span style={{ fontSize: '0.85rem', color: '#888' }}>
                                    {tradeEvents.length} recent events
                                </span>
                            </div>
                            {showTradeEvents && (
                                <div className={styles.cardBody} style={{ padding: '12px' }}>
                                    {tradeEvents.length === 0 ? (
                                        <p style={{ color: '#888', fontStyle: 'italic' }}>No trade events yet</p>
                                    ) : (
                                        <table className={styles.positionsTable} style={{ fontSize: '0.85rem' }}>
                                            <thead>
                                                <tr>
                                                    <th>Time (ET)</th>
                                                    <th>Symbol</th>
                                                    <th>Event</th>
                                                    <th>Details</th>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {tradeEvents.map((event: any, idx: number) => (
                                                    <tr key={event.id || idx}>
                                                        <td style={{ whiteSpace: 'nowrap' }}>
                                                            {formatTime(event.created_at)}
                                                        </td>
                                                        <td><strong>{event.symbol}</strong></td>
                                                        <td>
                                                            <span style={{
                                                                padding: '2px 6px',
                                                                borderRadius: '4px',
                                                                fontSize: '0.75rem',
                                                                backgroundColor: event.event_type?.includes('EXIT') ? '#ef444420'
                                                                    : event.event_type?.includes('ENTRY') ? '#22c55e20'
                                                                        : event.event_type?.includes('BREAKEVEN') ? '#3b82f620'
                                                                            : '#f5f5f520',
                                                                color: event.event_type?.includes('EXIT') ? '#ef4444'
                                                                    : event.event_type?.includes('ENTRY') ? '#22c55e'
                                                                        : event.event_type?.includes('BREAKEVEN') ? '#3b82f6'
                                                                            : '#888'
                                                            }}>
                                                                {event.event_type?.replace(/_/g, ' ')}
                                                            </span>
                                                        </td>
                                                        <td style={{ color: '#888' }}>
                                                            {event.reason || (event.new_value ? `→ $${event.new_value}` : '--')}
                                                        </td>
                                                    </tr>
                                                ))}
                                            </tbody>
                                        </table>
                                    )}
                                </div>
                            )}
                        </div>

                        {/* Trade History - Closed Trades with AI Analysis */}
                        <div className={styles.card} style={{ marginTop: '1rem' }}>
                            <div
                                className={styles.cardHeader}
                                style={{ cursor: 'pointer' }}
                                onClick={() => {
                                    const next = !showTradeHistory
                                    setShowTradeHistory(next)
                                    localStorage.setItem('warrior_showTradeHistory', String(next))
                                }}
                            >
                                <h2>📊 Trade History {showTradeHistory ? '▼' : '▶'}</h2>
                                <span style={{ fontSize: '0.85rem', color: '#888' }}>
                                    {tradeHistory.length} closed trades
                                </span>
                            </div>
                            {showTradeHistory && (
                                <div className={styles.cardBody} style={{ padding: '12px' }}>
                                    {tradeHistory.length === 0 ? (
                                        <p style={{ color: '#888', fontStyle: 'italic' }}>No closed trades yet</p>
                                    ) : (
                                        <>
                                            <div style={{ maxHeight: '400px', overflowY: 'auto' }}>
                                                <table className={styles.positionsTable} style={{ fontSize: '0.85rem' }}>
                                                    <thead>
                                                        <tr>
                                                            <th>Symbol</th>
                                                            <th>Entry $</th>
                                                            <th>Exit $</th>
                                                            <th>P&L</th>
                                                            <th>Entered</th>
                                                            <th>Closed</th>
                                                            <th>Action</th>
                                                        </tr>
                                                    </thead>
                                                    <tbody>
                                                        {[...tradeHistory]
                                                            .sort((a, b) => new Date(b.exit_time || 0).getTime() - new Date(a.exit_time || 0).getTime())
                                                            .map((trade: any) => (
                                                                <tr key={trade.id}>
                                                                    <td><strong>{trade.symbol}</strong></td>
                                                                    <td>${parseFloat(trade.entry_price || 0).toFixed(2)}</td>
                                                                    <td>${parseFloat(trade.exit_price || 0).toFixed(2)}</td>
                                                                    <td style={{
                                                                        color: parseFloat(trade.realized_pnl || 0) >= 0 ? '#22c55e' : '#ef4444'
                                                                    }}>
                                                                        ${parseFloat(trade.realized_pnl || 0).toFixed(2)}
                                                                    </td>
                                                                    <td style={{ whiteSpace: 'nowrap', fontSize: '0.75rem', color: '#888' }}>
                                                                        {trade.entry_time ? new Date(trade.entry_time).toLocaleDateString() : '--'}
                                                                    </td>
                                                                    <td style={{ whiteSpace: 'nowrap', fontSize: '0.75rem' }}>
                                                                        {trade.exit_time ? new Date(trade.exit_time).toLocaleDateString() : '--'}
                                                                    </td>
                                                                    <td>
                                                                        <button
                                                                            onClick={() => analyzeTradeWithAI(trade.id)}
                                                                            disabled={analyzingTrade === trade.id}
                                                                            style={{
                                                                                padding: '4px 8px',
                                                                                fontSize: '0.75rem',
                                                                                backgroundColor: '#3b82f6',
                                                                                color: 'white',
                                                                                border: 'none',
                                                                                borderRadius: '4px',
                                                                                cursor: 'pointer',
                                                                                opacity: analyzingTrade === trade.id ? 0.5 : 1,
                                                                            }}
                                                                        >
                                                                            {analyzingTrade === trade.id ? '⏳...' : '🤖 Analyze'}
                                                                        </button>
                                                                    </td>
                                                                </tr>
                                                            ))}
                                                    </tbody>
                                                </table>
                                            </div>

                                            {/* AI Analysis Result */}
                                            {tradeAnalysis && (
                                                <div style={{
                                                    marginTop: '1rem',
                                                    padding: '1rem',
                                                    backgroundColor: '#1a1a2e',
                                                    borderRadius: '8px',
                                                    border: '1px solid #333',
                                                }}>
                                                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                                                        <h3 style={{ margin: 0 }}>🤖 AI Analysis: {tradeAnalysis.symbol}</h3>
                                                        <button onClick={() => setTradeAnalysis(null)} style={{ background: 'none', border: 'none', color: '#888', cursor: 'pointer' }}>✕</button>
                                                    </div>

                                                    {/* Grades */}
                                                    <div style={{ display: 'flex', gap: '1rem', marginBottom: '1rem' }}>
                                                        {['entry', 'exit', 'management', 'overall'].map(key => (
                                                            <div key={key} style={{ textAlign: 'center' }}>
                                                                <div style={{ fontSize: '0.7rem', color: '#888', textTransform: 'uppercase' }}>{key}</div>
                                                                <div style={{
                                                                    fontSize: '1.5rem',
                                                                    fontWeight: 'bold',
                                                                    color: tradeAnalysis.grades?.[key] === 'A' ? '#22c55e'
                                                                        : tradeAnalysis.grades?.[key] === 'B' ? '#84cc16'
                                                                            : tradeAnalysis.grades?.[key] === 'C' ? '#eab308'
                                                                                : tradeAnalysis.grades?.[key] === 'D' ? '#f97316'
                                                                                    : '#ef4444'
                                                                }}>
                                                                    {tradeAnalysis.grades?.[key] || '?'}
                                                                </div>
                                                            </div>
                                                        ))}
                                                    </div>

                                                    {/* Summary */}
                                                    <p style={{ color: '#ccc', marginBottom: '0.5rem' }}>{tradeAnalysis.summary}</p>

                                                    {/* What Went Well */}
                                                    {tradeAnalysis.what_went_well?.length > 0 && (
                                                        <div style={{ marginBottom: '0.5rem' }}>
                                                            <strong style={{ color: '#22c55e' }}>✓ What Went Well:</strong>
                                                            <ul style={{ margin: '0.25rem 0', paddingLeft: '1.5rem', color: '#aaa' }}>
                                                                {tradeAnalysis.what_went_well.map((item: string, i: number) => (
                                                                    <li key={i}>{item}</li>
                                                                ))}
                                                            </ul>
                                                        </div>
                                                    )}

                                                    {/* Lessons Learned */}
                                                    {tradeAnalysis.lessons_learned?.length > 0 && (
                                                        <div>
                                                            <strong style={{ color: '#eab308' }}>📝 Lessons:</strong>
                                                            <ul style={{ margin: '0.25rem 0', paddingLeft: '1.5rem', color: '#aaa' }}>
                                                                {tradeAnalysis.lessons_learned.map((item: string, i: number) => (
                                                                    <li key={i}>{item}</li>
                                                                ))}
                                                            </ul>
                                                        </div>
                                                    )}
                                                </div>
                                            )}
                                        </>
                                    )}
                                </div>
                            )}
                        </div>

                        {/* Event Log */}
                        <EventLogCard eventLog={eventLog} onClear={() => setEventLog([])} />
                    </>
                )
                }
            </main >
        </>
    )
}
