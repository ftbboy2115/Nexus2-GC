import { useState, useEffect, useCallback } from 'react'
import Head from 'next/head'
import Link from 'next/link'
import styles from '@/styles/Warrior.module.css'

// ============================================================================
// Type Definitions
// ============================================================================

interface WarriorStatus {
    state: string
    trading_window: boolean
    market_hours: boolean
    watchlist_count: number
    watchlist: WatchedCandidate[]
    stats: {
        started_at: string | null
        scans_run: number
        candidates_found: number
        entries_triggered: number
        orders_submitted: number
        daily_pnl: number
        last_scan_at: string | null
        last_error: string | null
    }
    monitor: {
        running: boolean
        positions_count: number
        check_interval_seconds: number
        checks_run: number
        exits_triggered: number
        partials_triggered: number
        last_check: string | null
        last_error: string | null
        settings: {
            mental_stop_cents: number
            profit_target_r: number
            partial_exit_fraction: number
            candle_under_candle: boolean
            topping_tail: boolean
        }
    }
    config: {
        sim_only: boolean
        risk_per_trade: number
        max_positions: number
        max_daily_loss: number
        orb_enabled: boolean
        pmh_enabled: boolean
    }
}

interface WatchedCandidate {
    symbol: string
    pmh: number
    orb_high: number | null
    orb_established: boolean
    entry_triggered: boolean
}

interface WarriorCandidate {
    symbol: string
    name: string
    price: number
    gap_percent: number
    relative_volume: number
    float_shares: number | null
    catalyst_type: string
    catalyst_description: string
    quality_score: number
    is_ideal_float: boolean
    is_ideal_rvol: boolean
    is_ideal_gap: boolean
}

interface ScanResult {
    candidates: WarriorCandidate[]
    processed_count: number
    filtered_count: number
    avg_rvol: number
    avg_gap: number
}

interface WarriorPosition {
    position_id: string
    symbol: string
    entry_price: number
    shares: number
    current_stop: number
    profit_target: number
    partial_taken: boolean
    high_since_entry: number
    entry_time: string | null
}

// ============================================================================
// Main Component
// ============================================================================

