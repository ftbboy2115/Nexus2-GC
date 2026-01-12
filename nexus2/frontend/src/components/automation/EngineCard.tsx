import styles from '@/styles/Automation.module.css'
import { EngineStatus } from '@/types/automation'

interface EngineCardProps {
    engine: EngineStatus | null
    actionLoading: string | null
    onStart: () => void
    onStop: () => void
}

export default function EngineCard({ engine, actionLoading, onStart, onStop }: EngineCardProps) {
    return (
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
                        onClick={onStop}
                        className={styles.btnDanger}
                        disabled={actionLoading === 'engine-stop'}
                    >
                        {actionLoading === 'engine-stop' ? '...' : '⏹ Stop'}
                    </button>
                ) : (
                    <button
                        onClick={onStart}
                        className={styles.btnPrimary}
                        disabled={actionLoading === 'engine-start'}
                        title="Core automation engine. Manages order execution, position tracking, and trade lifecycle."
                    >
                        {actionLoading === 'engine-start' ? '...' : '▶️ Start'}
                    </button>
                )}
            </div>
        </div>
    )
}
