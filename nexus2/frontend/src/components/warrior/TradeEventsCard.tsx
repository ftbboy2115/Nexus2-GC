/**
 * TradeEventsCard - Collapsible trade events log
 */
import styles from '@/styles/Warrior.module.css'
import { formatTime } from './formatters'

interface TradeEvent {
    id?: number
    created_at: string
    symbol: string
    event_type?: string
    reason?: string
    new_value?: number
    exit_mode?: string
}

interface TradeEventsCardProps {
    tradeEvents: TradeEvent[]
    showTradeEvents: boolean
    setShowTradeEvents: (show: boolean) => void
}

export function TradeEventsCard({
    tradeEvents,
    showTradeEvents,
    setShowTradeEvents,
}: TradeEventsCardProps) {
    const toggleEvents = () => {
        const next = !showTradeEvents
        setShowTradeEvents(next)
        localStorage.setItem('warrior_showTradeEvents', String(next))
    }

    // Get entry type icon from exit_mode
    const getEntryTypeIcon = (exitMode?: string): string => {
        if (!exitMode) return '--'
        if (exitMode === 'home_run') return '🚀'
        if (exitMode === 'base_hit') return '⚾'
        return '--'
    }

    return (
        <div className={styles.card} style={{ marginTop: '1rem' }}>
            <div
                className={styles.cardHeader}
                style={{ cursor: 'pointer' }}
                onClick={toggleEvents}
            >
                <h2>📋 Trade Events Log {showTradeEvents ? '▼' : '▶'}</h2>
                <span style={{ fontSize: '0.85rem', color: '#888' }}>
                    {tradeEvents.length} recent events
                </span>
            </div>
            {showTradeEvents && (
                <div className={styles.cardBody} style={{ padding: '12px' }}>
                    {tradeEvents.length === 0 ? (
                        <p style={{ color: '#888', fontStyle: 'italic' }}>No trade events yet</p>
                    ) : (
                        <table className={styles.positionsTable} style={{ fontSize: '0.85rem' }}>
                            <thead>
                                <tr>
                                    <th>Time (ET)</th>
                                    <th>Symbol</th>
                                    <th>Entry Type</th>
                                    <th>Event</th>
                                    <th>Details</th>
                                </tr>
                            </thead>
                            <tbody>
                                {tradeEvents.map((event: TradeEvent, idx: number) => (
                                    <tr key={event.id || idx}>
                                        <td style={{ whiteSpace: 'nowrap' }}>
                                            {formatTime(event.created_at)}
                                        </td>
                                        <td><strong>{event.symbol}</strong></td>
                                        <td style={{ textAlign: 'center' }} title={event.exit_mode || 'N/A'}>
                                            {getEntryTypeIcon(event.exit_mode)}
                                        </td>
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
    )
}

