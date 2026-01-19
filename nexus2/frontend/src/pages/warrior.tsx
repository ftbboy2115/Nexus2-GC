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
    WatchlistCard,
    OpenPositionsCard,
    TradeEventsCard,
    TradeHistoryCard,
    EngineControlCard,
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
                            <EngineControlCard
                                state={status?.state}
                                stats={status?.stats || {}}
                                config={status?.config || {}}
                                brokerStatus={brokerStatus}
                                monitorSettings={monitorSettings}
                                countdown={countdown}
                                isRunning={isRunning}
                                isPaused={isPaused}
                                actionLoading={actionLoading}
                                startEngine={startEngine}
                                stopEngine={stopEngine}
                                pauseEngine={pauseEngine}
                                resumeEngine={resumeEngine}
                                updateMonitorSettings={updateMonitorSettings}
                            />

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
                            <WatchlistCard
                                watchlist={status?.watchlist}
                                watchlistCount={status?.watchlist_count || 0}
                                watchlistSort={watchlistSort}
                                setWatchlistSort={setWatchlistSort}
                                openChart={openChart}
                            />
                        </div>

                        {/* Positions Table */}
                        <OpenPositionsCard
                            positions={positions}
                            positionHealth={positionHealth}
                            openChart={openChart}
                        />

                        {/* Trade Events Log - Collapsible */}
                        <TradeEventsCard
                            tradeEvents={tradeEvents}
                            showTradeEvents={showTradeEvents}
                            setShowTradeEvents={setShowTradeEvents}
                        />

                        {/* Trade History - Closed Trades with AI Analysis */}
                        <TradeHistoryCard
                            tradeHistory={tradeHistory}
                            showTradeHistory={showTradeHistory}
                            setShowTradeHistory={setShowTradeHistory}
                            analyzeTradeWithAI={analyzeTradeWithAI}
                            analyzingTrade={analyzingTrade}
                            tradeAnalysis={tradeAnalysis}
                            setTradeAnalysis={setTradeAnalysis}
                        />

                        {/* Event Log */}
                        <EventLogCard eventLog={eventLog} onClear={() => setEventLog([])} />
                    </>
                )
                }
            </main >
        </>
    )
}
