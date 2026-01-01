import { useState, useEffect, useCallback } from 'react'
import Head from 'next/head'
import Link from 'next/link'
import styles from '@/styles/Automation.module.css'

interface EngineStatus {
    state: string
    sim_only: boolean
    is_market_hours: boolean
    trading_mode: string
    mode_description: string
    broker_available: boolean
    broker_type: string
    broker_display: string
    active_account: string
    settings_risk_per_trade: number
    config: {
        scanner_interval: number
        min_quality: number
        max_positions: number
        risk_per_trade: string
        daily_loss_limit: string
    }
    stats: {
        started_at: string | null
        scans_run: number
        signals_generated: number
        orders_submitted: number
        orders_filled: number
        daily_pnl: string
        last_scan_at: string | null
        last_error: string | null
    }
}

interface SchedulerStatus {
    running: boolean
    interval_minutes: number
    auto_execute: boolean
    is_market_hours: boolean
    cycles_run: number
    last_run: string | null
    last_error: string | null
}

interface MonitorStatus {
    running: boolean
    check_interval_seconds: number
    checks_run: number
    exits_triggered: number
    last_check: string | null
    last_error: string | null
}

interface ApiStats {
    status: string
    provider: string
    calls_this_minute: number
    limit_per_minute: number
    remaining: number
    usage_percent: number
}

interface Signal {
    symbol: string
    setup_type: string
    quality_score: number
    tier: string
    entry_price: string
    tactical_stop: string
    stop_percent: number
    rs_percentile: number
    shares: number
    risk_amount: string
    found_at?: string  // Timestamp when signal was found
}

interface ScanResult {
    status: string
    total_signals: number
    breakdown: { ep: number; breakout: number; htf: number }
    scanned_at: string
    signals: Signal[]
}

interface ScanRejection {
    symbol: string
    reason: string
    threshold: number
    actual_value: number
}

interface ScannerDiagnostic {
    scanner: string
    enabled: boolean
    candidates_found: number
    candidates_passed: number
    rejections: ScanRejection[]
    error: string | null
}

interface ScanDiagnostics {
    available: boolean
    message?: string
    scanned_at?: string
    duration_ms?: number
    total_signals?: number
    total_processed?: number
    ep_count?: number
    breakout_count?: number
    htf_count?: number
    diagnostics?: ScannerDiagnostic[]
}

interface BrokerPosition {
    symbol: string
    qty: number
    avg_price: number
    market_value: number
    unrealized_pnl: number
    pnl_percent: number
}

interface PositionsData {
    status: string
    positions: BrokerPosition[]
    count: number
    total_value: number
    total_pnl: number
}

interface ScannerSettings {
    preset: 'strict' | 'relaxed' | 'custom'
    minQuality: number
    stopMode: 'atr' | 'percent'  // KK uses ATR
    maxStopAtr: number           // Default: 1.0 ATR
    maxStopPercent: number       // Fallback option
    scanModes: string[]          // Which scanners to run: ep, breakout, htf
    htfFrequency: 'every_cycle' | 'market_open'  // How often to run HTF
}

const PRESET_MODES: Record<string, ScannerSettings> = {
    strict: { preset: 'strict', minQuality: 7, stopMode: 'atr', maxStopAtr: 1.0, maxStopPercent: 5, scanModes: ['ep', 'breakout'], htfFrequency: 'market_open' },
    relaxed: { preset: 'relaxed', minQuality: 5, stopMode: 'atr', maxStopAtr: 1.5, maxStopPercent: 8, scanModes: ['ep', 'breakout', 'htf'], htfFrequency: 'market_open' },
    custom: { preset: 'custom', minQuality: 6, stopMode: 'atr', maxStopAtr: 1.0, maxStopPercent: 6, scanModes: ['ep', 'breakout'], htfFrequency: 'market_open' },
}

interface SchedulerSettingsData {
    adopt_quick_actions: boolean
    preset: 'strict' | 'relaxed' | 'custom'
    min_quality: number
    stop_mode: 'atr' | 'percent'
    max_stop_atr: number
    max_stop_percent: number
    scan_modes: string[]  // ["ep", "breakout", "htf"]
    htf_frequency: 'every_cycle' | 'market_open'
}

const SCHEDULER_PRESET_DEFAULTS: Record<string, Partial<SchedulerSettingsData>> = {
    strict: { min_quality: 7, stop_mode: 'atr', max_stop_atr: 1.0, max_stop_percent: 5 },
    relaxed: { min_quality: 5, stop_mode: 'percent', max_stop_atr: 1.5, max_stop_percent: 8 },
}


