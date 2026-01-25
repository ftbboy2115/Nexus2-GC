/**
 * ExitRulesCard - Monitor exit rules display with exit mode toggle
 */
import { useState } from 'react'
import styles from '@/styles/Warrior.module.css'
import { CollapsibleCard } from './CollapsibleCard'

interface MonitorStatus {
    running?: boolean
    checks_run?: number
    exits_triggered?: number
    partials_triggered?: number
    settings?: {
        mental_stop_cents?: number
        profit_target_r?: number
        partial_exit_fraction?: number
        candle_under_candle?: boolean
        topping_tail?: boolean
        session_exit_mode?: string  // "base_hit" or "home_run"
    }
}

interface ExitRulesCardProps {
    monitor?: MonitorStatus
    onRefresh?: () => void  // Callback to refresh data after mode change
}

export function ExitRulesCard({ monitor, onRefresh }: ExitRulesCardProps) {
    const [isToggling, setIsToggling] = useState(false)
    const currentMode = monitor?.settings?.session_exit_mode || 'base_hit'

    const toggleExitMode = async () => {
        setIsToggling(true)
        const newMode = currentMode === 'base_hit' ? 'home_run' : 'base_hit'

        try {
            const response = await fetch(`/warrior/exit-mode?mode=${newMode}`, {
                method: 'POST',
            })

            if (response.ok) {
                // Refresh parent data to reflect change
                onRefresh?.()
            } else {
                console.error('Failed to toggle exit mode')
            }
        } catch (error) {
            console.error('Error toggling exit mode:', error)
        } finally {
            setIsToggling(false)
        }
    }

    return (
        <CollapsibleCard
            id="exitrules"
            title="🛡️ Exit Rules"
            badge={
                <span className={`${styles.badge} ${monitor?.running ? styles.badgeGreen : styles.badgeGray}`}>
                    {monitor?.running ? 'Active' : 'Inactive'}
                </span>
            }
        >
            <div className={styles.cardBody}>
                {/* Exit Mode Toggle - First Item */}
                <div className={styles.ruleItem} style={{ marginBottom: '1rem', paddingBottom: '0.75rem', borderBottom: '1px solid rgba(255,255,255,0.1)' }}>
                    <span className={styles.ruleLabel}>Exit Mode</span>
                    <button
                        onClick={toggleExitMode}
                        disabled={isToggling}
                        className={`${styles.exitModeToggle} ${currentMode === 'home_run' ? styles.homeRun : styles.baseHit}`}
                        style={{
                            padding: '0.25rem 0.75rem',
                            borderRadius: '4px',
                            border: 'none',
                            cursor: isToggling ? 'wait' : 'pointer',
                            fontWeight: 600,
                            fontSize: '0.85rem',
                            background: currentMode === 'home_run'
                                ? 'linear-gradient(135deg, #10b981 0%, #059669 100%)'
                                : 'linear-gradient(135deg, #f59e0b 0%, #d97706 100%)',
                            color: '#fff',
                            boxShadow: '0 2px 4px rgba(0,0,0,0.2)',
                            transition: 'all 0.2s ease',
                        }}
                    >
                        {isToggling ? '...' : currentMode === 'home_run' ? '🚀 Home Run' : '⚾ Base Hit'}
                    </button>
                </div>

                <div className={styles.rulesList}>
                    <div className={styles.ruleItem}>
                        <span className={styles.ruleLabel}>Mental Stop</span>
                        <span className={styles.ruleValue}>{monitor?.settings?.mental_stop_cents || 15}¢</span>
                    </div>
                    <div className={styles.ruleItem}>
                        <span className={styles.ruleLabel}>Profit Target</span>
                        <span className={styles.ruleValue}>{monitor?.settings?.profit_target_r || 2}:1 R</span>
                    </div>
                    <div className={styles.ruleItem}>
                        <span className={styles.ruleLabel}>Partial Exit</span>
                        <span className={styles.ruleValue}>{(monitor?.settings?.partial_exit_fraction || 0.5) * 100}%</span>
                    </div>
                    <div className={styles.ruleItem}>
                        <span className={styles.ruleLabel}>Candle-Under-Candle</span>
                        <span className={styles.ruleValue}>{monitor?.settings?.candle_under_candle ? '✅' : '❌'}</span>
                    </div>
                    <div className={styles.ruleItem}>
                        <span className={styles.ruleLabel}>Topping Tail</span>
                        <span className={styles.ruleValue}>{monitor?.settings?.topping_tail ? '✅' : '❌'}</span>
                    </div>
                </div>

                {/* Monitor Stats */}
                <div className={styles.monitorStats}>
                    <span>Checks: {monitor?.checks_run || 0}</span>
                    <span>Exits: {monitor?.exits_triggered || 0}</span>
                    <span>Partials: {monitor?.partials_triggered || 0}</span>
                </div>
            </div>
        </CollapsibleCard>
    )
}
