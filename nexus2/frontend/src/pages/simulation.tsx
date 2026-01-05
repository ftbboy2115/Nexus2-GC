import { useState, useEffect, useCallback } from 'react'
import Head from 'next/head'
import Link from 'next/link'
import styles from '@/styles/Simulation.module.css'

// ============================================================================
// Type Definitions
// ============================================================================

interface SimulationStatus {
    status: string
    clock: {
        current_time: string
        is_market_hours: boolean
        trading_day: string
        is_eod_window: boolean
        speed: number
    }
    broker: {
        cash: number
        portfolio_value: number
        position_count: number
    }
    market_data: {
        symbols_loaded: number
        date_range: { start: string; end: string } | null
    }
}

interface SimPosition {
    symbol: string
    qty: number
    avg_price: number
    market_value: number
    unrealized_pnl: number
    pnl_percent: number
    stop_price?: number
}

interface SimPositionsData {
    status: string
    positions: SimPosition[]
    count: number
    account?: {
        cash: number
        portfolio_value: number
        buying_power: number
        realized_pnl: number
        unrealized_pnl: number
        position_count: number
    }
}

interface BrokerState {
    cash: number
    portfolio_value: number
    buying_power: number
    realized_pnl: number
    positions: Record<string, { qty: number; avg_price: number; stop_price?: number }>
    orders: any[]
    fills: any[]
}

interface TestCase {
    id: string
    name: string
    description: string
    symbol: string
    date_range: { start: string; end: string }
    setup_type: string
}

interface DiagnosticResult {
    scanner: string
    enabled: boolean
    candidates_found: number
    candidates_passed: number
    rejections: Array<{
        symbol: string
        reason: string
        threshold: number
        actual_value: number
    }>
    error: string | null
}

// ============================================================================
// Main Component
// ============================================================================

