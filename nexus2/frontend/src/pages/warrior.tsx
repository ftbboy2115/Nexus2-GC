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
        next_scan: string | null
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
        max_candidates: number
        scanner_interval_minutes: number
        max_daily_loss: number
        orb_enabled: boolean
        pmh_enabled: boolean
        max_shares_per_trade?: number
    }
    auto_enable?: boolean  // Auto-enable on server startup
    last_scan_result?: {
        scan_time: string
        processed_count: number
        candidates: {
            symbol: string
            gap_percent: number
            rvol: number
            float_shares: number
            price: number
            in_watchlist: boolean
        }[]
    }
}

interface WatchedCandidate {
    symbol: string
    gap_percent: number
    rvol: number
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

interface SimStatus {
    sim_enabled: boolean
    message?: string
    account?: {
        cash: number
        portfolio_value: number
        unrealized_pnl: number
        realized_pnl: number
    }
    positions?: Array<{
        symbol: string
        qty: number
        avg_price: number
        market_value: number
        unrealized_pnl: number
        pnl_percent: number
        stop_price: number
    }>
    position_count?: number
}

interface BrokerStatus {
    broker_enabled: boolean
    paper_mode?: boolean
    account_value?: number
    positions_count?: number
    realized_pnl_today?: number
    unrealized_pnl?: number
    total_daily_pnl?: number
    invested_capital?: number
    peak_exposure?: number
    total_capital_deployed?: number
    daily_pnl_percent?: number
    error?: string
}

// ============================================================================
// Collapsible Card Component
// ============================================================================

interface CollapsibleCardProps {
    id: string
    title: string
    badge?: React.ReactNode
    children: React.ReactNode
    defaultCollapsed?: boolean
}

const getCollapsedState = (): Record<string, boolean> => {
    if (typeof window !== 'undefined') {
        try {
            const saved = localStorage.getItem('warrior-collapsed-cards')
            return saved ? JSON.parse(saved) : {}
        } catch {
            return {}
        }
    }
    return {}
}

const setCollapsedState = (cardId: string, collapsed: boolean) => {
    if (typeof window !== 'undefined') {
        const current = getCollapsedState()
        current[cardId] = collapsed
        localStorage.setItem('warrior-collapsed-cards', JSON.stringify(current))
    }
}

function CollapsibleCard({ id, title, badge, children, defaultCollapsed = false }: CollapsibleCardProps) {
    const [collapsed, setCollapsed] = useState(() => {
        const saved = getCollapsedState()
        return saved[id] ?? defaultCollapsed
    })

    const toggle = () => {
        const newState = !collapsed
        setCollapsed(newState)
        setCollapsedState(id, newState)
    }

    return (
        <div className={styles.card}>
            <div
                className={styles.cardHeader}
                onClick={toggle}
                style={{
                    cursor: 'pointer',
                    borderBottom: collapsed ? 'none' : undefined
                }}
            >
                <h2>{title}</h2>
                <div className={styles.headerRight}>
                    {badge}
                    <span className={styles.collapseToggle}>{collapsed ? '▶' : '▼'}</span>
                </div>
            </div>
            {!collapsed && children}
        </div>
    )
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

    // Simulation state
    const [simStatus, setSimStatus] = useState<SimStatus | null>(null)

    // Broker status (for live P&L)
    const [brokerStatus, setBrokerStatus] = useState<BrokerStatus | null>(null)

    // Mock Market state
    const [testCases, setTestCases] = useState<{ id: string, symbol: string, description: string }[]>([])
    const [selectedTestCase, setSelectedTestCase] = useState<string>('')
    const [loadedTestCase, setLoadedTestCase] = useState<{ symbol: string, price: number } | null>(null)

    // Event log
    const [eventLog, setEventLog] = useState<string[]>([])

    // Sorting state for tables
    const [watchlistSort, setWatchlistSort] = useState<{ key: string, dir: 'asc' | 'desc' }>({ key: 'gap_percent', dir: 'desc' })
    const [engineScanSort, setEngineScanSort] = useState<{ key: string, dir: 'asc' | 'desc' }>({ key: 'gap_percent', dir: 'desc' })

    // Countdown timer state
    const [countdown, setCountdown] = useState<string>('')

    // Trade events log
    const [tradeEvents, setTradeEvents] = useState<any[]>([])
    const [showTradeEvents, setShowTradeEvents] = useState(() => {
        if (typeof window !== 'undefined') {
            return localStorage.getItem('warrior_showTradeEvents') === 'true'
        }
        return false
    })

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

    // Use relative URLs - Next.js rewrites proxy to backend
    const API_BASE = ''

    // Open TradingView chart in new tab
    const openChart = (symbol: string) => {
        window.open(`https://www.tradingview.com/chart/?symbol=${symbol}`, '_blank')
    }

    // ========================================================================
    // Data Fetching
    // ========================================================================

    const fetchStatus = useCallback(async () => {
        try {
            const [statusRes, positionsRes, simRes, brokerRes] = await Promise.all([
                fetch(`${API_BASE}/warrior/status`),
                fetch(`${API_BASE}/warrior/positions`),
                fetch(`${API_BASE}/warrior/sim/status`),
                fetch(`${API_BASE}/warrior/broker/status`),
            ])

            if (statusRes.ok) setStatus(await statusRes.json())
            if (positionsRes.ok) {
                const data = await positionsRes.json()
                setPositions(data.positions || [])
            }
            if (simRes.ok) setSimStatus(await simRes.json())
            if (brokerRes.ok) setBrokerStatus(await brokerRes.json())

            // Fetch recent Warrior trade events
            try {
                const eventsRes = await fetch(`${API_BASE}/trade-events/recent?strategy=WARRIOR&limit=20`)
                if (eventsRes.ok) {
                    const eventsData = await eventsRes.json()
                    setTradeEvents(eventsData.events || [])
                }
            } catch (err) {
                console.error('Error fetching Warrior trade events:', err)
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
        const interval = setInterval(fetchStatus, 1000) // Fast refresh for day trading
        return () => clearInterval(interval)
    }, [fetchStatus])

    // Sorting helpers
    const sortData = <T,>(data: T[], sortConfig: { key: string, dir: 'asc' | 'desc' }): T[] => {
        return [...data].sort((a, b) => {
            const aVal = (a as Record<string, unknown>)[sortConfig.key]
            const bVal = (b as Record<string, unknown>)[sortConfig.key]
            if (aVal == null) return 1
            if (bVal == null) return -1
            if (aVal < bVal) return sortConfig.dir === 'asc' ? -1 : 1
            if (aVal > bVal) return sortConfig.dir === 'asc' ? 1 : -1
            return 0
        })
    }

    const toggleSort = (
        key: string,
        current: { key: string, dir: 'asc' | 'desc' },
        setter: React.Dispatch<React.SetStateAction<{ key: string, dir: 'asc' | 'desc' }>>
    ) => {
        if (current.key === key) {
            setter({ key, dir: current.dir === 'asc' ? 'desc' : 'asc' })
        } else {
            setter({ key, dir: 'desc' })
        }
    }

    const SortHeader = ({ label, sortKey, sortConfig, onSort }: {
        label: string,
        sortKey: string,
        sortConfig: { key: string, dir: 'asc' | 'desc' },
        onSort: () => void
    }) => (
        <th onClick={onSort} style={{ cursor: 'pointer', userSelect: 'none' }}>
            {label} {sortConfig.key === sortKey ? (sortConfig.dir === 'asc' ? '▲' : '▼') : ''}
        </th>
    )

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

    // Simulation Controls
    const enableSim = () => handleAction('Enable Sim', '/warrior/sim/enable')
    const resetSim = () => handleAction('Reset Sim', '/warrior/sim/reset')
    const disableSim = () => handleAction('Disable Sim', '/warrior/sim/disable')

    // Broker Controls (Alpaca Paper)
    const enableBroker = () => handleAction('Enable Broker', '/warrior/broker/enable')

    // Auto-enable toggle
    const toggleAutoEnable = async () => {
        setActionLoading('autoEnable')
        try {
            const newValue = !status?.auto_enable
            const res = await fetch(`${API_BASE}/warrior/auto-enable`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ enabled: newValue }),
            })
            if (res.ok) {
                const data = await res.json()
                addToLog(`⚙️ Auto-enable ${newValue ? 'enabled' : 'disabled'}: takes effect on next restart`)
                await fetchStatus()
            } else {
                addToLog('❌ Failed to toggle auto-enable')
            }
        } catch (err) {
            addToLog('❌ Failed to toggle auto-enable')
        } finally {
            setActionLoading(null)
        }
    }

