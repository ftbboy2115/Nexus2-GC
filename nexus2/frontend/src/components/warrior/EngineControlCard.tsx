/**
 * EngineControlCard - Engine stats, config, and controls
 */
import styles from '@/styles/Warrior.module.css'
import { CollapsibleCard } from './CollapsibleCard'
import { formatCurrency, formatPnL } from './formatters'

interface EngineStats {
    scans_run?: number
    candidates_found?: number
    entries_triggered?: number
    daily_pnl?: number
}

interface EngineConfig {
    risk_per_trade?: number
    max_positions?: number
    max_daily_loss?: number
    orb_enabled?: boolean
    pmh_enabled?: boolean
}

interface BrokerStatus {
    broker_enabled?: boolean
    total_daily_pnl?: number
    daily_pnl_percent?: number
    peak_exposure?: number
}

interface MonitorSettings {
    enable_scaling?: boolean
}

interface EngineControlCardProps {
    state?: string
    stats: EngineStats
    config: EngineConfig
    brokerStatus?: BrokerStatus | null
    monitorSettings?: MonitorSettings | null
    countdown: string
    isRunning: boolean
    isPaused: boolean
    actionLoading: string | null
    startEngine: () => void
    stopEngine: () => void
    pauseEngine: () => void
    resumeEngine: () => void
    updateMonitorSettings: (field: string, value: boolean | number) => void
}

export function EngineControlCard({
    state,
    stats,
    config,
    brokerStatus,
    monitorSettings,
    countdown,
    isRunning,
    isPaused,
    actionLoading,
    startEngine,
    stopEngine,
    pauseEngine,
    resumeEngine,
    updateMonitorSettings,
}: EngineControlCardProps) {
    const dailyPnl = brokerStatus?.broker_enabled ? brokerStatus?.total_daily_pnl : stats.daily_pnl
    const pnlValue = dailyPnl || 0

    return (
        <CollapsibleCard
            id="engine"
            title="🎛️ Engine Control"
            badge={
                <span className={`${styles.stateBadge} ${styles[`state${state}`]}`}>
                    {state?.toUpperCase() || 'UNKNOWN'}
                </span>
            }
        >
            <div className={styles.cardBody}>
                {/* Stats */}
                <div className={styles.statsGrid}>
                    <div className={styles.statBox}>
                        <div className={styles.statValue}>{stats.scans_run || 0}</div>
                        <div className={styles.statLabel}>Scans</div>
                    </div>
                    <div className={styles.statBox}>
                        <div className={styles.statValue}>{stats.candidates_found || 0}</div>
                        <div className={styles.statLabel}>Candidates</div>
                    </div>
                    <div className={styles.statBox}>
                        <div className={styles.statValue}>{stats.entries_triggered || 0}</div>
                        <div className={styles.statLabel}>Entries</div>
                    </div>
                    <div className={styles.statBox}>
                        <div className={`${styles.statValue} ${pnlValue >= 0 ? styles.pnlPositive : styles.pnlNegative}`}>
                            {formatPnL(pnlValue)}
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
                    <span>Risk/Trade: {formatCurrency(config.risk_per_trade || 100)}</span>
                    <span>Max Positions: {config.max_positions || 3}</span>
                    <span>Daily Loss Limit: {formatCurrency(config.max_daily_loss || 300)}</span>
                </div>

                {/* Entry Modes */}
                <div className={styles.entryModes}>
                    <span className={config.orb_enabled ? styles.modeEnabled : styles.modeDisabled}>
                        {config.orb_enabled ? '✅' : '❌'} ORB
                    </span>
                    <span className={config.pmh_enabled ? styles.modeEnabled : styles.modeDisabled}>
                        {config.pmh_enabled ? '✅' : '❌'} PMH
                    </span>
                    <span
                        className={monitorSettings?.enable_scaling ? styles.modeEnabled : styles.modeDisabled}
                        onClick={() => updateMonitorSettings('enable_scaling', !monitorSettings?.enable_scaling)}
                        style={{ cursor: 'pointer' }}
                        title="Click to toggle scaling (add to winners on pullback)"
                    >
                        {actionLoading === 'monitor-enable_scaling' ? '...' : (monitorSettings?.enable_scaling ? '✅' : '❌')} Scale
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
    )
}
