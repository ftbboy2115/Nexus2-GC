/**
 * ExitRulesCard - Monitor exit rules display
 */
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
    }
}

interface ExitRulesCardProps {
    monitor?: MonitorStatus
}

export function ExitRulesCard({ monitor }: ExitRulesCardProps) {
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
