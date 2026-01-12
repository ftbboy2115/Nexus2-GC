import { useState, useEffect, useCallback } from 'react'
import Head from 'next/head'
import Link from 'next/link'
import styles from '@/styles/Automation.module.css'
import ColumnEditor from '@/components/ColumnEditor'
import { SchedulerCard, EngineCard, MonitorCard, ApiUsageCard } from '@/components/automation'
import { useColumnConfig, AUTOMATION_COLUMNS, AUTOMATION_EXPANDED_COLUMNS } from '@/hooks/useColumnConfig'
import {
    EngineStatus,
    SchedulerStatus,
    MonitorStatus,
    ApiStats,
    Signal,
    ScanResult,
    ScanDiagnostics,
    BrokerPosition,
    PositionsData,
    SimPosition,
    SimPositionsData,
    ScannerSettings,
    SchedulerSettingsData,
    PRESET_MODES,
    SCHEDULER_PRESET_DEFAULTS,
} from '@/types/automation'


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

    // Scanner diagnostics for visibility (persisted in localStorage, collapsed by default)
    const [diagnostics, setDiagnostics] = useState<ScanDiagnostics | null>(null)
    const [showDiagnostics, setShowDiagnostics] = useState(() => {
        if (typeof window !== 'undefined') {
            return localStorage.getItem('nexus_showDiagnostics') === 'true'
        }
        return false
    })

    // How to Use section collapse state (persisted, collapsed by default)
    const [showHowToUse, setShowHowToUse] = useState(() => {
        if (typeof window !== 'undefined') {
            return localStorage.getItem('nexus_showHowToUse') === 'true'
        }
        return false
    })

    // Broker positions (actual Alpaca positions)
    const [positions, setPositions] = useState<PositionsData | null>(null)

    // Position table sort state
    const [positionSort, setPositionSort] = useState<{ column: string; direction: 'asc' | 'desc' }>({ column: 'unrealized_pnl', direction: 'desc' })

    // Simulation positions (from MockBroker)
    const [simPositions, setSimPositions] = useState<SimPositionsData | null>(null)

    // Scheduler interval selector (5, 10, 15, 30 min)
    const [selectedInterval, setSelectedInterval] = useState<number>(15)

    // Liquidate All modal state
    const [showLiquidateModal, setShowLiquidateModal] = useState(false)
    const [liquidateConfirm, setLiquidateConfirm] = useState('')
    const [liquidateResult, setLiquidateResult] = useState<{ status: string; message: string; closed?: number } | null>(null)

    // Column configuration for Open Positions table
    const columnConfig = useColumnConfig('automation_positions', AUTOMATION_COLUMNS)
    const [showColumnEditor, setShowColumnEditor] = useState(false)
    const [positionsMaximized, setPositionsMaximized] = useState(false)

    // Trade events log
    const [tradeEvents, setTradeEvents] = useState<any[]>([])
    const [showTradeEvents, setShowTradeEvents] = useState(() => {
        if (typeof window !== 'undefined') {
            return localStorage.getItem('nexus_showTradeEvents') === 'true'
        }
        return false
    })

    // Countdown timer state
    const [countdown, setCountdown] = useState<string>('')

    // Update countdown every second when scheduler is running
    useEffect(() => {
        if (!scheduler?.running || !scheduler?.next_run) {
            setCountdown('')
            return
        }

        const updateCountdown = () => {
            // If market is closed (backend checks holidays, weekends, hours)
            if (!scheduler.is_market_hours) {
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
            const nextRun = new Date(scheduler.next_run!)
            const now = new Date()
            const diffMs = nextRun.getTime() - now.getTime()

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
    }, [scheduler?.running, scheduler?.next_run, scheduler?.is_market_hours])

    // Persist collapse states to localStorage
    useEffect(() => {
        localStorage.setItem('nexus_showDiagnostics', String(showDiagnostics))
    }, [showDiagnostics])

    useEffect(() => {
        localStorage.setItem('nexus_showHowToUse', String(showHowToUse))
    }, [showHowToUse])

    useEffect(() => {
        localStorage.setItem('nexus_showTradeEvents', String(showTradeEvents))
    }, [showTradeEvents])

    // Use relative URLs - Next.js rewrites proxy to backend
    const API_BASE = ''


    const fetchStatus = useCallback(async () => {
        try {
            const [engineRes, schedulerRes, monitorRes, apiStatsRes, schedulerSignalsRes, diagnosticsRes, positionsRes, simPosRes, settingsRes] = await Promise.all([
                fetch(`${API_BASE}/automation/status`),
                fetch(`${API_BASE}/automation/scheduler/status`),
                fetch(`${API_BASE}/automation/monitor/status`),
                fetch(`${API_BASE}/automation/api-stats`),
                fetch(`${API_BASE}/automation/scheduler/signals`),
                fetch(`${API_BASE}/automation/scheduler/diagnostics`),
                fetch(`${API_BASE}/automation/positions`),
                fetch(`${API_BASE}/automation/simulation/positions`),  // Sim positions
                fetch(`${API_BASE}/automation/scheduler/settings`),    // Scheduler settings (for sim_mode)
            ])

            if (engineRes.ok) setEngine(await engineRes.json())
            if (schedulerRes.ok) setScheduler(await schedulerRes.json())
            if (monitorRes.ok) setMonitor(await monitorRes.json())
            if (apiStatsRes.ok) setApiStats(await apiStatsRes.json())
            if (positionsRes.ok) setPositions(await positionsRes.json())
            if (simPosRes.ok) setSimPositions(await simPosRes.json())  // Sim positions
            if (settingsRes.ok) setSchedulerSettings(await settingsRes.json())  // Scheduler settings

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

            // Fetch recent trade events (both NAC and Warrior)
            try {
                const eventsRes = await fetch(`${API_BASE}/trade-events/recent?limit=30`)
                if (eventsRes.ok) {
                    const eventsData = await eventsRes.json()
                    setTradeEvents(eventsData.events || [])
                }
            } catch (err) {
                console.error('Error fetching trade events:', err)
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

    // Handle Liquidate All with confirmation
    const handleLiquidateAll = async () => {
        if (liquidateConfirm.toLowerCase() !== 'yes') {
            setLiquidateResult({ status: 'error', message: 'Type "yes" to confirm' })
            return
        }

        setActionLoading('liquidate')
        try {
            const res = await fetch(`${API_BASE}/automation/liquidate-all?confirm=yes`, {
                method: 'POST',
            })
            const data = await res.json()
            setLiquidateResult(data)
            if (data.status === 'ok' || data.status === 'partial') {
                await fetchStatus()
            }
        } catch (err) {
            setLiquidateResult({ status: 'error', message: 'Failed to liquidate' })
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

    // Export positions to CSV
    const exportPositionsToCsv = () => {
        if (!positions?.positions || positions.positions.length === 0) return

        const headers = ['Symbol', 'Qty', 'Avg Price', 'Current Price', 'Market Value', 'Unrealized P/L', 'P/L %', 'Days Held', 'Stop Price']
        const rows = positions.positions.map(p => [
            p.symbol,
            p.qty,
            p.avg_price.toFixed(2),
            (p.current_price || p.avg_price).toFixed(2),
            p.market_value.toFixed(2),
            p.unrealized_pnl.toFixed(2),
            p.pnl_percent.toFixed(2),
            p.days_held || 0,
            p.stop_price?.toFixed(2) || ''
        ])

        const csv = [headers.join(','), ...rows.map(r => r.join(','))].join('\n')
        const blob = new Blob([csv], { type: 'text/csv' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `open_positions_${new Date().toISOString().split('T')[0]}.csv`
        a.click()
        URL.revokeObjectURL(url)
    }

    const formatTime = (iso: string | null | undefined) => {
        if (!iso) return '-'
        const d = new Date(iso)
        // Format as Eastern Time with ET label
        return d.toLocaleTimeString('en-US', {
            timeZone: 'America/New_York',
            hour: 'numeric',
            minute: '2-digit',
            second: '2-digit',
            hour12: true
        }) + ' ET'
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
                        <Link href="/simulation" className={styles.backLink}>🧪 Sim</Link>
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
                            <div className={styles.scanDetails}>
                                <button
                                    className={styles.scanDetailsToggle}
                                    onClick={() => setShowHowToUse(!showHowToUse)}
                                >
                                    {showHowToUse ? '▼' : '▶'} 📖 How to Use Automation
                                </button>
                                {showHowToUse && (
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
                                        <div className={styles.instructionNote} style={{ marginTop: '8px', color: '#9ca3af' }}>
                                            <strong>🌙 Auto-Shutdown:</strong> Scheduler stops automatically at 4:02 PM ET with Discord notification. Restarts automatically next market open if Auto-Start is enabled.
                                        </div>
                                    </div>
                                )}
                            </div>
                        </div>

                        <div className={styles.grid}>
                            {/* Scheduler Card */}
                            <SchedulerCard
                                scheduler={scheduler}
                                schedulerSettings={schedulerSettings}
                                engine={engine}
                                diagnostics={diagnostics}
                                sessionSignals={sessionSignals}
                                selectedInterval={selectedInterval}
                                countdown={countdown}
                                actionLoading={actionLoading}
                                showDiagnostics={showDiagnostics}
                                onIntervalChange={setSelectedInterval}
                                onToggleAutoExecute={toggleAutoExecute}
                                onStart={() => handleAction('scheduler-start', '/automation/scheduler/start', { interval_minutes: selectedInterval })}
                                onStop={() => handleAction('scheduler-stop', '/automation/scheduler/stop')}
                                onOpenSettings={() => setShowSchedulerModal(true)}
                                onToggleDiagnostics={() => setShowDiagnostics(!showDiagnostics)}
                                onRefreshStatus={fetchStatus}
                                formatTime={formatTime}
                            />

                            {/* Engine Card */}
                            <EngineCard
                                engine={engine}
                                actionLoading={actionLoading}
                                onStart={() => handleAction('engine-start', '/automation/start', { sim_only: true })}
                                onStop={() => handleAction('engine-stop', '/automation/stop')}
                            />

                            {/* Monitor Card */}
                            <MonitorCard
                                monitor={monitor}
                                actionLoading={actionLoading}
                                onStart={() => handleAction('monitor-start', '/automation/monitor/start')}
                                onStop={() => handleAction('monitor-stop', '/automation/monitor/stop')}
                                formatTime={formatTime}
                            />

                            {/* API Usage Card */}
                            <ApiUsageCard apiStats={apiStats} />

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
                                        <button
                                            onClick={() => setShowLiquidateModal(true)}
                                            className={styles.btnDanger}
                                            disabled={actionLoading === 'liquidate'}
                                            title="Sell all open positions with market orders. Requires confirmation."
                                        >
                                            {actionLoading === 'liquidate' ? '...' : '💥 Liquidate All'}
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

                            {/* Open Positions Card (Sim or Live based on mode) */}
                            {positionsMaximized && (
                                <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, zIndex: 99, backgroundColor: 'rgba(0, 0, 0, 0.8)', backdropFilter: 'blur(4px)' }} onClick={() => setPositionsMaximized(false)} />
                            )}
                            <div className={styles.card} style={positionsMaximized ? { position: 'fixed', top: '70px', left: '20px', right: '20px', bottom: '20px', zIndex: 100, margin: 0, borderRadius: '12px', display: 'flex', flexDirection: 'column', overflow: 'hidden' } : {}}>                                <div className={styles.cardHeader} style={{ display: 'flex', flexDirection: 'column', gap: '8px', flexShrink: 0 }}>
                                {/* Title row with window controls */}
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%' }}>
                                    <h2 style={{ margin: 0 }}>
                                        {schedulerSettings?.sim_mode ? '🧪 Sim Positions' : '📊 Open Positions'}
                                    </h2>
                                    <div style={{ display: 'flex', gap: '4px' }}>
                                        <button
                                            onClick={exportPositionsToCsv}
                                            style={{ padding: '4px 8px', fontSize: '14px', background: 'transparent', border: '1px solid #4b5563', borderRadius: '4px', cursor: 'pointer', color: '#9ca3af' }}
                                            title="Export to CSV"
                                        >
                                            📥
                                        </button>
                                        <button
                                            onClick={() => { columnConfig.openEditor(); setShowColumnEditor(true) }}
                                            style={{ padding: '4px 8px', fontSize: '14px', background: 'transparent', border: '1px solid #4b5563', borderRadius: '4px', cursor: 'pointer', color: '#9ca3af' }}
                                            title="Configure columns"
                                        >
                                            ⚙️
                                        </button>
                                        <button
                                            onClick={() => setPositionsMaximized(!positionsMaximized)}
                                            style={{ width: '24px', height: '24px', padding: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'transparent', border: '1px solid #4b5563', borderRadius: '4px', cursor: 'pointer' }}
                                            title={positionsMaximized ? 'Restore' : 'Maximize'}
                                        >
                                            {positionsMaximized ? (
                                                <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="#9ca3af" strokeWidth="1.5">
                                                    <path d="M5 1v4H1M9 13v-4h4M5 5L1 1M9 9l4 4" />
                                                </svg>
                                            ) : (
                                                <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="#9ca3af" strokeWidth="1.5">
                                                    <path d="M1 5V1h4M13 9v4H9M1 1l4 4M13 13l-4-4" />
                                                </svg>
                                            )}
                                        </button>
                                    </div>
                                </div>
                                {/* Badge row */}
                                {schedulerSettings?.sim_mode ? (
                                    <span className={`${styles.badge}`} style={{ backgroundColor: '#8b5cf6', color: '#fff', alignSelf: 'flex-start' }}>
                                        {simPositions?.count || 0} positions • ${simPositions?.account?.portfolio_value?.toFixed(0) || '100,000'}
                                    </span>
                                ) : positions?.count ? (
                                    <span className={`${styles.badge}`} style={{ backgroundColor: positions.total_pnl >= 0 ? '#22c55e' : '#ef4444', color: '#fff', alignSelf: 'flex-start' }}>
                                        {positions.count} positions • {positions.total_pnl >= 0 ? '+' : ''}${positions.total_pnl.toFixed(2)}
                                    </span>
                                ) : null}
                            </div>
                                <div className={styles.cardBody} style={positionsMaximized ? { flex: 1, overflow: 'auto' } : {}}>
                                    {/* SIM MODE: Show MockBroker positions */}
                                    {schedulerSettings?.sim_mode ? (
                                        simPositions?.positions && simPositions.positions.length > 0 ? (
                                            <div style={{ overflowX: 'auto', width: '100%' }}>
                                                <table className={styles.signalTable}>
                                                    <thead>
                                                        <tr>
                                                            <th>Symbol</th>
                                                            <th>Qty</th>
                                                            <th>Avg</th>
                                                            <th>Value</th>
                                                            <th>Stop</th>
                                                            <th>P/L%</th>
                                                        </tr>
                                                    </thead>
                                                    <tbody>
                                                        {simPositions.positions.map((pos) => (
                                                            <tr key={pos.symbol}>
                                                                <td className={styles.symbol}>{pos.symbol}</td>
                                                                <td>{pos.qty}</td>
                                                                <td>${pos.avg_price.toFixed(2)}</td>
                                                                <td>${pos.market_value.toFixed(0)}</td>
                                                                <td style={{ color: '#f59e0b' }}>${pos.stop_price?.toFixed(2) || '-'}</td>
                                                                <td style={{ color: pos.pnl_percent >= 0 ? '#22c55e' : '#ef4444' }}>
                                                                    {pos.pnl_percent >= 0 ? '+' : ''}{pos.pnl_percent.toFixed(1)}%
                                                                </td>
                                                            </tr>
                                                        ))}
                                                    </tbody>
                                                    <tfoot style={{ borderTop: '2px solid #374151' }}>
                                                        <tr style={{ fontWeight: 600 }}>
                                                            <td style={{ color: '#9ca3af' }}>TOTAL ({simPositions.positions.length})</td>
                                                            <td colSpan={2} style={{ color: '#9ca3af' }}>Cost Basis: ${simPositions.positions.reduce((sum, p) => sum + (p.qty * p.avg_price), 0).toFixed(0)}</td>
                                                            <td>${simPositions.positions.reduce((sum, p) => sum + p.market_value, 0).toFixed(0)}</td>
                                                            <td></td>
                                                            <td style={{ color: (simPositions.account?.unrealized_pnl ?? 0) >= 0 ? '#22c55e' : '#ef4444' }}>
                                                                {(simPositions.account?.unrealized_pnl ?? 0) >= 0 ? '+' : ''}{((simPositions.account?.unrealized_pnl || 0) / (simPositions.positions.reduce((sum, p) => sum + p.market_value, 0) - (simPositions.account?.unrealized_pnl || 0)) * 100).toFixed(1)}%
                                                            </td>
                                                        </tr>
                                                    </tfoot>
                                                </table>
                                                {simPositions.account && (
                                                    <div style={{ marginTop: '12px', padding: '8px 12px', backgroundColor: 'rgba(139,92,246,0.1)', borderRadius: '6px', display: 'flex', justifyContent: 'space-between' }}>
                                                        <span style={{ color: '#a78bfa' }}>Cash: <strong>${simPositions.account.cash?.toFixed(0)}</strong></span>
                                                        <span style={{ color: '#a78bfa' }}>Portfolio: <strong>${simPositions.account.portfolio_value?.toFixed(0)}</strong></span>
                                                    </div>
                                                )}
                                            </div>
                                        ) : (
                                            <div className={styles.emptySignals}>
                                                <p>No sim positions yet</p>
                                                <span className={styles.emptyHint}>
                                                    Start scheduler in sim mode to execute mock trades.
                                                </span>
                                            </div>
                                        )
                                    ) : (
                                        /* LIVE MODE: Show Alpaca positions */
                                        positions?.positions && positions.positions.length > 0 ? (
                                            <div className={`${styles.scrollableTable} ${positionsMaximized ? styles.scrollableTableMaximized : ''}`} style={{
                                                overflowX: 'auto',
                                                maxHeight: positionsMaximized ? 'calc(100vh - 200px)' : '300px',
                                                overflowY: positionsMaximized ? 'scroll' : 'auto',
                                                width: '100%',
                                            }}>
                                                <table className={styles.signalTable} style={positionsMaximized ? { width: '100%', tableLayout: 'fixed' } : {}}>
                                                    <thead style={{ position: 'sticky', top: 0, backgroundColor: '#1f2937', zIndex: 10 }}>
                                                        <tr>
                                                            {/* Maximized: show all columns in user's order; Normal: show visible columns only */}
                                                            {(positionsMaximized ? columnConfig.allColumns : columnConfig.columns).map(col => (
                                                                <th
                                                                    key={col.id}
                                                                    onClick={() => setPositionSort(prev => ({
                                                                        column: col.id,
                                                                        direction: prev.column === col.id && prev.direction === 'desc' ? 'asc' : 'desc'
                                                                    }))}
                                                                    style={{ cursor: 'pointer', userSelect: 'none' }}
                                                                    title={`Sort by ${col.label}`}
                                                                >
                                                                    {col.label}
                                                                    {positionSort.column === col.id && (
                                                                        <span style={{ marginLeft: '4px' }}>
                                                                            {positionSort.direction === 'desc' ? '▼' : '▲'}
                                                                        </span>
                                                                    )}
                                                                </th>
                                                            ))}
                                                        </tr>
                                                    </thead>
                                                    <tbody>
                                                        {[...positions.positions]
                                                            .sort((a, b) => {
                                                                const key = positionSort.column as keyof typeof a
                                                                const aVal = a[key] ?? 0
                                                                const bVal = b[key] ?? 0
                                                                if (typeof aVal === 'string' && typeof bVal === 'string') {
                                                                    return positionSort.direction === 'asc'
                                                                        ? aVal.localeCompare(bVal)
                                                                        : bVal.localeCompare(aVal)
                                                                }
                                                                return positionSort.direction === 'asc'
                                                                    ? (aVal as number) - (bVal as number)
                                                                    : (bVal as number) - (aVal as number)
                                                            })
                                                            .map((pos) => (
                                                                <tr key={pos.symbol}>
                                                                    {(positionsMaximized ? columnConfig.allColumns : columnConfig.columns).map((col) => {
                                                                        switch (col.id) {
                                                                            case 'symbol':
                                                                                return <td key={col.id} className={styles.symbol}>{pos.symbol}</td>
                                                                            case 'qty':
                                                                                return <td key={col.id}>{pos.qty}</td>
                                                                            case 'side':
                                                                                return <td key={col.id}>{pos.side?.toUpperCase() || 'LONG'}</td>
                                                                            case 'avg_price':
                                                                                return <td key={col.id}>${pos.avg_price.toFixed(2)}</td>
                                                                            case 'current_price':
                                                                                return <td key={col.id}>${pos.current_price?.toFixed(2) || '-'}</td>
                                                                            case 'stop_price':
                                                                                return <td key={col.id} style={{ color: '#f59e0b' }}>${pos.stop_price?.toFixed(2) || '-'}</td>
                                                                            case 'market_value':
                                                                                return <td key={col.id}>${pos.market_value.toFixed(0)}</td>
                                                                            case 'unrealized_pnl':
                                                                                return (
                                                                                    <td key={col.id} style={{ color: pos.unrealized_pnl > 0 ? '#22c55e' : pos.unrealized_pnl < 0 ? '#ef4444' : '#9ca3af' }}>
                                                                                        {pos.unrealized_pnl >= 0 ? '+' : ''}${pos.unrealized_pnl.toFixed(2)}
                                                                                    </td>
                                                                                )
                                                                            case 'pnl_percent':
                                                                                return (
                                                                                    <td key={col.id} style={{ color: pos.pnl_percent > 0 ? '#22c55e' : pos.pnl_percent < 0 ? '#ef4444' : '#9ca3af' }}>
                                                                                        {pos.pnl_percent >= 0 ? '+' : ''}{pos.pnl_percent.toFixed(1)}%
                                                                                    </td>
                                                                                )
                                                                            case 'today_pnl':
                                                                                const todayPnl = pos.today_pnl || 0
                                                                                return (
                                                                                    <td key={col.id} style={{ color: todayPnl > 0 ? '#22c55e' : todayPnl < 0 ? '#ef4444' : '#9ca3af' }}>
                                                                                        {todayPnl >= 0 ? '+' : ''}${todayPnl.toFixed(2)}
                                                                                    </td>
                                                                                )
                                                                            case 'change_today':
                                                                                const changeToday = pos.change_today || 0
                                                                                return (
                                                                                    <td key={col.id} style={{ color: changeToday > 0 ? '#22c55e' : changeToday < 0 ? '#ef4444' : '#9ca3af' }}>
                                                                                        {changeToday >= 0 ? '+' : ''}{changeToday.toFixed(1)}%
                                                                                    </td>
                                                                                )
                                                                            case 'days_held':
                                                                                return <td key={col.id}>{pos.days_held || 0}d</td>
                                                                            default:
                                                                                return <td key={col.id}>-</td>
                                                                        }
                                                                    })}
                                                                </tr>
                                                            ))}
                                                    </tbody>
                                                    <tfoot style={{ borderTop: '2px solid #374151', position: 'sticky', bottom: 0, backgroundColor: '#1f2937' }}>
                                                        <tr style={{ fontWeight: 600 }}>
                                                            {(positionsMaximized ? columnConfig.allColumns : columnConfig.columns).map((col) => {
                                                                // Calculate totals for each column type
                                                                switch (col.id) {
                                                                    case 'symbol':
                                                                        return <td key={col.id} style={{ color: '#9ca3af' }}>TOTAL ({positions.positions.length})</td>
                                                                    case 'qty':
                                                                        const totalQty = positions.positions.reduce((sum, p) => sum + p.qty, 0)
                                                                        return <td key={col.id}>{totalQty}</td>
                                                                    case 'avg_price':
                                                                        // Show cost basis in avg_price column for totals
                                                                        const costBasis = positions.positions.reduce((sum, p) => sum + (p.qty * p.avg_price), 0)
                                                                        return <td key={col.id} style={{ color: '#9ca3af' }}>${costBasis.toFixed(0)}</td>
                                                                    case 'market_value':
                                                                        return <td key={col.id}>${positions.total_value.toFixed(0)}</td>
                                                                    case 'unrealized_pnl':
                                                                        return (
                                                                            <td key={col.id} style={{ color: positions.total_pnl >= 0 ? '#22c55e' : '#ef4444' }}>
                                                                                {positions.total_pnl >= 0 ? '+' : ''}${positions.total_pnl.toFixed(2)}
                                                                            </td>
                                                                        )
                                                                    case 'pnl_percent':
                                                                        const totalPnlPct = positions.total_value > 0
                                                                            ? (positions.total_pnl / (positions.total_value - positions.total_pnl)) * 100
                                                                            : 0
                                                                        return (
                                                                            <td key={col.id} style={{ color: totalPnlPct >= 0 ? '#22c55e' : '#ef4444' }}>
                                                                                {totalPnlPct >= 0 ? '+' : ''}{totalPnlPct.toFixed(1)}%
                                                                            </td>
                                                                        )
                                                                    case 'today_pnl':
                                                                        const totalTodayPnl = positions.positions.reduce((sum, p) => sum + (p.today_pnl || 0), 0)
                                                                        return (
                                                                            <td key={col.id} style={{ color: totalTodayPnl >= 0 ? '#22c55e' : '#ef4444' }}>
                                                                                {totalTodayPnl >= 0 ? '+' : ''}${totalTodayPnl.toFixed(2)}
                                                                            </td>
                                                                        )
                                                                    default:
                                                                        return <td key={col.id}></td>
                                                                }
                                                            })}
                                                        </tr>
                                                    </tfoot>
                                                </table>
                                                <div style={{ marginTop: '12px', padding: '8px 12px', backgroundColor: 'rgba(255,255,255,0.03)', borderRadius: '6px', display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: '8px' }}>
                                                    <span style={{ color: '#9ca3af' }}>Total Value: <strong>${positions.total_value.toFixed(0)}</strong></span>
                                                    <span style={{ color: positions.total_pnl >= 0 ? '#22c55e' : '#ef4444' }}>
                                                        Total P&L ($): <strong>{positions.total_pnl >= 0 ? '+' : ''}${positions.total_pnl.toFixed(2)}</strong>
                                                    </span>
                                                    <span style={{ color: positions.total_value > 0 ? (positions.total_pnl >= 0 ? '#22c55e' : '#ef4444') : '#9ca3af' }}>
                                                        Total P&L (%): <strong>{positions.total_value > 0 ? `${positions.total_pnl >= 0 ? '+' : ''}${((positions.total_pnl / (positions.total_value - positions.total_pnl)) * 100).toFixed(2)}%` : '0.00%'}</strong>
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
                                        )
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
                                                        <td
                                                            title={`Score Breakdown:\n• RS: ${sig.rs_percentile}th percentile\n• Stop: ${sig.stop_percent?.toFixed(1) || '?'}%\n• Tier: ${sig.tier}\n• Entry: $${parseFloat(sig.entry_price).toFixed(2)}`}
                                                            style={{ cursor: 'help' }}
                                                        >
                                                            {sig.quality_score}/10
                                                        </td>
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
                            {/* NAC Broker/Account Selection */}
                            <div className={styles.settingGroup}>
                                <label>NAC Account</label>
                                <p className={styles.settingHint} style={{ marginTop: 0, marginBottom: '8px' }}>
                                    NAC uses its own account, separate from Dashboard trading.
                                </p>
                                <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                                    <select
                                        value={schedulerSettings?.nac_broker_type || 'alpaca_paper'}
                                        onChange={async (e) => {
                                            try {
                                                const res = await fetch(`${API_BASE}/automation/scheduler/settings`, {
                                                    method: 'PATCH',
                                                    headers: { 'Content-Type': 'application/json' },
                                                    body: JSON.stringify({ nac_broker_type: e.target.value })
                                                })
                                                if (res.ok) {
                                                    const data = await res.json()
                                                    setSchedulerSettings(data)
                                                }
                                            } catch (err) {
                                                console.error('Failed to update nac_broker_type:', err)
                                            }
                                        }}
                                        className={styles.intervalSelect}
                                    >
                                        <option value="alpaca_paper">Alpaca Paper</option>
                                        <option value="alpaca_live">Alpaca Live</option>
                                    </select>
                                    <select
                                        value={schedulerSettings?.nac_account || 'A'}
                                        onChange={async (e) => {
                                            try {
                                                const res = await fetch(`${API_BASE}/automation/scheduler/settings`, {
                                                    method: 'PATCH',
                                                    headers: { 'Content-Type': 'application/json' },
                                                    body: JSON.stringify({ nac_account: e.target.value })
                                                })
                                                if (res.ok) {
                                                    const data = await res.json()
                                                    setSchedulerSettings(data)
                                                }
                                            } catch (err) {
                                                console.error('Failed to update nac_account:', err)
                                            }
                                        }}
                                        className={styles.intervalSelect}
                                    >
                                        <option value="A">Account A (Automation)</option>
                                        <option value="B">Account B</option>
                                    </select>
                                </div>
                            </div>

                            {/* Simulation Mode Toggle */}
                            <div className={styles.settingGroup}>
                                <label className={styles.toggleLabel}>
                                    <span>🧪 Simulation Mode</span>
                                    <button
                                        className={`${styles.toggleBtn} ${schedulerSettings?.sim_mode ? styles.toggleActive : ''}`}
                                        onClick={async () => {
                                            const newValue = !schedulerSettings?.sim_mode
                                            try {
                                                const res = await fetch(`${API_BASE}/automation/scheduler/settings`, {
                                                    method: 'PATCH',
                                                    headers: { 'Content-Type': 'application/json' },
                                                    body: JSON.stringify({ sim_mode: newValue })
                                                })
                                                if (res.ok) {
                                                    const data = await res.json()
                                                    setSchedulerSettings(data)
                                                }
                                            } catch (err) {
                                                console.error('Failed to update sim_mode:', err)
                                            }
                                        }}
                                    >
                                        {schedulerSettings?.sim_mode ? '✅ ON' : '❌ OFF'}
                                    </button>
                                </label>
                                <p className={styles.settingHint}>
                                    When ON, trades use MockBroker (no real orders). Reset sim via API first.
                                </p>
                            </div>
                            {/* Discord Alerts Toggle */}
                            <div className={styles.settingGroup}>
                                <label className={styles.toggleLabel}>
                                    <span>🔔 Discord Alerts</span>
                                    <button
                                        className={`${styles.toggleBtn} ${schedulerSettings?.discord_alerts_enabled !== false ? styles.toggleActive : ''}`}
                                        onClick={async () => {
                                            const newValue = !(schedulerSettings?.discord_alerts_enabled !== false)
                                            try {
                                                const res = await fetch(`${API_BASE}/automation/scheduler/settings`, {
                                                    method: 'PATCH',
                                                    headers: { 'Content-Type': 'application/json' },
                                                    body: JSON.stringify({ discord_alerts_enabled: newValue })
                                                })
                                                if (res.ok) {
                                                    const data = await res.json()
                                                    setSchedulerSettings(data)
                                                }
                                            } catch (err) {
                                                console.error('Failed to update discord_alerts_enabled:', err)
                                            }
                                        }}
                                    >
                                        {(schedulerSettings?.discord_alerts_enabled !== false) ? '✅ ON' : '❌ OFF'}
                                    </button>
                                </label>
                                <p className={styles.settingHint}>
                                    Send Discord notifications for entries and exits (requires DISCORD_WEBHOOK_URL).
                                </p>
                            </div>
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

                                            {/* Min Price Slider */}
                                            <div className={styles.settingGroup}>
                                                <label>Min Stock Price: ${schedulerSettings?.min_price || 5}</label>
                                                <input
                                                    type="range"
                                                    min="2"
                                                    max="10"
                                                    step="0.5"
                                                    value={schedulerSettings?.min_price || 5}
                                                    onChange={async (e) => {
                                                        const min_price = parseFloat(e.target.value)
                                                        try {
                                                            const res = await fetch(`${API_BASE}/automation/scheduler/settings`, {
                                                                method: 'PATCH',
                                                                headers: { 'Content-Type': 'application/json' },
                                                                body: JSON.stringify({ min_price })
                                                            })
                                                            if (res.ok) {
                                                                const data = await res.json()
                                                                setSchedulerSettings(data)
                                                            }
                                                        } catch (err) {
                                                            console.error('Failed to update min_price:', err)
                                                        }
                                                    }}
                                                />
                                            </div>

                                            {/* Min RVOL Slider */}
                                            <div className={styles.settingGroup}>
                                                <label>Min RVOL: {schedulerSettings?.min_rvol || 1.5}x</label>
                                                <input
                                                    type="range"
                                                    min="0.5"
                                                    max="3.0"
                                                    step="0.1"
                                                    value={schedulerSettings?.min_rvol || 1.5}
                                                    className={styles.slider}
                                                    onChange={async (e) => {
                                                        const min_rvol = parseFloat(e.target.value)
                                                        try {
                                                            const res = await fetch(`${API_BASE}/automation/scheduler/settings`, {
                                                                method: 'PATCH',
                                                                headers: { 'Content-Type': 'application/json' },
                                                                body: JSON.stringify({ min_rvol })
                                                            })
                                                            if (res.ok) {
                                                                const data = await res.json()
                                                                setSchedulerSettings(data)
                                                            }
                                                        } catch (err) {
                                                            console.error('Failed to update min_rvol:', err)
                                                        }
                                                    }}
                                                />
                                                <p className={styles.settingHint}>
                                                    Minimum relative volume (1.5x = 50% above average)
                                                </p>
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

                                            {/* Stop Threshold - shows based on stop_mode */}
                                            {schedulerSettings?.stop_mode === 'atr' && (
                                                <div className={styles.settingGroup}>
                                                    <label>Max Stop ATR: {schedulerSettings?.max_stop_atr ?? 1.0}x</label>
                                                    <input
                                                        type="range"
                                                        min="0.5"
                                                        max="3.0"
                                                        step="0.1"
                                                        value={schedulerSettings?.max_stop_atr ?? 1.0}
                                                        className={styles.slider}
                                                        onChange={async (e) => {
                                                            const value = parseFloat(e.target.value)
                                                            try {
                                                                const res = await fetch(`${API_BASE}/automation/scheduler/settings`, {
                                                                    method: 'PATCH',
                                                                    headers: { 'Content-Type': 'application/json' },
                                                                    body: JSON.stringify({ max_stop_atr: value })
                                                                })
                                                                if (res.ok) {
                                                                    const data = await res.json()
                                                                    setSchedulerSettings(data)
                                                                }
                                                            } catch (err) {
                                                                console.error('Failed to update max_stop_atr:', err)
                                                            }
                                                        }}
                                                    />
                                                </div>
                                            )}

                                            {schedulerSettings?.stop_mode === 'percent' && (
                                                <div className={styles.settingGroup}>
                                                    <label>Max Stop %: {schedulerSettings?.max_stop_percent ?? 8}%</label>
                                                    <input
                                                        type="range"
                                                        min="1"
                                                        max="30"
                                                        step="1"
                                                        value={schedulerSettings?.max_stop_percent ?? 8}
                                                        className={styles.slider}
                                                        onChange={async (e) => {
                                                            const value = parseFloat(e.target.value)
                                                            try {
                                                                const res = await fetch(`${API_BASE}/automation/scheduler/settings`, {
                                                                    method: 'PATCH',
                                                                    headers: { 'Content-Type': 'application/json' },
                                                                    body: JSON.stringify({ max_stop_percent: value })
                                                                })
                                                                if (res.ok) {
                                                                    const data = await res.json()
                                                                    setSchedulerSettings(data)
                                                                }
                                                            } catch (err) {
                                                                console.error('Failed to update max_stop_percent:', err)
                                                            }
                                                        }}
                                                    />
                                                </div>
                                            )}
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

                                    {/* Max Position Value */}
                                    <div className={styles.settingGroup}>
                                        <label>Max Position Value ($)</label>
                                        <input
                                            type="number"
                                            min="0"
                                            step="100"
                                            placeholder="Use global setting"
                                            defaultValue={schedulerSettings?.max_position_value || ''}
                                            onBlur={async (e) => {
                                                const value = e.target.value ? parseFloat(e.target.value) : null;
                                                try {
                                                    const res = await fetch(`${API_BASE}/automation/scheduler/settings`, {
                                                        method: 'PATCH',
                                                        headers: { 'Content-Type': 'application/json' },
                                                        body: JSON.stringify({ max_position_value: value })
                                                    });
                                                    if (res.ok) {
                                                        const data = await res.json();
                                                        setSchedulerSettings(data);
                                                    }
                                                } catch (err) {
                                                    console.error('Failed to update max_position_value:', err);
                                                }
                                            }}
                                            className={styles.numberInput}
                                        />
                                        <p className={styles.settingHint}>
                                            Cap per position for automation. Leave empty to use global max_per_symbol from Settings.
                                        </p>
                                    </div>

                                    {/* NAC Max Concurrent Positions */}
                                    <div className={styles.settingGroup}>
                                        <label>Max Concurrent Positions</label>
                                        <input
                                            type="number"
                                            min="1"
                                            step="1"
                                            placeholder="Unlimited"
                                            defaultValue={schedulerSettings?.nac_max_positions || ''}
                                            onBlur={async (e) => {
                                                const value = e.target.value ? parseInt(e.target.value) : null;
                                                try {
                                                    const res = await fetch(`${API_BASE}/automation/scheduler/settings`, {
                                                        method: 'PATCH',
                                                        headers: { 'Content-Type': 'application/json' },
                                                        body: JSON.stringify({ nac_max_positions: value })
                                                    });
                                                    if (res.ok) {
                                                        const data = await res.json();
                                                        setSchedulerSettings(data);
                                                    }
                                                } catch (err) {
                                                    console.error('Failed to update nac_max_positions:', err);
                                                }
                                            }}
                                            className={styles.numberInput}
                                        />
                                        <p className={styles.settingHint}>
                                            Max number of positions NAC can hold simultaneously. Leave empty for unlimited.
                                        </p>
                                    </div>
                                </>
                            )}

                            {/* Auto-Start Settings - Always visible */}
                            <div className={styles.settingGroup} style={{ marginTop: '1rem', borderTop: '1px solid rgba(255,255,255,0.1)', paddingTop: '1rem' }}>
                                <label className={styles.toggleLabel}>
                                    <span>⏰ Auto-Start (Headless)</span>
                                    <button
                                        className={`${styles.toggleBtn} ${schedulerSettings?.auto_start_enabled ? styles.toggleActive : ''}`}
                                        onClick={async () => {
                                            const newValue = !schedulerSettings?.auto_start_enabled
                                            try {
                                                const res = await fetch(`${API_BASE}/automation/scheduler/settings`, {
                                                    method: 'PATCH',
                                                    headers: { 'Content-Type': 'application/json' },
                                                    body: JSON.stringify({ auto_start_enabled: newValue })
                                                })
                                                if (res.ok) {
                                                    const data = await res.json()
                                                    setSchedulerSettings(data)
                                                }
                                            } catch (err) {
                                                console.error('Failed to update auto_start_enabled:', err)
                                            }
                                        }}
                                    >
                                        {schedulerSettings?.auto_start_enabled ? '✅ ON' : '❌ OFF'}
                                    </button>
                                </label>
                                {schedulerSettings?.auto_start_enabled && (
                                    <div style={{ marginTop: '0.5rem' }}>
                                        <label>Start Time (ET)</label>
                                        <input
                                            type="time"
                                            value={schedulerSettings?.auto_start_time || '09:20'}
                                            onChange={async (e) => {
                                                const value = e.target.value;
                                                try {
                                                    const res = await fetch(`${API_BASE}/automation/scheduler/settings`, {
                                                        method: 'PATCH',
                                                        headers: { 'Content-Type': 'application/json' },
                                                        body: JSON.stringify({ auto_start_time: value })
                                                    });
                                                    if (res.ok) {
                                                        const data = await res.json();
                                                        setSchedulerSettings(data);
                                                    }
                                                } catch (err) {
                                                    console.error('Failed to update auto_start_time:', err);
                                                }
                                            }}
                                            className={styles.numberInput}
                                        />
                                    </div>
                                )}

                                {/* Auto Execute toggle - for autonomous trading */}
                                {schedulerSettings?.auto_start_enabled && (
                                    <label className={styles.toggleLabel} style={{ marginTop: '0.5rem' }}>
                                        <span>🤖 Auto Execute Trades</span>
                                        <button
                                            className={`${styles.toggleBtn} ${schedulerSettings?.auto_execute ? styles.toggleActive : ''}`}
                                            onClick={async () => {
                                                try {
                                                    const res = await fetch(`${API_BASE}/automation/scheduler/settings`, {
                                                        method: 'PATCH',
                                                        headers: { 'Content-Type': 'application/json' },
                                                        body: JSON.stringify({ auto_execute: !schedulerSettings?.auto_execute })
                                                    });
                                                    if (res.ok) {
                                                        const data = await res.json()
                                                        setSchedulerSettings(data)
                                                    }
                                                } catch (err) {
                                                    console.error('Failed to update auto_execute:', err)
                                                }
                                            }}
                                        >
                                            {schedulerSettings?.auto_execute ? '✅ ON' : '❌ OFF'}
                                        </button>
                                    </label>
                                )}

                                <p className={styles.settingHint}>
                                    Scheduler auto-starts at configured time. Discord notification sent on start.
                                </p>
                            </div>
                        </div>
                        <div className={styles.modalFooter}>
                            <button className={styles.btnPrimary} onClick={() => setShowSchedulerModal(false)}>
                                Done
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* Trade Events Log - Collapsible */}
            <div className={styles.card} style={{ marginTop: '1.5rem' }}>
                <div className={styles.cardHeader} style={{ cursor: 'pointer' }} onClick={() => setShowTradeEvents(!showTradeEvents)}>
                    <h3>📋 Trade Events Log {showTradeEvents ? '▼' : '▶'}</h3>
                    <span style={{ fontSize: '0.85rem', color: '#888' }}>
                        {tradeEvents.length} recent events
                    </span>
                </div>
                {showTradeEvents && (
                    <div className={styles.cardBody}>
                        {tradeEvents.length === 0 ? (
                            <p style={{ color: '#888', fontStyle: 'italic' }}>No trade events yet</p>
                        ) : (
                            <table className={styles.table} style={{ fontSize: '0.85rem' }}>
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

            {/* Liquidate All Confirmation Modal */}
            {showLiquidateModal && (
                <div className={styles.modalOverlay} onClick={() => { setShowLiquidateModal(false); setLiquidateConfirm(''); setLiquidateResult(null) }}>
                    <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
                        <div className={styles.modalHeader}>
                            <h3>💥 Liquidate All Positions</h3>
                            <button className={styles.closeBtn} onClick={() => { setShowLiquidateModal(false); setLiquidateConfirm(''); setLiquidateResult(null) }}>×</button>
                        </div>
                        <div className={styles.modalBody}>
                            <p style={{ color: '#ef4444', fontWeight: 'bold', marginBottom: '1rem' }}>
                                ⚠️ WARNING: This will sell ALL open positions with market orders!
                            </p>
                            <p style={{ marginBottom: '1rem' }}>
                                Type <strong>"yes"</strong> to confirm:
                            </p>
                            <input
                                type="text"
                                value={liquidateConfirm}
                                onChange={(e) => setLiquidateConfirm(e.target.value)}
                                placeholder='Type "yes" to confirm'
                                className={styles.numberInput}
                                style={{ width: '100%', marginBottom: '1rem' }}
                            />
                            {liquidateResult && (
                                <div style={{
                                    padding: '0.75rem',
                                    borderRadius: '6px',
                                    backgroundColor: liquidateResult.status === 'ok' ? 'rgba(34, 197, 94, 0.2)' : 'rgba(239, 68, 68, 0.2)',
                                    color: liquidateResult.status === 'ok' ? '#22c55e' : '#ef4444',
                                    marginBottom: '1rem'
                                }}>
                                    {liquidateResult.message}
                                    {liquidateResult.closed !== undefined && ` (${liquidateResult.closed} positions closed)`}
                                </div>
                            )}
                        </div>
                        <div className={styles.modalFooter}>
                            <button
                                className={styles.btnSecondary}
                                onClick={() => { setShowLiquidateModal(false); setLiquidateConfirm(''); setLiquidateResult(null) }}
                            >
                                Cancel
                            </button>
                            <button
                                className={styles.btnDanger}
                                onClick={handleLiquidateAll}
                                disabled={actionLoading === 'liquidate'}
                            >
                                {actionLoading === 'liquidate' ? 'Liquidating...' : '💥 Liquidate All'}
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* Column Editor Modal */}
            {showColumnEditor && (
                <div className={styles.modalOverlay} onClick={() => setShowColumnEditor(false)}>
                    <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
                        <ColumnEditor
                            columns={columnConfig.editColumns}
                            onColumnsChange={columnConfig.setEditColumns}
                            onSave={() => { columnConfig.saveEdit(); setShowColumnEditor(false) }}
                            onCancel={() => setShowColumnEditor(false)}
                            onReset={columnConfig.resetEdit}
                        />
                    </div>
                </div>
            )}
        </>
    )
}