export default function Automation() {
    const [engine, setEngine] = useState<EngineStatus | null>(null)
    const [scheduler, setScheduler] = useState<SchedulerStatus | null>(null)
    const [monitor, setMonitor] = useState<MonitorStatus | null>(null)
    const [loading, setLoading] = useState(true)
    const [actionLoading, setActionLoading] = useState<string | null>(null)
    const [signalStream, setSignalStream] = useState<ScanResult | null>(null)
    const [sessionSignals, setSessionSignals] = useState<Signal[]>([])  // Store session signals
    const [showSessionSignals, setShowSessionSignals] = useState(false)  // Toggle to show signals modal
    const [scannerSettings, setScannerSettings] = useState<ScannerSettings>(PRESET_MODES.strict)
    const [apiStats, setApiStats] = useState<ApiStats | null>(null)  // API rate limit stats

    // Scheduler settings (persisted separately from Quick Actions)
    const [schedulerSettings, setSchedulerSettings] = useState<SchedulerSettingsData | null>(null)
    const [showSchedulerModal, setShowSchedulerModal] = useState(false)

    // Scanner diagnostics for visibility
    const [diagnostics, setDiagnostics] = useState<ScanDiagnostics | null>(null)
    const [showDiagnostics, setShowDiagnostics] = useState(false)

    // Broker positions (actual Alpaca positions)
    const [positions, setPositions] = useState<PositionsData | null>(null)

    // Scheduler interval selector (5, 10, 15, 30 min)
    const [selectedInterval, setSelectedInterval] = useState<number>(15)

    const API_BASE = 'http://localhost:8000'


    const fetchStatus = useCallback(async () => {
        try {
            const [engineRes, schedulerRes, monitorRes, apiStatsRes, schedulerSignalsRes, diagnosticsRes, positionsRes] = await Promise.all([
                fetch(`${API_BASE}/automation/status`),
                fetch(`${API_BASE}/automation/scheduler/status`),
                fetch(`${API_BASE}/automation/monitor/status`),
                fetch(`${API_BASE}/automation/api-stats`),
                fetch(`${API_BASE}/automation/scheduler/signals`),
                fetch(`${API_BASE}/automation/scheduler/diagnostics`),
                fetch(`${API_BASE}/automation/positions`),
            ])

            if (engineRes.ok) setEngine(await engineRes.json())
            if (schedulerRes.ok) setScheduler(await schedulerRes.json())
            if (monitorRes.ok) setMonitor(await monitorRes.json())
            if (apiStatsRes.ok) setApiStats(await apiStatsRes.json())
            if (positionsRes.ok) setPositions(await positionsRes.json())

            // If scheduler has signals, REPLACE session signals (latest scan = source of truth)
            if (schedulerSignalsRes.ok) {
                const schedSigs = await schedulerSignalsRes.json()
                if (schedSigs.signals && schedSigs.signals.length > 0) {
                    // Replace strategy: latest scan replaces all previous signals
                    setSessionSignals(schedSigs.signals)
                }
            }

            // Fetch diagnostics for scanner visibility
            if (diagnosticsRes.ok) {
                setDiagnostics(await diagnosticsRes.json())
            }
        } catch (err) {
            console.error('Error fetching status:', err)
        } finally {
            setLoading(false)
        }
    }, [])

    useEffect(() => {
        fetchStatus()
        const interval = setInterval(fetchStatus, 5000) // Refresh every 5s
        return () => clearInterval(interval)
    }, [fetchStatus])

    // Fetch scheduler settings when modal opens
    useEffect(() => {
        if (showSchedulerModal && !schedulerSettings) {
            fetch(`${API_BASE}/automation/scheduler/settings`)
                .then(res => res.json())
                .then(data => setSchedulerSettings(data))
                .catch(err => console.error('Failed to fetch scheduler settings:', err))
        }
    }, [showSchedulerModal, schedulerSettings])


    const handleAction = async (action: string, endpoint: string, body?: object) => {
        setActionLoading(action)
        try {
            const res = await fetch(`${API_BASE}${endpoint}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: body ? JSON.stringify(body) : undefined,
            })
            if (res.ok) {
                const data = await res.json()
                // Capture scan results for Signal Stream display
                if (endpoint === '/automation/scan-all' && data.signals) {
                    setSignalStream(data)
                    // Append to session signals for history
                    setSessionSignals(prev => {
                        const newSignals = [...data.signals, ...prev]
                        return newSignals.slice(0, 50)  // Keep last 50
                    })
                }
                await fetchStatus()
            }
        } catch (err) {
            console.error(`Error with ${action}:`, err)
        } finally {
            setActionLoading(null)
        }
    }

    const toggleAutoExecute = async () => {
        const newValue = !scheduler?.auto_execute
        setActionLoading('toggle-auto')
        try {
            await fetch(`${API_BASE}/automation/scheduler/auto-execute`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ auto_execute: newValue }),
            })
            await fetchStatus()
        } catch (err) {
            console.error('Error toggling auto-execute:', err)
        } finally {
            setActionLoading(null)
        }
    }

    // Sync Quick Actions settings to scheduler API when adopt_quick_actions is enabled
    const updateScannerSettings = async (newSettings: ScannerSettings) => {
        setScannerSettings(newSettings)

        // If adopt_quick_actions is enabled, sync to scheduler settings
        if (schedulerSettings?.adopt_quick_actions) {
            try {
                await fetch(`${API_BASE}/automation/scheduler/settings`, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        preset: newSettings.preset,
                        min_quality: newSettings.minQuality,
                        stop_mode: newSettings.stopMode,
                        max_stop_atr: newSettings.maxStopAtr,
                        max_stop_percent: newSettings.maxStopPercent,
                        scan_modes: newSettings.scanModes.join(','),
                        htf_frequency: newSettings.htfFrequency,
                    }),
                })
                console.log('Quick Actions synced to scheduler settings')
            } catch (err) {
                console.error('Failed to sync Quick Actions to scheduler:', err)
            }
        }
    }

    const formatTime = (iso: string | null | undefined) => {
        if (!iso) return '-'
        const d = new Date(iso)
        return d.toLocaleTimeString()
    }

    return (
        <>
            <Head>
                <title>Automation | Nexus 2</title>
            </Head>

            <main className={styles.container}>
                {/* Header */}
                <header className={styles.header}>
                    <div className={styles.headerLeft}>
                        <Link href="/" className={styles.backLink}>← Dashboard</Link>
                        <h1>🤖 Automation Control</h1>
                    </div>
                    <div className={styles.headerRight}>
                        {/* Trading Mode Badge */}
                        <span
                            className={`${styles.badge} ${engine?.trading_mode === 'LIVE' ? styles.badgeLive : styles.badgeSim}`}
                            title={engine?.mode_description || ''}
                        >
                            {engine?.trading_mode === 'LIVE' ? '🔥 LIVE' : '🧪 SIM'}
                            {engine?.broker_display && ` | ${engine.broker_display}`}
                        </span>
                        <span className={`${styles.badge} ${engine?.is_market_hours ? styles.badgeGreen : styles.badgeGray}`}>
                            {engine?.is_market_hours ? '🟢 Market Open' : '🔴 Market Closed'}
                        </span>
                        <button onClick={fetchStatus} className={styles.refreshBtn}>
                            🔄 Refresh
                        </button>
                    </div>
                </header>

                {loading ? (
                    <div className={styles.loading}>Loading...</div>
                ) : (
                    <>
                        {/* Getting Started Instructions */}
                        <div className={styles.instructions}>
                            <details open>
                                <summary>📖 How to Use Automation</summary>
                                <div className={styles.instructionContent}>
                                    <div className={styles.instructionStep}>
                                        <span className={styles.stepNumber}>1</span>
                                        <div>
                                            <strong>Start Scheduler</strong> (recommended)
                                            <p>Runs scans every 15 min, auto-executes trades, monitors Day 3-5 partials, and runs EOD MA check at 3:45 PM.</p>
                                        </div>
                                    </div>
                                    <div className={styles.instructionStep}>
                                        <span className={styles.stepNumber}>2</span>
                                        <div>
                                            <strong>Or use Manual Mode</strong>
                                            <p>Start Engine + Monitor separately for more control. Use "Run Scan" to find setups manually.</p>
                                        </div>
                                    </div>
                                    <div className={styles.instructionNote}>
                                        <strong>💡 KK-Style Automation:</strong> Day 1 stop (LoD via bracket order) → Day 3-5 partial (50%) + breakeven → Day 5+ MA trailing
                                    </div>
                                </div>
                            </details>
                        </div>

                        <div className={styles.grid}>
                            {/* Scheduler Card - First (recommended approach) */}
                            <div className={styles.card}>
                                <div className={styles.cardHeader}>
                                    <h2>⏰ Scheduler</h2>
                                    <div className={styles.cardHeaderRight}>
                                        <span className={`${styles.statusBadge} ${scheduler?.running ? styles.statusRunning : styles.statusStopped}`}>
                                            {scheduler?.running ? 'RUNNING' : 'STOPPED'}
                                        </span>
                                        <button
                                            className={styles.gearBtn}
                                            onClick={() => setShowSchedulerModal(true)}
                                            title="Scheduler Settings"
                                        >
                                            ⚙️
                                        </button>
                                    </div>
                                </div>

                                <div className={styles.cardBody}>
                                    <div className={styles.stat}>
                                        <span>Interval:</span>
                                        <select
                                            value={scheduler?.running ? scheduler.interval_minutes : selectedInterval}
                                            onChange={async (e) => {
                                                const newInterval = Number(e.target.value);
                                                setSelectedInterval(newInterval);
                                                if (scheduler?.running) {
                                                    // Update running scheduler
                                                    try {
                                                        await fetch(`${API_BASE}/automation/scheduler/interval`, {
                                                            method: 'PATCH',
                                                            headers: { 'Content-Type': 'application/json' },
                                                            body: JSON.stringify({ interval_minutes: newInterval }),
                                                        });
                                                        // Refresh status to show new interval
                                                        fetchStatus();
                                                    } catch (err) {
                                                        console.error('Failed to update interval:', err);
                                                    }
                                                }
                                            }}
                                            className={styles.intervalSelect}
                                        >
                                            <option value={5}>5 min</option>
                                            <option value={10}>10 min</option>
                                            <option value={15}>15 min</option>
                                            <option value={30}>30 min</option>
                                        </select>
                                    </div>
                                    <div className={styles.stat}>
                                        <span>Auto-Execute:</span>
                                        <button
                                            onClick={toggleAutoExecute}
                                            className={`${styles.toggleBtn} ${scheduler?.auto_execute ? styles.toggleActive : ''}`}
                                            disabled={!scheduler?.running || actionLoading === 'toggle-auto'}
                                            title={scheduler?.running ? 'Click to toggle auto-execute' : 'Start scheduler first'}
                                        >
                                            {actionLoading === 'toggle-auto' ? '...' : (scheduler?.auto_execute ? '✅ ON' : '❌ OFF')}
                                        </button>
                                    </div>
                                    <div className={styles.stat}>
                                        <span>Cycles Run:</span>
                                        <strong>{scheduler?.cycles_run || 0}</strong>
                                    </div>
                                    <div className={styles.stat}>
                                        <span>Last Run:</span>
                                        <strong>{formatTime(scheduler?.last_run)}</strong>
                                    </div>
                                </div>

                                {/* Collapsible Scan Details */}
                                {diagnostics?.available && scheduler?.running && (
                                    <div className={styles.scanDetails}>
                                        <button
                                            className={styles.scanDetailsToggle}
                                            onClick={() => setShowDiagnostics(!showDiagnostics)}
                                        >
                                            {showDiagnostics ? '▼' : '▶'} Last Scan Details ({diagnostics.duration_ms}ms)
                                        </button>
                                        {showDiagnostics && (
                                            <div className={styles.scanDetailsContent}>
                                                <div className={styles.scanSummary}>
                                                    <span>📊 {diagnostics.total_processed} processed → {diagnostics.total_signals} signals</span>
                                                    <span>EP: {diagnostics.ep_count} | BO: {diagnostics.breakout_count} | HTF: {diagnostics.htf_count}</span>
                                                </div>
                                                {diagnostics.diagnostics?.map((d, i) => (
                                                    <div key={i} className={styles.scannerInfo}>
                                                        <div className={styles.scannerHeader}>
                                                            <strong>{d.scanner.toUpperCase()}</strong>
                                                            {d.enabled ? (
                                                                <span className={styles.badge}>
                                                                    {d.candidates_found} → {d.candidates_passed}
                                                                </span>
                                                            ) : (
                                                                <span className={styles.badgeDisabled}>SKIPPED</span>
                                                            )}
                                                        </div>
                                                        {d.rejections.length > 0 && (
                                                            <div className={styles.rejections}>
                                                                {d.rejections.slice(0, 3).map((r, j) => (
                                                                    <small key={j} className={styles.rejection}>
                                                                        ❌ {r.symbol}: {r.reason.replace(/_/g, ' ')}
                                                                        (needed ≤{r.threshold}, got {r.actual_value.toFixed(2)})
                                                                    </small>
                                                                ))}
                                                                {d.rejections.length > 3 && (
                                                                    <small>...and {d.rejections.length - 3} more</small>
                                                                )}
                                                            </div>
                                                        )}
                                                    </div>
                                                ))}
                                            </div>
                                        )}
                                    </div>
                                )}

                                <div className={styles.cardActions}>
                                    {scheduler?.running ? (
                                        <button
                                            onClick={() => handleAction('scheduler-stop', '/automation/scheduler/stop')}
                                            className={styles.btnDanger}
                                            disabled={actionLoading === 'scheduler-stop'}
                                        >
                                            {actionLoading === 'scheduler-stop' ? '...' : '⏹ Stop'}
                                        </button>
                                    ) : (
                                        <button
                                            onClick={() => handleAction('scheduler-start', '/automation/scheduler/start', { interval_minutes: selectedInterval })}
                                            className={styles.btnPrimary}
                                            disabled={actionLoading === 'scheduler-start'}
                                            title="Starts full automation: scans every 15 min, auto-executes trades, monitors positions for Day 3-5 partials, and runs EOD MA check at 3:45 PM"
                                        >
                                            {actionLoading === 'scheduler-start' ? '...' : '▶️ Start'}
                                        </button>
                                    )}
                                </div>
                            </div>

                            {/* Engine Card - Manual mode */}
                            <div className={styles.card}>
                                <div className={styles.cardHeader}>
                                    <h2>⚡ Engine</h2>
                                    <span className={`${styles.statusBadge} ${engine?.state === 'running' ? styles.statusRunning :
                                        engine?.state === 'paused' ? styles.statusPaused : styles.statusStopped
                                        }`}>
                                        {engine?.state?.toUpperCase() || 'UNKNOWN'}
                                    </span>
                                </div>
                                <div className={styles.cardBody}>
                                    <div className={styles.stat}>
                                        <span>Mode:</span>
                                        <strong className={engine?.sim_only ? styles.simMode : styles.liveMode}>
                                            {engine?.sim_only ? '🧪 SIM' : '🔥 LIVE'}
                                        </strong>
                                    </div>
                                    <div className={styles.stat}>
                                        <span>Risk/Trade:</span>
                                        <strong>${engine?.settings_risk_per_trade}</strong>
                                    </div>
                                    <div className={styles.stat}>
                                        <span>Max Positions:</span>
                                        <strong>{(engine as any)?.settings_max_positions ?? engine?.config?.max_positions}</strong>
                                    </div>
                                    <div className={styles.stat}>
                                        <span>Orders Filled:</span>
                                        <strong>{engine?.stats?.orders_filled || 0}</strong>
                                    </div>
                                </div>
                                <div className={styles.cardActions}>
                                    {engine?.state === 'running' ? (
                                        <button
                                            onClick={() => handleAction('engine-stop', '/automation/stop')}
                                            className={styles.btnDanger}
                                            disabled={actionLoading === 'engine-stop'}
                                        >
                                            {actionLoading === 'engine-stop' ? '...' : '⏹ Stop'}
                                        </button>
                                    ) : (
                                        <button
                                            onClick={() => handleAction('engine-start', '/automation/start', { sim_only: true })}
                                            className={styles.btnPrimary}
                                            disabled={actionLoading === 'engine-start'}
                                            title="Core automation engine. Manages order execution, position tracking, and trade lifecycle. Start manually for more control over individual scans and trades."
                                        >
                                            {actionLoading === 'engine-start' ? '...' : '▶️ Start'}
                                        </button>
                                    )}
                                </div>
                            </div>

                            {/* Monitor Card */}
                            <div className={styles.card}>
                                <div className={styles.cardHeader}>
                                    <h2>👁 Monitor</h2>
                                    <span className={`${styles.statusBadge} ${monitor?.running ? styles.statusRunning : styles.statusStopped
                                        }`}>
                                        {monitor?.running ? 'RUNNING' : 'STOPPED'}
                                    </span>
                                </div>
                                <div className={styles.cardBody}>
                                    <div className={styles.stat}>
                                        <span>Interval:</span>
                                        <strong>{monitor?.check_interval_seconds || 60}s</strong>
                                    </div>
                                    <div className={styles.stat}>
                                        <span>Checks Run:</span>
                                        <strong>{monitor?.checks_run || 0}</strong>
                                    </div>
                                    <div className={styles.stat}>
                                        <span>Exits Triggered:</span>
                                        <strong>{monitor?.exits_triggered || 0}</strong>
                                    </div>
                                    <div className={styles.stat}>
                                        <span>Last Check:</span>
                                        <strong>{formatTime(monitor?.last_check)}</strong>
                                    </div>
                                </div>
                                <div className={styles.cardActions}>
                                    {monitor?.running ? (
                                        <button
                                            onClick={() => handleAction('monitor-stop', '/automation/monitor/stop')}
                                            className={styles.btnDanger}
                                            disabled={actionLoading === 'monitor-stop'}
                                        >
                                            {actionLoading === 'monitor-stop' ? '...' : '⏹ Stop'}
                                        </button>
                                    ) : (
                                        <button
                                            onClick={() => handleAction('monitor-start', '/automation/monitor/start')}
                                            className={styles.btnPrimary}
                                            disabled={actionLoading === 'monitor-start'}
                                            title="Monitors open positions every 60 sec for stop hits, Day 3-5 partial exits (50%), and moves stops to breakeven after partials"
                                        >
                                            {actionLoading === 'monitor-start' ? '...' : '▶️ Start'}
                                        </button>
                                    )}
                                </div>
                            </div>

                            {/* API Rate Monitor */}
                            <div className={styles.card}>
                                <div className={styles.cardHeader}>
                                    <h2>📡 API Usage</h2>
                                    <span className={`${styles.statusBadge} ${(apiStats?.usage_percent || 0) > 80 ? styles.statusPaused :
                                        (apiStats?.usage_percent || 0) > 50 ? styles.statusRunning : styles.statusStopped
                                        }`}>
                                        {apiStats?.usage_percent || 0}%
                                    </span>
                                </div>
                                <div className={styles.cardBody}>
                                    <div className={styles.usageBar}>
                                        <div
                                            className={styles.usageProgress}
                                            style={{
                                                width: `${Math.min(apiStats?.usage_percent || 0, 100)}%`,
                                                background: (apiStats?.usage_percent || 0) > 80 ? '#ff6b6b' :
                                                    (apiStats?.usage_percent || 0) > 50 ? '#ffc800' : '#00ff88'
                                            }}
                                        />
                                    </div>
                                    <div className={styles.stat}>
                                        <span>Calls/min:</span>
                                        <strong>{apiStats?.calls_this_minute || 0} / {apiStats?.limit_per_minute || 300}</strong>
                                    </div>
                                    <div className={styles.stat}>
                                        <span>Remaining:</span>
                                        <strong style={{ color: (apiStats?.remaining || 300) < 50 ? '#ff6b6b' : undefined }}>
                                            {apiStats?.remaining ?? 300}
                                        </strong>
                                    </div>
                                    <div className={styles.stat}>
                                        <span>Provider:</span>
                                        <strong>{apiStats?.provider || 'FMP'}</strong>
                                    </div>
                                </div>
                            </div>

                            {/* Quick Actions */}
                            <div className={`${styles.card} ${styles.actionsCard}`}>
                                <div className={styles.cardHeader}>
                                    <h2>🎯 Quick Actions</h2>
                                </div>
                                <div className={styles.cardBody}>
                                    {/* Scanner Settings */}
                                    <div className={styles.scannerSettings}>
                                        <div className={styles.presetButtons}>
                                            <button
                                                className={`${styles.presetBtn} ${scannerSettings.preset === 'strict' ? styles.presetActive : ''}`}
                                                onClick={() => updateScannerSettings(PRESET_MODES.strict)}
                                                title="KK-style: Quality ≥7, Stop ≤5%"
                                            >
                                                🎯 Strict
                                            </button>
                                            <button
                                                className={`${styles.presetBtn} ${scannerSettings.preset === 'relaxed' ? styles.presetActive : ''}`}
                                                onClick={() => updateScannerSettings(PRESET_MODES.relaxed)}
                                                title="Relaxed: Quality ≥5, Stop ≤8%"
                                            >
                                                🔓 Relaxed
                                            </button>
                                            <button
                                                className={`${styles.presetBtn} ${scannerSettings.preset === 'custom' ? styles.presetActive : ''}`}
                                                onClick={() => updateScannerSettings({ ...scannerSettings, preset: 'custom' })}
                                                title="Custom settings"
                                            >
                                                ⚙️ Custom
                                            </button>
                                        </div>
                                        {scannerSettings.preset === 'custom' && (
                                            <div className={styles.customSettings}>
                                                <div className={styles.settingRow}>
                                                    <label>Min Quality: {scannerSettings.minQuality}</label>
                                                    <input
                                                        type="range"
                                                        min="1"
                                                        max="10"
                                                        value={scannerSettings.minQuality}
                                                        onChange={(e) => updateScannerSettings({
                                                            ...scannerSettings,
                                                            minQuality: parseInt(e.target.value)
                                                        })}
                                                    />
                                                </div>
                                                <div className={styles.settingRow}>
                                                    <label>Stop Filter:</label>
                                                    <div className={styles.toggleButtons}>
                                                        <button
                                                            className={`${styles.toggleBtn} ${scannerSettings.stopMode === 'atr' ? styles.toggleActive : ''}`}
                                                            onClick={() => updateScannerSettings({ ...scannerSettings, stopMode: 'atr' })}
                                                            title="KK-style: Stop distance in ATR units"
                                                        >
                                                            ATR
                                                        </button>
                                                        <button
                                                            className={`${styles.toggleBtn} ${scannerSettings.stopMode === 'percent' ? styles.toggleActive : ''}`}
                                                            onClick={() => updateScannerSettings({ ...scannerSettings, stopMode: 'percent' })}
                                                            title="Simple percentage-based stop filter"
                                                        >
                                                            %
                                                        </button>
                                                    </div>
                                                </div>
                                                {scannerSettings.stopMode === 'atr' ? (
                                                    <div className={styles.settingRow}>
                                                        <label>Max Stop: {scannerSettings.maxStopAtr} ATR</label>
                                                        <input
                                                            type="range"
                                                            min="0.5"
                                                            max="3"
                                                            step="0.1"
                                                            value={scannerSettings.maxStopAtr}
                                                            onChange={(e) => updateScannerSettings({
                                                                ...scannerSettings,
                                                                maxStopAtr: parseFloat(e.target.value)
                                                            })}
                                                        />
                                                    </div>
                                                ) : (
                                                    <div className={styles.settingRow}>
                                                        <label>Max Stop: {scannerSettings.maxStopPercent}%</label>
                                                        <input
                                                            type="range"
                                                            min="1"
                                                            max="15"
                                                            value={scannerSettings.maxStopPercent}
                                                            onChange={(e) => updateScannerSettings({
                                                                ...scannerSettings,
                                                                maxStopPercent: parseInt(e.target.value)
                                                            })}
                                                        />
                                                    </div>
                                                )}
                                            </div>
                                        )}
                                        <div className={styles.currentSettings}>
                                            Quality ≥{scannerSettings.minQuality} • Stop ≤{scannerSettings.stopMode === 'atr'
                                                ? `${scannerSettings.maxStopAtr} ATR`
                                                : `${scannerSettings.maxStopPercent}%`}
                                        </div>

                                        {/* Scanner Mode Selection */}
                                        <div style={{ marginTop: '12px', padding: '10px', backgroundColor: 'rgba(255,255,255,0.03)', borderRadius: '6px' }}>
                                            <div style={{ display: 'flex', alignItems: 'center', gap: '16px', flexWrap: 'wrap' }}>
                                                <span style={{ fontSize: '12px', color: '#9ca3af' }}>Scanners:</span>
                                                <span style={{ fontSize: '12px', color: '#22c55e' }}>✓ EP</span>
                                                <span style={{ fontSize: '12px', color: '#22c55e' }}>✓ Breakout</span>
                                                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                                                    <span style={{ fontSize: '12px', color: '#9ca3af' }}>HTF:</span>
                                                    <select
                                                        value={scannerSettings.scanModes?.includes('htf')
                                                            ? (scannerSettings.htfFrequency || 'market_open')
                                                            : 'off'}
                                                        onChange={(e) => {
                                                            const val = e.target.value
                                                            if (val === 'off') {
                                                                // Remove HTF from modes
                                                                const newModes = (scannerSettings.scanModes || ['ep', 'breakout']).filter(m => m !== 'htf')
                                                                updateScannerSettings({ ...scannerSettings, scanModes: newModes, preset: 'custom' })
                                                            } else {
                                                                // Add HTF and set frequency
                                                                const currentModes = scannerSettings.scanModes || ['ep', 'breakout']
                                                                const newModes = currentModes.includes('htf') ? currentModes : [...currentModes, 'htf']
                                                                updateScannerSettings({
                                                                    ...scannerSettings,
                                                                    scanModes: newModes,
                                                                    htfFrequency: val as 'every_cycle' | 'market_open',
                                                                    preset: 'custom'
                                                                })
                                                            }
                                                        }}
                                                        style={{ padding: '4px 8px', fontSize: '12px', borderRadius: '4px', backgroundColor: '#1f2937', border: '1px solid #374151', color: '#fff' }}
                                                    >
                                                        <option value="off">Off</option>
                                                        <option value="market_open">Once/day (9am)</option>
                                                        <option value="every_cycle">Every cycle</option>
                                                    </select>
                                                </div>
                                            </div>
                                        </div>
                                    </div>

                                    <div className={styles.actionButtons}>
                                        <button
                                            onClick={() => handleAction('scan', '/automation/scan-all', {
                                                min_quality: scannerSettings.minQuality,
                                                stop_mode: scannerSettings.stopMode,
                                                max_stop_atr: scannerSettings.maxStopAtr,
                                                max_stop_percent: scannerSettings.maxStopPercent
                                            })}
                                            className={styles.btnSecondary}
                                            disabled={actionLoading === 'scan'}
                                            title={`Run EP, Breakout, and HTF scanners with current settings (Quality ≥${scannerSettings.minQuality}, Stop ≤${scannerSettings.maxStopPercent}%)`}
                                        >
                                            {actionLoading === 'scan' ? '...' : '🔍 Run Scan (All)'}
                                        </button>
                                        <button
                                            onClick={() => handleAction('dry-run', '/automation/scan_and_execute')}
                                            className={styles.btnSecondary}
                                            disabled={actionLoading === 'dry-run'}
                                            title="[Not implemented yet] Will scan for signals AND simulate execution to show what trades would be placed without actually executing."
                                        >
                                            {actionLoading === 'dry-run' ? '...' : '🧪 Dry Run'}
                                        </button>
                                        <button
                                            onClick={() => handleAction('check', '/automation/monitor/check')}
                                            className={styles.btnSecondary}
                                            disabled={actionLoading === 'check'}
                                            title="Check all open positions against their stops. Triggers exits if stop prices are breached."
                                        >
                                            {actionLoading === 'check' ? '...' : '🔎 Check Positions'}
                                        </button>
                                    </div>
                                </div>
                            </div>

                            {/* Signal Stream - Proposed Trade Candidates */}
                            {signalStream && (
                                <div className={`${styles.card} ${styles.signalCard}`}>
                                    <div className={styles.cardHeader}>
                                        <h2>📡 Signal Stream</h2>
                                        <span className={styles.scanTime}>
                                            {new Date(signalStream.scanned_at).toLocaleTimeString()}
                                        </span>
                                    </div>
                                    <div className={styles.signalBreakdown}>
                                        <span className={styles.breakdownItem}>EP: {signalStream.breakdown.ep}</span>
                                        <span className={styles.breakdownItem}>Breakout: {signalStream.breakdown.breakout}</span>
                                        <span className={styles.breakdownItem}>HTF: {signalStream.breakdown.htf}</span>
                                        <span className={styles.breakdownItem}>Total: {signalStream.total_signals}</span>
                                    </div>
                                    {signalStream.signals.length > 0 ? (
                                        <>
                                            <div className={styles.signalTable}>
                                                <table>
                                                    <thead>
                                                        <tr>
                                                            <th>Symbol</th>
                                                            <th>Type</th>
                                                            <th>Quality</th>
                                                            <th>Tier</th>
                                                            <th>Entry</th>
                                                            <th>Stop</th>
                                                            <th>Stop%</th>
                                                            <th>Shares</th>
                                                            <th>Risk</th>
                                                        </tr>
                                                    </thead>
                                                    <tbody>
                                                        {signalStream.signals.map((sig) => (
                                                            <tr key={sig.symbol} className={sig.tier === 'FOCUS' ? styles.focusTier : ''}>
                                                                <td className={styles.symbol}>{sig.symbol}</td>
                                                                <td>{sig.setup_type.toUpperCase()}</td>
                                                                <td>{sig.quality_score}/10</td>
                                                                <td className={sig.tier === 'FOCUS' ? styles.tierFocus : styles.tierWide}>
                                                                    {sig.tier}
                                                                </td>
                                                                <td>${parseFloat(sig.entry_price).toFixed(2)}</td>
                                                                <td>${parseFloat(sig.tactical_stop).toFixed(2)}</td>
                                                                <td className={styles.stopPct}>{sig.stop_percent.toFixed(1)}%</td>
                                                                <td>{sig.shares}</td>
                                                                <td>${sig.risk_amount}</td>
                                                            </tr>
                                                        ))}
                                                    </tbody>
                                                </table>
                                            </div>
                                            <div className={styles.signalHint}>
                                                ⚡ These are proposed trades based on current scan. Click "Dry Run" to preview execution.
                                            </div>
                                        </>
                                    ) : (
                                        <div className={styles.emptySignals}>
                                            <p>No qualifying signals found</p>
                                            <span className={styles.emptyHint}>
                                                Filters: Quality ≥7, Stop ≤5%. Try during market hours for live data.
                                            </span>
                                        </div>
                                    )}
                                </div>
                            )}

                            {/* Open Positions Card (Alpaca) */}
                            <div className={styles.card}>
                                <div className={styles.cardHeader}>
                                    <h2>📊 Open Positions</h2>
                                    {positions?.count ? (
                                        <span className={`${styles.badge}`} style={{ backgroundColor: positions.total_pnl >= 0 ? '#22c55e' : '#ef4444' }}>
                                            {positions.count} positions • {positions.total_pnl >= 0 ? '+' : ''}${positions.total_pnl.toFixed(2)}
                                        </span>
                                    ) : null}
                                </div>
                                <div className={styles.cardBody}>
                                    {positions?.positions && positions.positions.length > 0 ? (
                                        <div style={{ overflowX: 'auto', width: '100%' }}>
                                            <table className={styles.signalTable}>
                                                <thead>
                                                    <tr>
                                                        <th>Symbol</th>
                                                        <th>Qty</th>
                                                        <th>Avg</th>
                                                        <th>Value</th>
                                                        <th>P/L$</th>
                                                        <th>P/L%</th>
                                                    </tr>
                                                </thead>
                                                <tbody>
                                                    {positions.positions.map((pos) => (
                                                        <tr key={pos.symbol}>
                                                            <td className={styles.symbol}>{pos.symbol}</td>
                                                            <td>{pos.qty}</td>
                                                            <td>${pos.avg_price.toFixed(2)}</td>
                                                            <td>${pos.market_value.toFixed(0)}</td>
                                                            <td style={{ color: pos.unrealized_pnl >= 0 ? '#22c55e' : '#ef4444' }}>
                                                                {pos.unrealized_pnl >= 0 ? '+' : ''}${pos.unrealized_pnl.toFixed(2)}
                                                            </td>
                                                            <td style={{ color: pos.pnl_percent >= 0 ? '#22c55e' : '#ef4444' }}>
                                                                {pos.pnl_percent >= 0 ? '+' : ''}{pos.pnl_percent.toFixed(1)}%
                                                            </td>
                                                        </tr>
                                                    ))}
                                                </tbody>
                                            </table>
                                            <div className={styles.positionsSummary} style={{ marginTop: '12px', padding: '8px 12px', backgroundColor: 'rgba(255,255,255,0.03)', borderRadius: '6px', display: 'flex', justifyContent: 'space-between' }}>
                                                <span style={{ color: '#9ca3af' }}>Total Value: <strong>${positions.total_value.toFixed(0)}</strong></span>
                                                <span style={{ color: positions.total_pnl >= 0 ? '#22c55e' : '#ef4444' }}>
                                                    Total P&L: <strong>{positions.total_pnl >= 0 ? '+' : ''}${positions.total_pnl.toFixed(2)}</strong>
                                                </span>
                                            </div>
                                        </div>
                                    ) : (
                                        <div className={styles.emptySignals}>
                                            <p>No open positions</p>
                                            <span className={styles.emptyHint}>
                                                Positions opened via automation will appear here.
                                            </span>
                                        </div>
                                    )}
                                </div>
                            </div>

                            {/* Kill Switch */}
                            <div className={`${styles.card} ${styles.killCard}`}>
                                <div className={styles.cardHeader}>
                                    <h2>🛑 Emergency</h2>
                                </div>
                                <div className={styles.cardBody}>
                                    <button
                                        onClick={async () => {
                                            setActionLoading('kill')
                                            await handleAction('kill-engine', '/automation/stop')
                                            await handleAction('kill-scheduler', '/automation/scheduler/stop')
                                            await handleAction('kill-monitor', '/automation/monitor/stop')
                                            setActionLoading(null)
                                        }}
                                        className={styles.btnKill}
                                        disabled={actionLoading === 'kill'}
                                    >
                                        {actionLoading === 'kill' ? 'Stopping...' : '⛔ STOP ALL'}
                                    </button>
                                </div>
                            </div>

                            {/* Stats Summary - Clickable Signals */}
                            <div className={`${styles.card} ${styles.statsCard}`}>
                                <div className={styles.cardHeader}>
                                    <h2>📊 Session Stats</h2>
                                </div>
                                <div className={styles.statsGrid}>
                                    <div className={styles.statBox}>
                                        <div className={styles.statValue}>{engine?.stats?.scans_run || 0}</div>
                                        <div className={styles.statLabel}>Scans</div>
                                    </div>
                                    <div
                                        className={`${styles.statBox} ${sessionSignals.length > 0 ? styles.clickable : ''}`}
                                        onClick={() => sessionSignals.length > 0 && setShowSessionSignals(!showSessionSignals)}
                                        title={sessionSignals.length > 0 ? 'Click to view signals' : 'No signals yet'}
                                        style={{ cursor: sessionSignals.length > 0 ? 'pointer' : 'default' }}
                                    >
                                        <div className={styles.statValue}>{engine?.stats?.signals_generated || 0}</div>
                                        <div className={styles.statLabel}>Signals {sessionSignals.length > 0 && '🔍'}</div>
                                    </div>
                                    <div className={styles.statBox}>
                                        <div className={styles.statValue}>{engine?.stats?.orders_submitted || 0}</div>
                                        <div className={styles.statLabel}>Orders</div>
                                    </div>
                                    <div className={styles.statBox}>
                                        <div className={styles.statValue}>{engine?.stats?.orders_filled || 0}</div>
                                        <div className={styles.statLabel}>Fills</div>
                                    </div>
                                </div>
                                {/* Expandable Signal History */}
                                {showSessionSignals && sessionSignals.length > 0 && (
                                    <div className={styles.signalHistory}>
                                        <h4>Recent Signals ({sessionSignals.length})</h4>
                                        <table>
                                            <thead>
                                                <tr>
                                                    <th>Symbol</th>
                                                    <th>Type</th>
                                                    <th>Quality</th>
                                                    <th>Entry</th>
                                                    <th>Stop</th>
                                                    <th>Found</th>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {sessionSignals.slice(0, 10).map((sig, i) => (
                                                    <tr key={`${sig.symbol}-${i}`}>
                                                        <td className={styles.symbol}>{sig.symbol}</td>
                                                        <td>{sig.setup_type.toUpperCase()}</td>
                                                        <td>{sig.quality_score}/10</td>
                                                        <td>${parseFloat(sig.entry_price).toFixed(2)}</td>
                                                        <td>${parseFloat(sig.tactical_stop).toFixed(2)}</td>
                                                        <td className={styles.timestamp}>
                                                            {sig.found_at ? new Date(sig.found_at).toLocaleTimeString() : '-'}
                                                        </td>
                                                    </tr>
                                                ))}
                                            </tbody>
                                        </table>
                                    </div>
                                )}
                            </div>

                            {/* Errors Section */}
                            {(engine?.stats?.last_error || scheduler?.last_error || monitor?.last_error) && (
                                <div className={styles.errors}>
                                    <h3>⚠️ Recent Errors</h3>
                                    {engine?.stats?.last_error && <p>Engine: {engine.stats.last_error}</p>}
                                    {scheduler?.last_error && <p>Scheduler: {scheduler.last_error}</p>}
                                    {monitor?.last_error && <p>Monitor: {monitor.last_error}</p>}
                                </div>
                            )}
                        </div>
                    </>
                )}
            </main>

            {/* Scheduler Settings Modal */}
            {showSchedulerModal && (
                <div className={styles.modalOverlay} onClick={() => setShowSchedulerModal(false)}>
                    <div className={styles.modal} onClick={e => e.stopPropagation()}>
                        <div className={styles.modalHeader}>
                            <h2>⚙️ Scheduler Settings</h2>
                            <button className={styles.closeBtn} onClick={() => setShowSchedulerModal(false)}>×</button>
                        </div>
                        <div className={styles.modalBody}>
                            {/* Use Quick Actions Toggle */}
                            <div className={styles.settingGroup}>
                                <label className={styles.toggleLabel}>
                                    <span>Use Quick Actions Settings</span>
                                    <button
                                        className={`${styles.toggleBtn} ${schedulerSettings?.adopt_quick_actions ? styles.toggleActive : ''}`}
                                        onClick={async () => {
                                            const newValue = !schedulerSettings?.adopt_quick_actions
                                            try {
                                                const res = await fetch(`${API_BASE}/automation/scheduler/settings`, {
                                                    method: 'PATCH',
                                                    headers: { 'Content-Type': 'application/json' },
                                                    body: JSON.stringify({ adopt_quick_actions: newValue })
                                                })
                                                if (res.ok) {
                                                    const data = await res.json()
                                                    setSchedulerSettings(data)
                                                }
                                            } catch (err) {
                                                console.error('Failed to update scheduler settings:', err)
                                            }
                                        }}
                                    >
                                        {schedulerSettings?.adopt_quick_actions ? '✅ ON' : '❌ OFF'}
                                    </button>
                                </label>
                                <p className={styles.settingHint}>
                                    When ON, scheduler uses the same settings as Quick Actions panel.
                                </p>
                            </div>

                            {/* Custom Settings (shown when not adopting Quick Actions) */}
                            {!schedulerSettings?.adopt_quick_actions && (
                                <>
                                    {/* Preset Buttons */}
                                    <div className={styles.settingGroup}>
                                        <label>Quality Preset</label>
                                        <div className={styles.presetBtns}>
                                            {['strict', 'relaxed', 'custom'].map(preset => (
                                                <button
                                                    key={preset}
                                                    className={`${styles.presetBtn} ${schedulerSettings?.preset === preset ? styles.presetActive : ''}`}
                                                    onClick={async () => {
                                                        try {
                                                            const res = await fetch(`${API_BASE}/automation/scheduler/settings`, {
                                                                method: 'PATCH',
                                                                headers: { 'Content-Type': 'application/json' },
                                                                body: JSON.stringify({ preset })
                                                            })
                                                            if (res.ok) {
                                                                const data = await res.json()
                                                                setSchedulerSettings(data)
                                                            }
                                                        } catch (err) {
                                                            console.error('Failed to update preset:', err)
                                                        }
                                                    }}
                                                >
                                                    {preset.charAt(0).toUpperCase() + preset.slice(1)}
                                                </button>
                                            ))}
                                        </div>
                                    </div>

                                    {/* Custom Settings (only shown when preset is 'custom') */}
                                    {schedulerSettings?.preset === 'custom' && (
                                        <>
                                            {/* Min Quality Slider */}
                                            <div className={styles.settingGroup}>
                                                <label>Min Quality: {schedulerSettings?.min_quality}</label>
                                                <input
                                                    type="range"
                                                    min="1"
                                                    max="10"
                                                    value={schedulerSettings?.min_quality || 7}
                                                    onChange={async (e) => {
                                                        const min_quality = parseInt(e.target.value)
                                                        try {
                                                            const res = await fetch(`${API_BASE}/automation/scheduler/settings`, {
                                                                method: 'PATCH',
                                                                headers: { 'Content-Type': 'application/json' },
                                                                body: JSON.stringify({ min_quality })
                                                            })
                                                            if (res.ok) {
                                                                const data = await res.json()
                                                                setSchedulerSettings(data)
                                                            }
                                                        } catch (err) {
                                                            console.error('Failed to update min_quality:', err)
                                                        }
                                                    }}
                                                />
                                            </div>

                                            {/* Stop Mode */}
                                            <div className={styles.settingGroup}>
                                                <label>Stop Mode</label>
                                                <div className={styles.presetBtns}>
                                                    {['atr', 'percent'].map(mode => (
                                                        <button
                                                            key={mode}
                                                            className={`${styles.presetBtn} ${schedulerSettings?.stop_mode === mode ? styles.presetActive : ''}`}
                                                            onClick={async () => {
                                                                try {
                                                                    const res = await fetch(`${API_BASE}/automation/scheduler/settings`, {
                                                                        method: 'PATCH',
                                                                        headers: { 'Content-Type': 'application/json' },
                                                                        body: JSON.stringify({ stop_mode: mode })
                                                                    })
                                                                    if (res.ok) {
                                                                        const data = await res.json()
                                                                        setSchedulerSettings(data)
                                                                    }
                                                                } catch (err) {
                                                                    console.error('Failed to update stop_mode:', err)
                                                                }
                                                            }}
                                                        >
                                                            {mode.toUpperCase()}
                                                        </button>
                                                    ))}
                                                </div>
                                            </div>
                                        </>
                                    )}

                                    {/* Scanner Selection */}
                                    <div className={styles.settingGroup}>
                                        <label>Scanners</label>
                                        <div className={styles.checkboxGroup}>
                                            {['ep', 'breakout', 'htf'].map(scanner => (
                                                <label key={scanner} className={styles.checkboxLabel}>
                                                    <input
                                                        type="checkbox"
                                                        checked={schedulerSettings?.scan_modes?.includes(scanner) ?? true}
                                                        onChange={async (e) => {
                                                            const currentModes = schedulerSettings?.scan_modes || ['ep', 'breakout', 'htf']
                                                            const newModes = e.target.checked
                                                                ? [...currentModes, scanner]
                                                                : currentModes.filter(m => m !== scanner)
                                                            try {
                                                                const res = await fetch(`${API_BASE}/automation/scheduler/settings`, {
                                                                    method: 'PATCH',
                                                                    headers: { 'Content-Type': 'application/json' },
                                                                    body: JSON.stringify({ scan_modes: newModes })
                                                                })
                                                                if (res.ok) {
                                                                    const data = await res.json()
                                                                    setSchedulerSettings(data)
                                                                }
                                                            } catch (err) {
                                                                console.error('Failed to update scan_modes:', err)
                                                            }
                                                        }}
                                                    />
                                                    {scanner.toUpperCase()}
                                                </label>
                                            ))}
                                        </div>
                                    </div>

                                    {/* HTF Frequency */}
                                    <div className={styles.settingGroup}>
                                        <label>HTF Scan Frequency</label>
                                        <div className={styles.presetBtns}>
                                            <button
                                                className={`${styles.presetBtn} ${schedulerSettings?.htf_frequency === 'every_cycle' ? styles.presetActive : ''}`}
                                                onClick={async () => {
                                                    try {
                                                        const res = await fetch(`${API_BASE}/automation/scheduler/settings`, {
                                                            method: 'PATCH',
                                                            headers: { 'Content-Type': 'application/json' },
                                                            body: JSON.stringify({ htf_frequency: 'every_cycle' })
                                                        })
                                                        if (res.ok) {
                                                            const data = await res.json()
                                                            setSchedulerSettings(data)
                                                        }
                                                    } catch (err) {
                                                        console.error('Failed to update htf_frequency:', err)
                                                    }
                                                }}
                                            >
                                                Every Cycle
                                            </button>
                                            <button
                                                className={`${styles.presetBtn} ${schedulerSettings?.htf_frequency === 'market_open' ? styles.presetActive : ''}`}
                                                onClick={async () => {
                                                    try {
                                                        const res = await fetch(`${API_BASE}/automation/scheduler/settings`, {
                                                            method: 'PATCH',
                                                            headers: { 'Content-Type': 'application/json' },
                                                            body: JSON.stringify({ htf_frequency: 'market_open' })
                                                        })
                                                        if (res.ok) {
                                                            const data = await res.json()
                                                            setSchedulerSettings(data)
                                                        }
                                                    } catch (err) {
                                                        console.error('Failed to update htf_frequency:', err)
                                                    }
                                                }}
                                            >
                                                Market Open Only
                                            </button>
                                        </div>
                                        <p className={styles.settingHint}>
                                            HTF patterns form slowly - running once at market open saves API calls.
                                        </p>
                                    </div>
                                </>
                            )}
                        </div>
                        <div className={styles.modalFooter}>
                            <button className={styles.btnPrimary} onClick={() => setShowSchedulerModal(false)}>
                                Done
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </>
    )
}

