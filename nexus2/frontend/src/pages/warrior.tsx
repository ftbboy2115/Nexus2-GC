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
    TradingModeCard,
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
    const [testCases, setTestCases] = useState<{ id: string, symbol: string, description: string, ross_traded?: boolean, notes?: string, trade_date?: string }[]>([])
    const [selectedTestCase, setSelectedTestCase] = useState<string>('')
    const [loadedTestCase, setLoadedTestCase] = useState<{ symbol: string, price: number } | null>(null)
    const [clockState, setClockState] = useState<{ time_string: string, is_market_hours: boolean, speed: number } | null>(null)
    const [simOrders, setSimOrders] = useState<any[]>([])
    // Chart data for candlestick visualization
    const [visibleBars, setVisibleBars] = useState<any[]>([])
    const [currentBarIndex, setCurrentBarIndex] = useState(0)
    const [chartSymbol, setChartSymbol] = useState('')

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

    // Open TradingView chart in new window (not tab)
    const openChart = (symbol: string) => {
        window.open(
            `https://www.tradingview.com/chart/D7F9NNnO/?symbol=${symbol}`,
            '_blank',
            'width=1400,height=900,menubar=no,toolbar=no,location=no,status=no'
        )
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

    // Historical Replay: Load with intraday bars
    const loadHistoricalTestCase = async () => {
        if (!selectedTestCase) return
        setActionLoading('loadHistorical')
        try {
            const res = await fetch(`${API_BASE}/warrior/sim/load_historical?case_id=${selectedTestCase}`, {
                method: 'POST'
            })
            if (res.ok) {
                const data = await res.json()
                setLoadedTestCase({
                    symbol: data.symbol,
                    price: data.premarket?.pmh || 0
                })
                setClockState(data.clock)
                // Set chart data for immediate rendering
                if (data.visible_bars) {
                    setVisibleBars(data.visible_bars)
                    setCurrentBarIndex(data.current_bar_index || 0)
                    setChartSymbol(data.chart_symbol || data.symbol || '')
                }
                addToLog(`📊 Loaded historical replay: ${data.symbol} (${data.bar_count} bars)`)
                await refetch()
            }
        } catch (err) {
            addToLog('❌ Failed to load historical test case')
        } finally {
            setActionLoading(null)
        }
    }

    // Historical Replay: Step forward
    // Wrapped in useCallback to prevent effect re-runs on every render
    const stepClock = useCallback(async (minutes: number) => {
        try {
            const res = await fetch(`${API_BASE}/warrior/sim/step?minutes=${minutes}`, { method: 'POST' })
            if (res.ok) {
                const data = await res.json()
                setClockState(data.clock)
                // Update price if available
                const prices = data.prices || {}
                const symbol = Object.keys(prices)[0]
                if (symbol && prices[symbol]) {
                    setLoadedTestCase(prev => prev ? { ...prev, price: prices[symbol] } : null)
                }
                // Update orders for GUI
                if (data.orders) {
                    setSimOrders(data.orders)
                }
                // Update chart data
                if (data.visible_bars) {
                    setVisibleBars(data.visible_bars)
                    setCurrentBarIndex(data.current_bar_index || 0)
                    setChartSymbol(data.chart_symbol || '')
                }
            }
        } catch (err) {
            console.error('Failed to step clock:', err)
        }
    }, [])  // Empty deps - function doesn't depend on any props/state

    // Historical Replay: Step backward
    const stepClockBack = async (minutes: number) => {
        try {
            const res = await fetch(`${API_BASE}/warrior/sim/step_back?minutes=${minutes}`, { method: 'POST' })
            if (res.ok) {
                const data = await res.json()
                setClockState(data.clock)
                const prices = data.prices || {}
                const symbol = Object.keys(prices)[0]
                if (symbol && prices[symbol]) {
                    setLoadedTestCase(prev => prev ? { ...prev, price: prices[symbol] } : null)
                }
            }
        } catch (err) {
            console.error('Failed to step clock back:', err)
        }
    }

    // Historical Replay: Reset to market open
    const resetClock = async () => {
        try {
            const res = await fetch(`${API_BASE}/warrior/sim/reset_clock`, { method: 'POST' })
            if (res.ok) {
                const data = await res.json()
                setClockState(data.clock)
                const prices = data.prices || {}
                const symbol = Object.keys(prices)[0]
                if (symbol && prices[symbol]) {
                    setLoadedTestCase(prev => prev ? { ...prev, price: prices[symbol] } : null)
                }
                addToLog('⏮️ Reset to 9:30 AM')
            }
        } catch (err) {
            console.error('Failed to reset clock:', err)
        }
    }

    // Historical Replay: Set playback speed
    const setPlaybackSpeed = async (speed: number) => {
        try {
            const res = await fetch(`${API_BASE}/warrior/sim/speed?speed=${speed}`, { method: 'POST' })
            if (res.ok) {
                const data = await res.json()
                setClockState(data.clock)
            }
        } catch (err) {
            console.error('Failed to set playback speed:', err)
        }
    }

    // Clear sim orders (reset mock broker state)
    const clearSimOrders = async () => {
        try {
            const res = await fetch(`${API_BASE}/warrior/sim/reset`, { method: 'POST' })
            if (res.ok) {
                setSimOrders([])
                addToLog('🗑️ Cleared mock orders')
            }
        } catch (err) {
            console.error('Failed to clear sim orders:', err)
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
                        {/* Main Grid - Ordered by priority: active trading views first, config/testing last */}
                        <div className={styles.grid}>
                            {/* 1. Engine Control Card */}
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

                            {/* 2. Watchlist Card */}
                            <WatchlistCard
                                watchlist={status?.watchlist}
                                watchlistCount={status?.watchlist_count || 0}
                                watchlistSort={watchlistSort}
                                setWatchlistSort={setWatchlistSort}
                                openChart={openChart}
                            />
                        </div>

                        {/* 3. Open Positions Table */}
                        <OpenPositionsCard
                            positions={positions}
                            positionHealth={positionHealth}
                            openChart={openChart}
                        />

                        {/* 4. Trade Events Log - Collapsible */}
                        <TradeEventsCard
                            tradeEvents={tradeEvents}
                            showTradeEvents={showTradeEvents}
                            setShowTradeEvents={setShowTradeEvents}
                        />

                        {/* 5. Trade History - Closed Trades with AI Analysis */}
                        <TradeHistoryCard
                            tradeHistory={tradeHistory}
                            showTradeHistory={showTradeHistory}
                            setShowTradeHistory={setShowTradeHistory}
                            analyzeTradeWithAI={analyzeTradeWithAI}
                            analyzingTrade={analyzingTrade}
                            tradeAnalysis={tradeAnalysis}
                            setTradeAnalysis={setTradeAnalysis}
                        />

                        {/* 6. Event Log */}
                        <EventLogCard eventLog={eventLog} onClear={() => setEventLog([])} />

                        {/* Secondary Grid - Less frequently used cards */}
                        <div className={styles.grid} style={{ marginTop: '1.25rem' }}>
                            {/* 7. Last Engine Scan Card */}
                            <EngineCard
                                lastScanResult={status?.last_scan_result}
                                engineScanSort={engineScanSort}
                                setEngineScanSort={setEngineScanSort}
                                openChart={openChart}
                            />

                            {/* 8. Scanner Card (Manual Scan) */}
                            <ScannerCard
                                scanResult={scanResult}
                                runScan={runScan}
                                openChart={openChart}
                                actionLoading={actionLoading}
                            />

                            {/* 9. Trading Mode Card */}
                            <TradingModeCard
                                simStatus={simStatus}
                                brokerStatus={brokerStatus}
                                autoEnable={status?.auto_enable}
                                actionLoading={actionLoading}
                                enableSim={enableSim}
                                disableSim={disableSim}
                                resetSim={resetSim}
                                enableBroker={enableBroker}
                                toggleAutoEnable={toggleAutoEnable}
                            />

                            {/* 10. Mock Market Card */}
                            <MockMarketCard
                                testCases={testCases}
                                selectedTestCase={selectedTestCase}
                                setSelectedTestCase={setSelectedTestCase}
                                loadedTestCase={loadedTestCase}
                                loadTestCase={loadTestCase}
                                setMockPrice={setMockPrice}
                                actionLoading={actionLoading}
                                clockState={clockState}
                                onLoadHistorical={loadHistoricalTestCase}
                                onStep={stepClock}
                                onStepBack={stepClockBack}
                                onResetClock={resetClock}
                                onSetSpeed={setPlaybackSpeed}
                                orders={simOrders}
                                onClearOrders={clearSimOrders}
                                visibleBars={visibleBars}
                                currentBarIndex={currentBarIndex}
                                chartSymbol={chartSymbol}
                                simPositions={(simStatus?.positions || []).map((p: any) => ({
                                    symbol: p.symbol || '',
                                    qty: p.qty || 0,
                                    avg: p.avg_entry || p.avg || 0,
                                    pnl: p.unrealized_pnl || 0,
                                }))}
                            />

                            {/* 11. Exit Rules Card */}
                            <ExitRulesCard monitor={status?.monitor} />

                            {/* 12. Settings Card */}
                            <SettingsCard config={status?.config} updateConfig={updateConfig} />
                        </div>
                    </>
                )
                }
            </main >
        </>
    )
}
