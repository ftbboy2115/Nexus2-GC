/**
 * EventLogCard - Displays scrollable event log with clear button
 */
import styles from '@/styles/Warrior.module.css'

interface EventLogCardProps {
    eventLog: string[]
    onClear: () => void
}

export function EventLogCard({ eventLog, onClear }: EventLogCardProps) {
    return (
        <div className={styles.eventLogCard}>
            <div className={styles.cardHeader}>
                <h2>📜 Event Log</h2>
                <button onClick={onClear} className={styles.clearBtn}>
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
    )
}