    // Config Updates
    const updateConfig = async (field: string, value: number | boolean) => {
        setActionLoading(`config-${field}`)
        try {
            const res = await fetch(`${API_BASE}/warrior/config`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ [field]: value }),
            })
            if (res.ok) {
                const data = await res.json()
                addToLog(`⚙️ Config updated: ${field} = ${value}`)
                await fetchStatus()
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
                await fetchStatus()
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
        return new Date(iso).toLocaleTimeString('en-US', {
            timeZone: 'America/New_York',
            hour: '2-digit',
            minute: '2-digit'
        }) + ' ET'
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
                            <CollapsibleCard
                                id="mockmarket"
                                title="🎮 Mock Market"
                                badge={loadedTestCase ? <span className={styles.badge}>{loadedTestCase.symbol}</span> : undefined}
                            >
                                <div className={styles.cardBody}>
                                    {/* Test Case Selector */}
                                    <div className={styles.testCaseSelector}>
                                        <select
                                            value={selectedTestCase}
                                            onChange={(e) => setSelectedTestCase(e.target.value)}
                                            className={styles.selectInput}
                                            title={testCases.find(tc => tc.id === selectedTestCase)?.description || ''}
                                        >
                                            <option value="">Select a test case...</option>
                                            {testCases.map((tc) => (
                                                <option key={tc.id} value={tc.id}>
                                                    {tc.symbol} - {tc.description.length > 40 ? tc.description.slice(0, 40) + '...' : tc.description}
                                                </option>
                                            ))}
                                        </select>
                                        <button
                                            onClick={loadTestCase}
                                            className={styles.btnPrimary}
                                            disabled={!selectedTestCase || actionLoading === 'loadTest'}
                                            style={{ flexShrink: 0 }}
                                        >
                                            {actionLoading === 'loadTest' ? '...' : '📦 Load'}
                                        </button>
                                    </div>

                                    {/* Price Controls */}
                                    {loadedTestCase && loadedTestCase.price != null && (
                                        <div className={styles.priceControls}>
                                            <div className={styles.priceDisplay}>
                                                <span className={styles.priceLabel}>Price:</span>
                                                <span className={styles.priceValue}>${loadedTestCase.price.toFixed(2)}</span>
                                            </div>
                                            <div className={styles.priceButtons}>
                                                <button
                                                    onClick={() => setMockPrice(loadedTestCase.symbol, loadedTestCase.price - 0.10)}
                                                    className={styles.btnSmall}
                                                >-10¢</button>
                                                <button
                                                    onClick={() => setMockPrice(loadedTestCase.symbol, loadedTestCase.price - 0.05)}
                                                    className={styles.btnSmall}
                                                >-5¢</button>
                                                <button
                                                    onClick={() => setMockPrice(loadedTestCase.symbol, loadedTestCase.price + 0.05)}
                                                    className={styles.btnSmall}
                                                >+5¢</button>
                                                <button
                                                    onClick={() => setMockPrice(loadedTestCase.symbol, loadedTestCase.price + 0.10)}
                                                    className={styles.btnSmall}
                                                >+10¢</button>
                                                <button
                                                    onClick={() => setMockPrice(loadedTestCase.symbol, loadedTestCase.price + 0.25)}
                                                    className={styles.btnPrimary}
                                                >+25¢ 🚀</button>
                                            </div>
                                        </div>
                                    )}

                                    {!loadedTestCase && !selectedTestCase && (
                                        <p className={styles.emptyMessage}>
                                            Select a test case to simulate price movements
                                        </p>
                                    )}
                                </div>
                            </CollapsibleCard>

                            {/* Monitor Settings Card */}
                            <CollapsibleCard
                                id="exitrules"
                                title="🛡️ Exit Rules"
                                badge={
                                    <span className={`${styles.badge} ${status?.monitor.running ? styles.badgeGreen : styles.badgeGray}`}>
                                        {status?.monitor.running ? 'Active' : 'Inactive'}
                                    </span>
                                }
                            >
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
                            </CollapsibleCard>

                            {/* Settings Card */}
                            <CollapsibleCard
                                id="settings"
                                title="⚙️ Settings"
                            >
                                <div className={styles.cardBody}>
                                    <div className={styles.settingsGrid}>
                                        <div className={styles.settingItem}>
                                            <label>Max Candidates</label>
                                            <div className={styles.settingControl}>
                                                <button
                                                    onClick={() => updateConfig('max_candidates', Math.max(1, (status?.config.max_candidates || 5) - 1))}
                                                    className={styles.btnSmall}
                                                >-</button>
                                                <span>{status?.config.max_candidates || 5}</span>
                                                <button
                                                    onClick={() => updateConfig('max_candidates', Math.min(20, (status?.config.max_candidates || 5) + 1))}
                                                    className={styles.btnSmall}
                                                >+</button>
                                            </div>
                                        </div>
                                        <div className={styles.settingItem}>
                                            <label>Scan Interval (min)</label>
                                            <div className={styles.settingControl}>
                                                <button
                                                    onClick={() => updateConfig('scanner_interval_minutes', Math.max(1, (status?.config.scanner_interval_minutes || 5) - 1))}
                                                    className={styles.btnSmall}
                                                >-</button>
                                                <span>{status?.config.scanner_interval_minutes || 5}</span>
                                                <button
                                                    onClick={() => updateConfig('scanner_interval_minutes', Math.min(30, (status?.config.scanner_interval_minutes || 5) + 1))}
                                                    className={styles.btnSmall}
                                                >+</button>
                                            </div>
                                        </div>
                                        <div className={styles.settingItem}>
                                            <label>Risk/Trade ($)</label>
                                            <div className={styles.settingControl}>
                                                <button
                                                    onClick={() => updateConfig('risk_per_trade', Math.max(25, (status?.config.risk_per_trade || 100) - 25))}
                                                    className={styles.btnSmall}
                                                >-</button>
                                                <span>${status?.config.risk_per_trade || 100}</span>
                                                <button
                                                    onClick={() => updateConfig('risk_per_trade', Math.min(500, (status?.config.risk_per_trade || 100) + 25))}
                                                    className={styles.btnSmall}
                                                >+</button>
                                            </div>
                                        </div>
                                        <div className={styles.settingItem}>
                                            <label>Max Positions</label>
                                            <div className={styles.settingControl}>
                                                <button
                                                    onClick={() => updateConfig('max_positions', Math.max(1, (status?.config.max_positions || 3) - 1))}
                                                    className={styles.btnSmall}
                                                >-</button>
                                                <span>{status?.config.max_positions || 3}</span>
                                                <button
                                                    onClick={() => updateConfig('max_positions', Math.min(20, (status?.config.max_positions || 3) + 1))}
                                                    className={styles.btnSmall}
                                                >+</button>
                                            </div>
                                        </div>
                                        <div className={styles.settingItem}>
                                            <label>Max Shares/Trade</label>
                                            <div className={styles.settingControl}>
                                                <button
                                                    onClick={() => updateConfig('max_shares_per_trade', Math.max(10, (status?.config.max_shares_per_trade || 100) - 10))}
                                                    className={styles.btnSmall}
                                                >-</button>
                                                <span>{status?.config.max_shares_per_trade || 100}</span>
                                                <button
                                                    onClick={() => updateConfig('max_shares_per_trade', Math.min(1000, (status?.config.max_shares_per_trade || 100) + 10))}
                                                    className={styles.btnSmall}
                                                >+</button>
                                            </div>
                                        </div>
                                    </div>

                                    {/* Entry Mode Toggles */}
                                    <div className={styles.entryModeToggles}>
                                        <button
                                            onClick={() => updateConfig('orb_enabled', !status?.config.orb_enabled)}
                                            className={status?.config.orb_enabled ? styles.btnToggleOn : styles.btnToggleOff}
                                        >
                                            {status?.config.orb_enabled ? '✅' : '❌'} ORB
                                        </button>
                                        <button
                                            onClick={() => updateConfig('pmh_enabled', !status?.config.pmh_enabled)}
                                            className={status?.config.pmh_enabled ? styles.btnToggleOn : styles.btnToggleOff}
                                        >
                                            {status?.config.pmh_enabled ? '✅' : '❌'} PMH
                                        </button>
                                    </div>
                                </div>
                            </CollapsibleCard>

                            {/* Positions Card */}
                            <CollapsibleCard
                                id="positions"
                                title="📊 Positions"
                                badge={positions.length > 0 ? (
                                    <span className={styles.badge}>{positions.length}</span>
                                ) : undefined}
                            >
                                <div className={styles.cardBody}>
                                    {positions.length === 0 ? (
                                        <div className={styles.noData}>No open positions</div>
                                    ) : (
                                        <div className={styles.candidateTable}>
                                            <table>
                                                <thead>
                                                    <tr>
                                                        <th>Symbol</th>
                                                        <th>Shares</th>
                                                        <th>Entry</th>
                                                        <th>Stop</th>
                                                        <th>Target</th>
                                                        <th>Partial</th>
                                                    </tr>
                                                </thead>
                                                <tbody>
                                                    {positions.map((pos) => (
                                                        <tr key={pos.position_id}>
                                                            <td className={styles.symbolCell}>
                                                                <span
                                                                    className={styles.clickableSymbol}
                                                                    onClick={() => openChart(pos.symbol)}
                                                                    title="Open TradingView chart"
                                                                >
                                                                    {pos.symbol}
                                                                </span>
                                                            </td>
                                                            <td>{pos.shares}</td>
                                                            <td>${pos.entry_price.toFixed(2)}</td>
                                                            <td className={styles.stopCell}>
                                                                ${pos.current_stop.toFixed(2)}
                                                            </td>
                                                            <td className={styles.targetCell}>
                                                                ${pos.profit_target.toFixed(2)}
                                                            </td>
                                                            <td>
                                                                {pos.partial_taken ? '✅' : '—'}
                                                            </td>
                                                        </tr>
                                                    ))}
                                                </tbody>
                                            </table>
                                        </div>
                                    )}
                                </div>
                            </CollapsibleCard>

                            {/* Scanner Card */}
                            <CollapsibleCard
                                id="scanner"
                                title="🔍 Scanner"
                                badge={
                                    <button
                                        onClick={(e) => { e.stopPropagation(); runScan(); }}
                                        className={styles.btnSmall}
                                        disabled={actionLoading === 'scan'}
                                    >
                                        {actionLoading === 'scan' ? '...' : 'Run Scan'}
                                    </button>
                                }
                            >
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
                                                                    <td className={styles.symbol}>
                                                                        <span
                                                                            className={styles.clickableSymbol}
                                                                            onClick={() => openChart(c.symbol)}
                                                                            title="Open TradingView chart"
                                                                        >
                                                                            {c.symbol}
                                                                        </span>
                                                                    </td>
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
                            </CollapsibleCard>

                            {/* Last Engine Scan Card */}
                            <CollapsibleCard
                                id="engineScan"
                                title="📊 Last Engine Scan"
                                badge={
                                    status?.last_scan_result && (
                                        <span className={styles.countBadge}>
                                            {status.last_scan_result.candidates.length}
                                        </span>
                                    )
                                }
                            >
                                <div className={styles.cardBody}>
                                    {status?.last_scan_result ? (
                                        <>
                                            <div className={styles.scanStats}>
                                                <span>Processed: {status.last_scan_result.processed_count}</span>
                                                <span>Found: {status.last_scan_result.candidates.length}</span>
                                            </div>
                                            {status.last_scan_result.candidates.length > 0 ? (
                                                <div className={styles.candidateTable}>
                                                    <table>
                                                        <thead>
                                                            <tr>
                                                                <SortHeader label="Symbol" sortKey="symbol" sortConfig={engineScanSort} onSort={() => toggleSort('symbol', engineScanSort, setEngineScanSort)} />
                                                                <SortHeader label="Gap%" sortKey="gap_percent" sortConfig={engineScanSort} onSort={() => toggleSort('gap_percent', engineScanSort, setEngineScanSort)} />
                                                                <SortHeader label="RVOL" sortKey="rvol" sortConfig={engineScanSort} onSort={() => toggleSort('rvol', engineScanSort, setEngineScanSort)} />
                                                                <SortHeader label="Price" sortKey="price" sortConfig={engineScanSort} onSort={() => toggleSort('price', engineScanSort, setEngineScanSort)} />
                                                                <th>Status</th>
                                                            </tr>
                                                        </thead>
                                                        <tbody>
                                                            {sortData(status.last_scan_result.candidates, engineScanSort).map((c) => (
                                                                <tr key={c.symbol} className={c.in_watchlist ? styles.inWatchlist : ''}>
                                                                    <td className={styles.symbol}>
                                                                        <span
                                                                            className={styles.clickableSymbol}
                                                                            onClick={() => openChart(c.symbol)}
                                                                            title="Open TradingView chart"
                                                                        >
                                                                            {c.symbol}
                                                                        </span>
                                                                    </td>
                                                                    <td className={c.gap_percent >= 10 ? styles.pnlPositive : ''}>{c.gap_percent.toFixed(1)}%</td>
                                                                    <td>{c.rvol.toFixed(1)}x</td>
                                                                    <td>${c.price.toFixed(2)}</td>
                                                                    <td>{c.in_watchlist ? '👁️' : '-'}</td>
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
                                        <p className={styles.emptyMessage}>Engine hasn't scanned yet. Start the engine to begin.</p>
                                    )}
                                </div>
                            </CollapsibleCard>

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
                                                        <SortHeader label="Gap%" sortKey="gap_percent" sortConfig={watchlistSort} onSort={() => toggleSort('gap_percent', watchlistSort, setWatchlistSort)} />
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
                                                            <td className={w.gap_percent >= 10 ? styles.pnlPositive : ''}>{w.gap_percent.toFixed(1)}%</td>
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
                                                <th>High</th>
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
                                                            {event.created_at ? new Date(event.created_at).toLocaleTimeString('en-US', {
                                                                timeZone: 'America/New_York',
                                                                hour: '2-digit',
                                                                minute: '2-digit'
                                                            }) + ' ET' : '--'}
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
                )
                }
            </main >
        </>
    )
}