export default function Simulation() {
    // Core state
    const [status, setStatus] = useState<SimulationStatus | null>(null)
    const [positions, setPositions] = useState<SimPositionsData | null>(null)
    const [brokerState, setBrokerState] = useState<BrokerState | null>(null)
    const [testCases, setTestCases] = useState<TestCase[]>([])
    const [loading, setLoading] = useState(true)
    const [actionLoading, setActionLoading] = useState<string | null>(null)

    // Form state for Load Historical
    const [loadSymbol, setLoadSymbol] = useState('')
    const [loadStartDate, setLoadStartDate] = useState('')
    const [loadEndDate, setLoadEndDate] = useState('')

    // Diagnostics panel
    const [diagnostics, setDiagnostics] = useState<DiagnosticResult[] | null>(null)
    const [showDiagnostics, setShowDiagnostics] = useState(false)

    // Event log
    const [eventLog, setEventLog] = useState<string[]>([])

    const API_BASE = 'http://localhost:8000'

    // ========================================================================
    // Data Fetching
    // ========================================================================

    const fetchStatus = useCallback(async () => {
        try {
            const [statusRes, positionsRes, brokerRes, testCasesRes] = await Promise.all([
                fetch(`${API_BASE}/automation/simulation/status`),
                fetch(`${API_BASE}/automation/simulation/positions`),
                fetch(`${API_BASE}/automation/simulation/broker`),
                fetch(`${API_BASE}/automation/simulation/test_cases`),
            ])

            if (statusRes.ok) setStatus(await statusRes.json())
            if (positionsRes.ok) setPositions(await positionsRes.json())
            if (brokerRes.ok) setBrokerState(await brokerRes.json())
            if (testCasesRes.ok) {
                const data = await testCasesRes.json()
                setTestCases(data.test_cases || [])
            }
        } catch (err) {
            console.error('Error fetching simulation status:', err)
            addToLog('❌ Failed to connect to backend')
        } finally {
            setLoading(false)
        }
    }, [])

    useEffect(() => {
        fetchStatus()
        const interval = setInterval(fetchStatus, 3000) // Refresh every 3s
        return () => clearInterval(interval)
    }, [fetchStatus])

    // ========================================================================
    // Action Handlers
    // ========================================================================

    const addToLog = (message: string) => {
        const timestamp = new Date().toLocaleTimeString()
        setEventLog(prev => [`${timestamp} - ${message}`, ...prev.slice(0, 49)])
    }

    const handleAction = async (
        actionId: string,
        endpoint: string,
        method: 'GET' | 'POST' = 'POST',
        body?: object
    ) => {
        setActionLoading(actionId)
        try {
            const res = await fetch(`${API_BASE}${endpoint}`, {
                method,
                headers: { 'Content-Type': 'application/json' },
                body: body ? JSON.stringify(body) : undefined,
            })
            if (res.ok) {
                const data = await res.json()
                addToLog(`✅ ${actionId}: ${data.message || 'Success'}`)
                await fetchStatus()
                return data
            } else {
                const err = await res.json()
                addToLog(`❌ ${actionId}: ${err.detail || 'Failed'}`)
            }
        } catch (err) {
            console.error(`Error with ${actionId}:`, err)
            addToLog(`❌ ${actionId}: Network error`)
        } finally {
            setActionLoading(null)
        }
    }

    // Clock Controls
    const advanceTime = (minutes: number) => {
        handleAction(
            `Advance ${minutes}m`,
            `/automation/simulation/advance?minutes=${minutes}`,
            'POST'
        )
    }

    const advanceDays = (days: number) => {
        handleAction(
            `Advance ${days}d`,
            `/automation/simulation/advance?days=${days}`,
            'POST'
        )
    }

    const advanceToTime = (targetTime: string) => {
        // For 16:00, use to_eod flag
        if (targetTime === '16:00') {
            handleAction(
                'Advance to 16:00',
                '/automation/simulation/advance?to_eod=true',
                'POST'
            )
        } else {
            // For other times like 15:45, calculate hours from 9:30 AM market open
            const [hours, mins] = targetTime.split(':').map(Number)
            const targetMinutes = hours * 60 + mins
            const marketOpenMinutes = 9 * 60 + 30 // 9:30 AM
            const advanceMinutes = targetMinutes - marketOpenMinutes
            handleAction(
                `Advance to ${targetTime}`,
                `/automation/simulation/advance?minutes=${advanceMinutes}`,
                'POST'
            )
        }
    }

    // Reset simulation
    const resetSimulation = () => {
        handleAction('Reset', '/automation/simulation/reset')
    }

    // Load Historical Data
    const loadHistorical = async () => {
        if (!loadSymbol || !loadStartDate || !loadEndDate) {
            addToLog('⚠️ Please fill all fields for historical load')
            return
        }
        await handleAction(
            `Load ${loadSymbol}`,
            '/automation/simulation/load_historical',
            'POST',
            { symbol: loadSymbol, start_date: loadStartDate, end_date: loadEndDate }
        )
    }

    // Load Test Case
    const loadTestCase = async (id: string) => {
        await handleAction(`Load Test Case ${id}`, `/automation/simulation/load_test_case?case_id=${id}`, 'POST')
    }

    // Inject Synthetic Pattern
    const injectPattern = (patternType: string) => {
        handleAction(`Inject ${patternType}`, '/automation/simulation/load_htf_pattern', 'POST', {
            pattern_type: patternType,
        })
    }

    // Run Diagnostic Scan
    const runDiagnosticScan = async () => {
        setActionLoading('diagnostic')
        try {
            const res = await fetch(`${API_BASE}/automation/simulation/diagnostic_unified_scan`, {
                method: 'POST',
            })
            if (res.ok) {
                const data = await res.json()
                setDiagnostics(data.diagnostics || [])
                setShowDiagnostics(true)
                addToLog(`🔍 Diagnostic scan complete: ${data.total_signals || 0} signals`)
            }
        } catch (err) {
            addToLog('❌ Diagnostic scan failed')
        } finally {
            setActionLoading(null)
        }
    }

    // Execute Path (mimic scheduler execution)
    const executePath = async () => {
        await handleAction('Execute Path', '/automation/simulation/debug_execute_path', 'POST')
    }

    // ========================================================================
    // Formatting Helpers
    // ========================================================================

    const formatCurrency = (value: number) =>
        new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(value)

    const formatPnL = (value: number) => {
        const formatted = formatCurrency(Math.abs(value))
        if (value > 0) return `+${formatted}`
        if (value < 0) return `-${formatted}`
        return formatted
    }

    const formatDateTime = (iso: string | null | undefined) => {
        if (!iso) return '-'
        const d = new Date(iso)
        return d.toLocaleString()
    }

    const formatDate = (iso: string | null | undefined) => {
        if (!iso) return '-'
        const d = new Date(iso)
        return d.toLocaleDateString()
    }

    const formatTime = (iso: string | null | undefined) => {
        if (!iso) return '-'
        const d = new Date(iso)
        return d.toLocaleTimeString()
    }

    // ========================================================================
    // Render
    // ========================================================================

    return (
        <>
            <Head>
                <title>Simulation | Nexus 2</title>
            </Head>

            <main className={styles.container}>
                {/* Header */}
                <header className={styles.header}>
                    <div className={styles.headerLeft}>
                        <Link href="/automation" className={styles.backLink}>← Automation</Link>
                        <h1>🧪 Mock Market Simulation</h1>
                    </div>
                    <div className={styles.headerRight}>
                        <span className={styles.badgeSim}>SIM MODE</span>
                        <span className={`${styles.badge} ${status?.clock?.is_market_hours ? styles.badgeGreen : styles.badgeGray}`}>
                            {status?.clock?.is_market_hours ? '🟢 Market Open' : '🔴 Market Closed'}
                        </span>
                        <button onClick={fetchStatus} className={styles.refreshBtn}>
                            🔄 Refresh
                        </button>
                    </div>
                </header>

                {loading ? (
                    <div className={styles.loading}>Loading simulation state...</div>
                ) : (
                    <>
                        {/* Main Grid */}
                        <div className={styles.grid}>
                            {/* Clock Control Card */}
                            <div className={styles.card}>
                                <div className={styles.cardHeader}>
                                    <h2>⏰ Clock Controls</h2>
                                </div>
                                <div className={styles.cardBody}>
                                    {/* Current SIM Time Display */}
                                    <div className={styles.clockDisplay}>
                                        <div className={styles.clockDate}>
                                            {formatDate(status?.clock?.current_time)}
                                        </div>
                                        <div className={styles.clockTime}>
                                            {formatTime(status?.clock?.current_time)}
                                        </div>
                                    </div>

                                    {/* Day Controls */}
                                    <div className={styles.controlRow}>
                                        <span className={styles.controlLabel}>Day:</span>
                                        <div className={styles.controlButtons}>
                                            <button
                                                onClick={() => advanceDays(-1)}
                                                className={styles.btnControl}
                                                disabled={actionLoading !== null}
                                            >
                                                ◀ -1
                                            </button>
                                            <button
                                                onClick={() => advanceDays(1)}
                                                className={styles.btnControl}
                                                disabled={actionLoading !== null}
                                            >
                                                +1 ▶
                                            </button>
                                        </div>
                                    </div>

                                    {/* Hour Controls */}
                                    <div className={styles.controlRow}>
                                        <span className={styles.controlLabel}>Hour:</span>
                                        <div className={styles.controlButtons}>
                                            <button
                                                onClick={() => advanceTime(-60)}
                                                className={styles.btnControl}
                                                disabled={actionLoading !== null}
                                            >
                                                ◀ -1
                                            </button>
                                            <button
                                                onClick={() => advanceTime(60)}
                                                className={styles.btnControl}
                                                disabled={actionLoading !== null}
                                            >
                                                +1 ▶
                                            </button>
                                        </div>
                                    </div>

                                    {/* Quick Advance Targets */}
                                    <div className={styles.quickAdvance}>
                                        <button
                                            onClick={() => advanceToTime('15:45')}
                                            className={styles.btnQuickAdvance}
                                            disabled={actionLoading !== null}
                                            title="Advance to 3:45 PM - Operational EOD window"
                                        >
                                            → 3:45 PM
                                        </button>
                                        <button
                                            onClick={() => advanceToTime('16:00')}
                                            className={styles.btnQuickAdvance}
                                            disabled={actionLoading !== null}
                                            title="Advance to 4:00 PM - Market Close"
                                        >
                                            → 4:00 PM
                                        </button>
                                    </div>
                                </div>
                                <div className={styles.cardActions}>
                                    <button
                                        onClick={resetSimulation}
                                        className={styles.btnDanger}
                                        disabled={actionLoading === 'Reset'}
                                    >
                                        {actionLoading === 'Reset' ? '...' : '🔄 Reset Sim'}
                                    </button>
                                </div>
                            </div>

                            {/* Stats Dashboard Card */}
                            <div className={styles.card}>
                                <div className={styles.cardHeader}>
                                    <h2>📊 Stats Dashboard</h2>
                                </div>
                                <div className={styles.cardBody}>
                                    <div className={styles.statsGrid}>
                                        <div className={styles.statBox}>
                                            <div className={styles.statValue}>
                                                {formatCurrency(positions?.account?.cash || 100000)}
                                            </div>
                                            <div className={styles.statLabel}>Cash</div>
                                        </div>
                                        <div className={styles.statBox}>
                                            <div className={styles.statValue}>
                                                {formatCurrency(positions?.account?.portfolio_value || 100000)}
                                            </div>
                                            <div className={styles.statLabel}>Equity</div>
                                        </div>
                                        <div className={styles.statBox}>
                                            <div className={`${styles.statValue} ${(positions?.account?.unrealized_pnl || 0) >= 0 ? styles.pnlPositive : styles.pnlNegative}`}>
                                                {formatPnL(positions?.account?.unrealized_pnl || 0)}
                                            </div>
                                            <div className={styles.statLabel}>Unrealized P&L</div>
                                        </div>
                                        <div className={styles.statBox}>
                                            <div className={`${styles.statValue} ${(positions?.account?.realized_pnl || 0) >= 0 ? styles.pnlPositive : styles.pnlNegative}`}>
                                                {formatPnL(positions?.account?.realized_pnl || 0)}
                                            </div>
                                            <div className={styles.statLabel}>Realized P&L</div>
                                        </div>
                                    </div>

                                    {/* Position Count */}
                                    <div className={styles.positionCount}>
                                        <span>📈 Open Positions:</span>
                                        <strong>{positions?.count || 0}</strong>
                                    </div>

                                    {/* Positions Table */}
                                    {positions && positions.positions.length > 0 && (
                                        <div className={styles.positionsTable}>
                                            <table>
                                                <thead>
                                                    <tr>
                                                        <th>Symbol</th>
                                                        <th>Qty</th>
                                                        <th>Avg Price</th>
                                                        <th>Value</th>
                                                        <th>P&L</th>
                                                        <th>Stop</th>
                                                    </tr>
                                                </thead>
                                                <tbody>
                                                    {positions.positions.map((pos) => (
                                                        <tr key={pos.symbol}>
                                                            <td className={styles.symbol}>{pos.symbol}</td>
                                                            <td>{pos.qty}</td>
                                                            <td>${pos.avg_price.toFixed(2)}</td>
                                                            <td>{formatCurrency(pos.market_value)}</td>
                                                            <td className={pos.unrealized_pnl >= 0 ? styles.pnlPositive : styles.pnlNegative}>
                                                                {formatPnL(pos.unrealized_pnl)} ({pos.pnl_percent.toFixed(1)}%)
                                                            </td>
                                                            <td>{pos.stop_price ? `$${pos.stop_price.toFixed(2)}` : '-'}</td>
                                                        </tr>
                                                    ))}
                                                </tbody>
                                            </table>
                                        </div>
                                    )}
                                </div>
                            </div>

                            {/* Scenario Builder Card */}
                            <div className={`${styles.card} ${styles.scenarioCard}`}>
                                <div className={styles.cardHeader}>
                                    <h2>🎬 Scenario Builder</h2>
                                </div>
                                <div className={styles.cardBody}>
                                    {/* Load Historical Data */}
                                    <div className={styles.scenarioSection}>
                                        <h3>Load Historical Data</h3>
                                        <div className={styles.formRow}>
                                            <input
                                                type="text"
                                                placeholder="Symbol (e.g., SMCI)"
                                                value={loadSymbol}
                                                onChange={(e) => setLoadSymbol(e.target.value.toUpperCase())}
                                                className={styles.input}
                                            />
                                        </div>
                                        <div className={styles.formRow}>
                                            <input
                                                type="date"
                                                value={loadStartDate}
                                                onChange={(e) => setLoadStartDate(e.target.value)}
                                                className={styles.input}
                                            />
                                            <span className={styles.dateSeparator}>to</span>
                                            <input
                                                type="date"
                                                value={loadEndDate}
                                                onChange={(e) => setLoadEndDate(e.target.value)}
                                                className={styles.input}
                                            />
                                        </div>
                                        <button
                                            onClick={loadHistorical}
                                            className={styles.btnSecondary}
                                            disabled={actionLoading !== null}
                                        >
                                            📥 Load Historical
                                        </button>
                                    </div>

                                    {/* Curated Test Cases */}
                                    <div className={styles.scenarioSection}>
                                        <h3>Curated Test Cases</h3>
                                        {testCases.length > 0 ? (
                                            <div className={styles.testCaseList}>
                                                {testCases.map((tc) => (
                                                    <button
                                                        key={tc.id}
                                                        onClick={() => loadTestCase(tc.id)}
                                                        className={styles.testCaseBtn}
                                                        disabled={actionLoading !== null}
                                                        title={tc.description}
                                                    >
                                                        <span className={styles.tcName}>{tc.name}</span>
                                                        <span className={styles.tcMeta}>{tc.symbol} • {tc.setup_type}</span>
                                                    </button>
                                                ))}
                                            </div>
                                        ) : (
                                            <p className={styles.emptyMessage}>No test cases loaded</p>
                                        )}
                                    </div>

                                    {/* Synthetic Pattern Injection */}
                                    <div className={styles.scenarioSection}>
                                        <h3>Inject Synthetic Pattern</h3>
                                        <div className={styles.patternButtons}>
                                            <button
                                                onClick={() => injectPattern('ep')}
                                                className={styles.btnPattern}
                                                disabled={actionLoading !== null}
                                            >
                                                ⚡ EP
                                            </button>
                                            <button
                                                onClick={() => injectPattern('htf')}
                                                className={styles.btnPattern}
                                                disabled={actionLoading !== null}
                                            >
                                                📈 HTF
                                            </button>
                                            <button
                                                onClick={() => injectPattern('breakout')}
                                                className={styles.btnPattern}
                                                disabled={actionLoading !== null}
                                            >
                                                🚀 Breakout
                                            </button>
                                        </div>
                                    </div>
                                </div>
                            </div>

                            {/* Diagnostic Panel Card */}
                            <div className={styles.card}>
                                <div className={styles.cardHeader}>
                                    <h2>🔧 Diagnostics</h2>
                                </div>
                                <div className={styles.cardBody}>
                                    <div className={styles.diagnosticButtons}>
                                        <button
                                            onClick={runDiagnosticScan}
                                            className={styles.btnSecondary}
                                            disabled={actionLoading === 'diagnostic'}
                                            title="Run all scanners (EP, Breakout, HTF) against loaded simulation data. Shows which candidates pass/fail filtering and why. Does NOT execute trades."
                                        >
                                            {actionLoading === 'diagnostic' ? '...' : '🔍 Run Diagnostic Scan'}
                                        </button>
                                        <button
                                            onClick={executePath}
                                            className={styles.btnSecondary}
                                            disabled={actionLoading !== null}
                                            title="Debug tool: Traces what execute_callback does. Checks sim_mode setting, runs scanner, but does NOT submit orders. Use Scheduler for actual trade execution."
                                        >
                                            ▶️ Execute Path
                                        </button>
                                    </div>

                                    {/* Diagnostic Results */}
                                    {showDiagnostics && diagnostics && (
                                        <div className={styles.diagnosticResults}>
                                            <h4>Scan Results</h4>
                                            {diagnostics.map((d, i) => (
                                                <div key={i} className={styles.scannerResult}>
                                                    <div className={styles.scannerHeader}>
                                                        <strong>{d.scanner.toUpperCase()}</strong>
                                                        {d.enabled ? (
                                                            <span className={styles.badgeSmall}>
                                                                {d.candidates_found} → {d.candidates_passed}
                                                            </span>
                                                        ) : (
                                                            <span className={styles.badgeDisabled}>SKIPPED</span>
                                                        )}
                                                    </div>
                                                    {d.rejections.length > 0 && (
                                                        <div className={styles.rejections}>
                                                            {d.rejections.slice(0, 3).map((r, j) => (
                                                                <div key={j} className={styles.rejection}>
                                                                    ❌ {r.symbol}: {r.reason.replace(/_/g, ' ')}
                                                                </div>
                                                            ))}
                                                            {d.rejections.length > 3 && (
                                                                <div className={styles.moreRejections}>
                                                                    ...and {d.rejections.length - 3} more
                                                                </div>
                                                            )}
                                                        </div>
                                                    )}
                                                </div>
                                            ))}
                                        </div>
                                    )}

                                    {/* Market Data Info */}
                                    <div className={styles.marketDataInfo}>
                                        <div className={styles.stat}>
                                            <span>Symbols Loaded:</span>
                                            <strong>{status?.market_data?.symbols_loaded || 0}</strong>
                                        </div>
                                        {status?.market_data?.date_range && (
                                            <div className={styles.stat}>
                                                <span>Date Range:</span>
                                                <strong>
                                                    {status.market_data.date_range.start} → {status.market_data.date_range.end}
                                                </strong>
                                            </div>
                                        )}
                                    </div>
                                </div>
                            </div>
                        </div>

                        {/* Event Log */}
                        <div className={styles.eventLogCard}>
                            <div className={styles.cardHeader}>
                                <h2>📜 Event Log</h2>
                                <button
                                    onClick={() => setEventLog([])}
                                    className={styles.clearBtn}
                                >
                                    Clear
                                </button>
                            </div>
                            <div className={styles.eventLog}>
                                {eventLog.length === 0 ? (
                                    <p className={styles.emptyLog}>No events yet. Start interacting with the simulation!</p>
                                ) : (
                                    eventLog.map((log, i) => (
                                        <div key={i} className={styles.logEntry}>{log}</div>
                                    ))
                                )}
                            </div>
                        </div>
                    </>
                )}
            </main>
        </>
    )
}