export default function Warrior() {
    // Core state
    const [status, setStatus] = useState<WarriorStatus | null>(null)
    const [scanResult, setScanResult] = useState<ScanResult | null>(null)
    const [positions, setPositions] = useState<WarriorPosition[]>([])
    const [loading, setLoading] = useState(true)
    const [actionLoading, setActionLoading] = useState<string | null>(null)

    // Event log
    const [eventLog, setEventLog] = useState<string[]>([])

    // Use relative URLs - Next.js rewrites proxy to backend
    const API_BASE = ''

    // ========================================================================
    // Data Fetching
    // ========================================================================

    const fetchStatus = useCallback(async () => {
        try {
            const [statusRes, positionsRes] = await Promise.all([
                fetch(`${API_BASE}/warrior/status`),
                fetch(`${API_BASE}/warrior/positions`),
            ])

            if (statusRes.ok) setStatus(await statusRes.json())
            if (positionsRes.ok) {
                const data = await positionsRes.json()
                setPositions(data.positions || [])
            }
        } catch (err) {
            console.error('Error fetching Warrior status:', err)
            addToLog('❌ Failed to connect to backend')
        } finally {
            setLoading(false)
        }
    }, [])

    useEffect(() => {
        fetchStatus()
        const interval = setInterval(fetchStatus, 5000) // Refresh every 5s
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
        method: 'GET' | 'POST' | 'PUT' = 'POST',
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
                addToLog(`✅ ${actionId}: ${data.status || 'Success'}`)
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

    // Engine Controls
    const startEngine = () => handleAction('Start Engine', '/warrior/start')
    const stopEngine = () => handleAction('Stop Engine', '/warrior/stop')
    const pauseEngine = () => handleAction('Pause Engine', '/warrior/pause')
    const resumeEngine = () => handleAction('Resume Engine', '/warrior/resume')

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

    const formatFloat = (shares: number | null) => {
        if (!shares) return '-'
        if (shares >= 1_000_000) return `${(shares / 1_000_000).toFixed(1)}M`
        if (shares >= 1_000) return `${(shares / 1_000).toFixed(0)}K`
        return shares.toString()
    }

    const formatTime = (iso: string | null) => {
        if (!iso) return '-'
        return new Date(iso).toLocaleTimeString()
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
                        <span className={`${styles.badge} ${status?.config?.sim_only ? styles.badgeSim : styles.badgeLive}`}>
                            {status?.config?.sim_only ? '🧪 SIM' : '🔴 LIVE'}
                        </span>
                        <span className={`${styles.badge} ${status?.trading_window ? styles.badgeGreen : styles.badgeGray}`}>
                            {status?.trading_window ? '🟢 Trading Window' : '⚫ Outside Window'}
                        </span>
                        <button onClick={fetchStatus} className={styles.refreshBtn}>
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
                            <div className={styles.card}>
                                <div className={styles.cardHeader}>
                                    <h2>🎛️ Engine Control</h2>
                                    <span className={`${styles.stateBadge} ${styles[`state${status?.state}`]}`}>
                                        {status?.state?.toUpperCase() || 'UNKNOWN'}
                                    </span>
                                </div>
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
                                            <div className={`${styles.statValue} ${(status?.stats.daily_pnl || 0) >= 0 ? styles.pnlPositive : styles.pnlNegative}`}>
                                                {formatPnL(status?.stats.daily_pnl || 0)}
                                            </div>
                                            <div className={styles.statLabel}>Daily P&L</div>
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
                                    </div>
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
                            </div>

                            {/* Monitor Settings Card */}
                            <div className={styles.card}>
                                <div className={styles.cardHeader}>
                                    <h2>🛡️ Exit Rules</h2>
                                    <span className={`${styles.badge} ${status?.monitor.running ? styles.badgeGreen : styles.badgeGray}`}>
                                        {status?.monitor.running ? 'Active' : 'Inactive'}
                                    </span>
                                </div>
                                <div className={styles.cardBody}>
                                    <div className={styles.rulesList}>
                                        <div className={styles.ruleItem}>
                                            <span className={styles.ruleLabel}>Mental Stop</span>
                                            <span className={styles.ruleValue}>{status?.monitor.settings.mental_stop_cents || 15}¢</span>
                                        </div>
                                        <div className={styles.ruleItem}>
                                            <span className={styles.ruleLabel}>Profit Target</span>
                                            <span className={styles.ruleValue}>{status?.monitor.settings.profit_target_r || 2}:1 R</span>
                                        </div>
                                        <div className={styles.ruleItem}>
                                            <span className={styles.ruleLabel}>Partial Exit</span>
                                            <span className={styles.ruleValue}>{(status?.monitor.settings.partial_exit_fraction || 0.5) * 100}%</span>
                                        </div>
                                        <div className={styles.ruleItem}>
                                            <span className={styles.ruleLabel}>Candle-Under-Candle</span>
                                            <span className={styles.ruleValue}>{status?.monitor.settings.candle_under_candle ? '✅' : '❌'}</span>
                                        </div>
                                        <div className={styles.ruleItem}>
                                            <span className={styles.ruleLabel}>Topping Tail</span>
                                            <span className={styles.ruleValue}>{status?.monitor.settings.topping_tail ? '✅' : '❌'}</span>
                                        </div>
                                    </div>

                                    {/* Monitor Stats */}
                                    <div className={styles.monitorStats}>
                                        <span>Checks: {status?.monitor.checks_run || 0}</span>
                                        <span>Exits: {status?.monitor.exits_triggered || 0}</span>
                                        <span>Partials: {status?.monitor.partials_triggered || 0}</span>
                                    </div>
                                </div>
                            </div>

                            {/* Scanner Card */}
                            <div className={styles.card}>
                                <div className={styles.cardHeader}>
                                    <h2>🔍 Scanner</h2>
                                    <button
                                        onClick={runScan}
                                        className={styles.btnSmall}
                                        disabled={actionLoading === 'scan'}
                                    >
                                        {actionLoading === 'scan' ? '...' : 'Run Scan'}
                                    </button>
                                </div>
                                <div className={styles.cardBody}>
                                    {scanResult ? (
                                        <>
                                            <div className={styles.scanStats}>
                                                <span>Processed: {scanResult.processed_count}</span>
                                                <span>Passed: {scanResult.candidates.length}</span>
                                                <span>Avg RVOL: {scanResult.avg_rvol.toFixed(1)}x</span>
                                                <span>Avg Gap: {scanResult.avg_gap.toFixed(1)}%</span>
                                            </div>

                                            {scanResult.candidates.length > 0 ? (
                                                <div className={styles.candidateTable}>
                                                    <table>
                                                        <thead>
                                                            <tr>
                                                                <th>Symbol</th>
                                                                <th>Price</th>
                                                                <th>Gap%</th>
                                                                <th>RVOL</th>
                                                                <th>Float</th>
                                                                <th>Catalyst</th>
                                                                <th>Score</th>
                                                            </tr>
                                                        </thead>
                                                        <tbody>
                                                            {scanResult.candidates.slice(0, 10).map((c) => (
                                                                <tr key={c.symbol}>
                                                                    <td className={styles.symbol}>{c.symbol}</td>
                                                                    <td>${c.price.toFixed(2)}</td>
                                                                    <td className={c.is_ideal_gap ? styles.ideal : ''}>
                                                                        {c.gap_percent.toFixed(1)}%
                                                                    </td>
                                                                    <td className={c.is_ideal_rvol ? styles.ideal : ''}>
                                                                        {c.relative_volume.toFixed(1)}x
                                                                    </td>
                                                                    <td className={c.is_ideal_float ? styles.ideal : ''}>
                                                                        {formatFloat(c.float_shares)}
                                                                    </td>
                                                                    <td title={c.catalyst_description}>
                                                                        {c.catalyst_type === 'earnings' ? '📊' :
                                                                            c.catalyst_type === 'news' ? '📰' :
                                                                                c.catalyst_type === 'former_runner' ? '🏃' : '-'}
                                                                    </td>
                                                                    <td className={styles.score}>
                                                                        <span className={`${styles.scoreBar} ${styles[`score${Math.min(10, Math.max(0, c.quality_score))}`]}`}>
                                                                            {c.quality_score}/10
                                                                        </span>
                                                                    </td>
                                                                </tr>
                                                            ))}
                                                        </tbody>
                                                    </table>
                                                </div>
                                            ) : (
                                                <p className={styles.emptyMessage}>No candidates found</p>
                                            )}
                                        </>
                                    ) : (
                                        <p className={styles.emptyMessage}>Click "Run Scan" to find candidates</p>
                                    )}
                                </div>
                            </div>

                            {/* Watchlist Card */}
                            <div className={styles.card}>
                                <div className={styles.cardHeader}>
                                    <h2>👁️ Watchlist</h2>
                                    <span className={styles.countBadge}>{status?.watchlist_count || 0}</span>
                                </div>
                                <div className={styles.cardBody}>
                                    {status?.watchlist && status.watchlist.length > 0 ? (
                                        <div className={styles.watchlistTable}>
                                            <table>
                                                <thead>
                                                    <tr>
                                                        <th>Symbol</th>
                                                        <th>PMH</th>
                                                        <th>ORB High</th>
                                                        <th>Status</th>
                                                    </tr>
                                                </thead>
                                                <tbody>
                                                    {status.watchlist.map((w) => (
                                                        <tr key={w.symbol} className={w.entry_triggered ? styles.triggered : ''}>
                                                            <td className={styles.symbol}>{w.symbol}</td>
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
                            </div>
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
                                                <th>High</th>
                                                <th>Partial?</th>
                                                <th>Time</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {positions.map((p) => (
                                                <tr key={p.position_id}>
                                                    <td className={styles.symbol}>{p.symbol}</td>
                                                    <td>{p.shares}</td>
                                                    <td>${p.entry_price.toFixed(2)}</td>
                                                    <td className={styles.stopPrice}>${p.current_stop.toFixed(2)}</td>
                                                    <td className={styles.targetPrice}>${p.profit_target.toFixed(2)}</td>
                                                    <td>${p.high_since_entry.toFixed(2)}</td>
                                                    <td>{p.partial_taken ? '✅' : '-'}</td>
                                                    <td>{formatTime(p.entry_time)}</td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        )}

                        {/* Event Log */}
                        <div className={styles.eventLogCard}>
                            <div className={styles.cardHeader}>
                                <h2>📜 Event Log</h2>
                                <button onClick={() => setEventLog([])} className={styles.clearBtn}>
                                    Clear
                                </button>
                            </div>
                            <div className={styles.eventLog}>
                                {eventLog.length === 0 ? (
                                    <p className={styles.emptyLog}>No events yet</p>
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
