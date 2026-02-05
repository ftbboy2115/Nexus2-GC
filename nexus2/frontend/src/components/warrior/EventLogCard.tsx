/**
 * EventLogCard - Displays scrollable event log with clear button
 */
import styles from '@/styles/Warrior.module.css'
import { CollapsibleCard } from './CollapsibleCard'

interface EventLogCardProps {
    eventLog: string[]
    onClear: () => void
}

export function EventLogCard({ eventLog, onClear }: EventLogCardProps) {
    return (
        <CollapsibleCard
            id="event-log"
            title="📜 Event Log"
            badge={
                <button
                    onClick={(e) => { e.stopPropagation(); onClear(); }}
                    className={styles.clearBtn}
                >
                    Clear
                </button>
            }
        >
            <div className={styles.eventLog}>
                {eventLog.length === 0 ? (
                    <p className={styles.emptyLog}>No events yet</p>
                ) : (
                    eventLog.map((log, i) => (
                        <div key={i} className={styles.logEntry}>{log}</div>
                    ))
                )}
            </div>
        </CollapsibleCard>
    )
}

