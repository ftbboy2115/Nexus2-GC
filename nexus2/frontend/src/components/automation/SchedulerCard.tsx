import styles from '@/styles/Automation.module.css'
import { SchedulerStatus, SchedulerSettingsData, EngineStatus, ScanDiagnostics, Signal } from '@/types/automation'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface SchedulerCardProps {
    scheduler: SchedulerStatus | null
    schedulerSettings: SchedulerSettingsData | null
    engine: EngineStatus | null
    diagnostics: ScanDiagnostics | null
    sessionSignals: Signal[]
    selectedInterval: number
    countdown: string
    actionLoading: string | null
    showDiagnostics: boolean
    onIntervalChange: (interval: number) => void
    onToggleAutoExecute: () => void
    onStart: () => void
    onStop: () => void
    onOpenSettings: () => void
    onToggleDiagnostics: () => void
    onRefreshStatus: () => void
    formatTime: (iso: string | null | undefined) => string
}

export default function SchedulerCard({
    scheduler,
    schedulerSettings,
    engine,
    diagnostics,
    sessionSignals,
    selectedInterval,
    countdown,
    actionLoading,
    showDiagnostics,
    onIntervalChange,
    onToggleAutoExecute,
    onStart,
    onStop,
    onOpenSettings,
    onToggleDiagnostics,
    onRefreshStatus,
    formatTime,
}: SchedulerCardProps) {

    const handleIntervalChange = async (newInterval: number) => {
        onIntervalChange(newInterval)
        if (scheduler?.running) {
            try {
                const res = await fetch(`${API_BASE}/automation/scheduler/interval`, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ interval_minutes: newInterval }),
                })
                if (res.ok) {
                    await onRefreshStatus()
                }
            } catch (err) {
                console.error('Failed to update interval:', err)
            }
        }
    }

    const exportScannerLog = () => {
        if (!diagnostics?.diagnostics) return
        const headers = ['Scanner', 'Symbol', 'Reason', 'Threshold', 'Actual Value', 'Status']
        const rows: (string | number)[][] = []

        diagnostics.diagnostics.forEach(d => {
            d.rejections.forEach(r => {
                rows.push([d.scanner.toUpperCase(), r.symbol, r.reason, r.threshold, r.actual_value, 'REJECTED'])
            })
        })

        if (sessionSignals.length > 0) {
            sessionSignals.forEach(s => {
                rows.push([s.setup_type.toUpperCase(), s.symbol, 'PASSED_FILTERS', s.quality_score, s.quality_score, 'ACCEPTED'])
            })
        }

        const csv = [headers.join(','), ...rows.map(r => r.join(','))].join('\n')
        const blob = new Blob([csv], { type: 'text/csv' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `scanner_log_${new Date().toISOString().split('T')[0]}.csv`
        a.click()
        URL.revokeObjectURL(url)
    }

    return (
        <div className={styles.card}>
            <div className={styles.cardHeader}>
                <h2>⏰ Scheduler</h2>
                <div className={styles.cardHeaderRight}>
                    <span className={`${styles.statusBadge} ${scheduler?.running ? styles.statusRunning : styles.statusStopped}`}>
                        {scheduler?.running ? 'RUNNING' : 'STOPPED'}
                    </span>
                    <button
                        className={styles.gearBtn}
                        onClick={onOpenSettings}
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
                        onChange={(e) => handleIntervalChange(Number(e.target.value))}
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
                        onClick={onToggleAutoExecute}
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
                    <span>Max Positions:</span>
                    <strong>
                        {schedulerSettings?.nac_max_positions
                            ? schedulerSettings.nac_max_positions
                            : `${engine?.config?.max_positions ?? 5} (Dashboard)`}
                    </strong>
                </div>
                <div className={styles.stat}>
                    <span>Last Run:</span>
                    <strong>{formatTime(scheduler?.last_run)}</strong>
                </div>
                {scheduler?.running && countdown && (
                    <div className={styles.stat} style={{ backgroundColor: 'rgba(59, 130, 246, 0.15)' }}>
                        <span>⏱️ Next Scan:</span>
                        <strong style={{ color: '#60a5fa', fontFamily: 'monospace' }}>{countdown}</strong>
                    </div>
                )}
            </div>

            {/* Collapsible Scan Details */}
            {diagnostics?.available && (
                <div className={styles.scanDetails}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <button
                            className={styles.scanDetailsToggle}
                            onClick={onToggleDiagnostics}
                        >
                            {showDiagnostics ? '▼' : '▶'} Last Scan Details ({diagnostics.duration_ms}ms)
                        </button>
                        <button
                            onClick={exportScannerLog}
                            style={{ padding: '4px 8px', fontSize: '12px', background: 'transparent', border: '1px solid #4b5563', borderRadius: '4px', cursor: 'pointer', color: '#9ca3af' }}
                            title="Export scanner log to CSV"
                        >
                            📥
                        </button>
                    </div>
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
                        onClick={onStop}
                        className={styles.btnDanger}
                        disabled={actionLoading === 'scheduler-stop'}
                    >
                        {actionLoading === 'scheduler-stop' ? '...' : '⏹ Stop'}
                    </button>
                ) : (
                    <button
                        onClick={onStart}
                        className={styles.btnPrimary}
                        disabled={actionLoading === 'scheduler-start'}
                        title="Starts full automation: scans, auto-executes trades, monitors positions, and runs EOD MA check"
                    >
                        {actionLoading === 'scheduler-start' ? '...' : '▶️ Start'}
                    </button>
                )}
            </div>
        </div>
    )
}
