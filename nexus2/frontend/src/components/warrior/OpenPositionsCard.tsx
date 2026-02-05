/**
 * OpenPositionsCard - Active positions table with health indicators
 */
import styles from '@/styles/Warrior.module.css'
import { CollapsibleCard } from './CollapsibleCard'
import { formatTime } from './formatters'
import { PositionHealth } from './types'

interface Position {
    position_id: string | number
    symbol: string
    shares: number
    entry_price: number
    current_stop: number
    profit_target: number
    current_price?: number | null
    high_since_entry: number
    partial_taken?: boolean
    entry_time: string | null
}

interface OpenPositionsCardProps {
    positions: Position[]
    positionHealth: Record<string | number, PositionHealth>
    openChart: (symbol: string) => void
}

export function OpenPositionsCard({
    positions,
    positionHealth,
    openChart,
}: OpenPositionsCardProps) {
    return (
        <CollapsibleCard
            id="open-positions"
            title="📈 Open Positions"
            badge={<span style={{ color: '#888' }}>{positions.length}</span>}
        >
            {positions.length === 0 ? (
                <div style={{ padding: '20px', textAlign: 'center', color: '#888' }}>
                    No open positions
                </div>
            ) : (
                <div className={styles.positionsTable}>
                    <table>
                        <thead>
                            <tr>
                                <th>Symbol</th>
                                <th>Shares</th>
                                <th>Entry</th>
                                <th>Stop</th>
                                <th>Target</th>
                                <th>Current</th>
                                <th>P&L</th>
                                <th>High</th>
                                <th>Health</th>
                                <th>Partial?</th>
                                <th>Time</th>
                            </tr>
                        </thead>
                        <tbody>
                            {positions.map((p) => (
                                <tr key={p.position_id}>
                                    <td className={styles.symbol}>
                                        <span
                                            className={styles.clickableSymbol}
                                            onClick={() => openChart(p.symbol)}
                                            title="Open TradingView chart"
                                        >
                                            {p.symbol}
                                        </span>
                                    </td>
                                    <td>{p.shares}</td>
                                    <td>${p.entry_price.toFixed(2)}</td>
                                    <td className={styles.stopPrice}>${p.current_stop.toFixed(2)}</td>
                                    <td className={styles.targetPrice}>${p.profit_target.toFixed(2)}</td>
                                    <td>{p.current_price ? `$${p.current_price.toFixed(2)}` : '-'}</td>
                                    <td style={{ color: p.current_price ? ((p.current_price - p.entry_price) >= 0 ? '#22c55e' : '#ef4444') : '#888' }}>
                                        {p.current_price ? `${(p.current_price - p.entry_price) >= 0 ? '+' : ''}$${((p.current_price - p.entry_price) * p.shares).toFixed(2)}` : '-'}
                                    </td>
                                    <td>${p.high_since_entry.toFixed(2)}</td>
                                    <td>
                                        {positionHealth[p.position_id] ? (
                                            <div className={styles.indicatorRow} style={{ gap: '2px' }}>
                                                {(['macd', 'ema9', 'ema20', 'ema200', 'vwap', 'volume', 'stop', 'target'] as const).map((key) => {
                                                    const ind = positionHealth[p.position_id]?.[key]
                                                    if (!ind) return null
                                                    const dotClass = ind.status === 'green' ? styles.dotGreen
                                                        : ind.status === 'yellow' ? styles.dotYellow
                                                            : ind.status === 'red' ? styles.dotRed
                                                                : styles.dotGray
                                                    return (
                                                        <span
                                                            key={key}
                                                            className={`${styles.indicatorDot} ${dotClass}`}
                                                            title={ind.tooltip}
                                                        >●</span>
                                                    )
                                                })}
                                            </div>
                                        ) : (
                                            <span style={{ color: '#666' }}>...</span>
                                        )}
                                    </td>
                                    <td>{p.partial_taken ? '✅' : '-'}</td>
                                    <td>{formatTime(p.entry_time)}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </CollapsibleCard>
    )
}

