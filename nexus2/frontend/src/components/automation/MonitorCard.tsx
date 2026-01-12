import styles from '@/styles/Automation.module.css'
import { MonitorStatus } from '@/types/automation'

interface MonitorCardProps {
    monitor: MonitorStatus | null
    actionLoading: string | null
    onStart: () => void
    onStop: () => void
    formatTime: (iso: string | null | undefined) => string
}

export default function MonitorCard({ monitor, actionLoading, onStart, onStop, formatTime }: MonitorCardProps) {
    return (
        <div className={styles.card}>
            <div className={styles.cardHeader}>
                <h2>👁 Monitor</h2>
                <span className={`${styles.statusBadge} ${monitor?.running ? styles.statusRunning : styles.statusStopped}`}>
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
                        onClick={onStop}
                        className={styles.btnDanger}
                        disabled={actionLoading === 'monitor-stop'}
                    >
                        {actionLoading === 'monitor-stop' ? '...' : '⏹ Stop'}
                    </button>
                ) : (
                    <button
                        onClick={onStart}
                        className={styles.btnPrimary}
                        disabled={actionLoading === 'monitor-start'}
                        title="Monitors open positions every 60 sec for stop hits, Day 3-5 partial exits (50%), and moves stops to breakeven after partials"
                    >
                        {actionLoading === 'monitor-start' ? '...' : '▶️ Start'}
                    </button>
                )}
            </div>
        </div>
    )
}
