import { useState, useEffect, useCallback } from 'react'
import Head from 'next/head'
import Link from 'next/link'
import styles from '@/styles/Warrior.module.css'

// =============================================================================
// Type Definitions
// =============================================================================

interface Trade {
    id: string
    symbol: string
    status: string
    entry_price: string
    quantity: number
    entry_time: string | null
    trigger_type: string | null
    stop_price: string
    target_price: string | null
    exit_price: string | null
    exit_time: string | null
    exit_reason: string | null
    realized_pnl: string
    partial_taken: boolean
    remaining_quantity: number | null
}

interface TradeSummary {
    total_trades: number
    winning_trades: number
    losing_trades: number
    win_rate: number
    total_pnl: number
}

interface TradeHistoryResponse {
    trades: Trade[]
    summary: TradeSummary
}

// =============================================================================
// Helper Functions
// =============================================================================

const formatCurrency = (value: number | string) => {
    const num = typeof value === 'string' ? parseFloat(value) : value
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(num || 0)
}

const formatPnL = (value: number | string) => {
    const num = typeof value === 'string' ? parseFloat(value) : value
    const formatted = formatCurrency(Math.abs(num || 0))
    if (num > 0) return `+${formatted}`
    if (num < 0) return `-${formatted}`
    return formatted
}

const formatTime = (iso: string | null) => {
    if (!iso) return '-'
    const utcIso = iso.endsWith('Z') ? iso : iso + 'Z'
    return new Date(utcIso).toLocaleString('en-US', {
        timeZone: 'America/New_York',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    })
}

const getPSMBadge = (status: string) => {
    const badges: Record<string, { emoji: string, color: string, label: string }> = {
        'open': { emoji: '🟢', color: '#28a745', label: 'OPEN' },
        'pending_fill': { emoji: '⏳', color: '#ffc107', label: 'PENDING' },
        'pending_exit': { emoji: '🟡', color: '#ffc107', label: 'EXITING' },
        'partial': { emoji: '🔵', color: '#6366f1', label: 'PARTIAL' },
        'scaling': { emoji: '📈', color: '#22c55e', label: 'SCALING' },
        'closed': { emoji: '⚫', color: '#6b7280', label: 'CLOSED' },
        'rejected': { emoji: '❌', color: '#dc3545', label: 'REJECTED' },
    }
    const badge = badges[status] || { emoji: '❓', color: '#888', label: status.toUpperCase() }
    return (
        <span style={{
            color: badge.color,
            fontSize: '0.75rem',
            fontWeight: 600,
            display: 'inline-flex',
            alignItems: 'center',
            gap: '4px'
        }}>
            {badge.emoji} {badge.label}
        </span>
    )
}

// =============================================================================
// Main Component
// =============================================================================

export default function WarriorPerformance() {
    const [trades, setTrades] = useState<Trade[]>([])
    const [summary, setSummary] = useState<TradeSummary | null>(null)
    const [loading, setLoading] = useState(true)
    const [filter, setFilter] = useState<string>('all')
    const [expandedTrade, setExpandedTrade] = useState<string | null>(null)

    const API_BASE = ''

    const fetchTrades = useCallback(async () => {
        try {
            const statusParam = filter !== 'all' ? `&status=${filter}` : ''
            const res = await fetch(`${API_BASE}/warrior/trades?limit=100${statusParam}`)
            if (res.ok) {
                const data: TradeHistoryResponse = await res.json()
                setTrades(data.trades)
                setSummary(data.summary)
            }
        } catch (err) {
            console.error('Error fetching trades:', err)
        } finally {
            setLoading(false)
        }
    }, [filter])

    useEffect(() => {
        fetchTrades()
        const interval = setInterval(fetchTrades, 5000)
        return () => clearInterval(interval)
    }, [fetchTrades])

    // Active positions (non-closed)
    const activePositions = trades.filter(t =>
        t.status !== 'closed' && t.status !== 'rejected'
    )

    // Closed trades for history
    const closedTrades = trades.filter(t =>
        t.status === 'closed' || t.status === 'rejected'
    )

    return (
        <>
            <Head>
                <title>Warrior Performance | Nexus 2</title>
            </Head>

            <main className={styles.container}>
                {/* Header */}
                <header className={styles.header}>
                    <div className={styles.headerLeft}>
                        <Link href="/warrior" className={styles.backLink}>← Back to Warrior</Link>
                        <h1>📊 Performance Dashboard</h1>
                    </div>
                    <div className={styles.headerRight}>
                        <button onClick={fetchTrades} className={styles.refreshBtn}>
                            🔄 Refresh
                        </button>
                    </div>
                </header>

                {loading ? (
                    <div className={styles.loading}>Loading performance data...</div>
                ) : (
                    <>
                        {/* Summary Stats */}
                        <div className={styles.card} style={{ marginBottom: '1.25rem' }}>
                            <div className={styles.cardHeader}>
                                <h2>📈 Performance Summary</h2>
                            </div>
                            <div className={styles.cardBody}>
                                <div className={styles.statsGrid}>
                                    <div className={styles.statBox}>
                                        <div className={styles.statValue}>{summary?.total_trades || 0}</div>
                                        <div className={styles.statLabel}>Total Trades</div>
                                    </div>
                                    <div className={styles.statBox}>
                                        <div className={`${styles.statValue} ${styles.pnlPositive}`}>
                                            {summary?.winning_trades || 0}
                                        </div>
                                        <div className={styles.statLabel}>Winners</div>
                                    </div>
                                    <div className={styles.statBox}>
                                        <div className={`${styles.statValue} ${styles.pnlNegative}`}>
                                            {summary?.losing_trades || 0}
                                        </div>
                                        <div className={styles.statLabel}>Losers</div>
                                    </div>
                                    <div className={styles.statBox}>
                                        <div className={styles.statValue}>
                                            {summary ? `${(summary.win_rate * 100).toFixed(0)}%` : '0%'}
                                        </div>
                                        <div className={styles.statLabel}>Win Rate</div>
                                    </div>
                                </div>
                                <div style={{
                                    display: 'flex',
                                    justifyContent: 'center',
                                    marginTop: '1rem',
                                    padding: '1rem',
                                    background: 'rgba(0,0,0,0.2)',
                                    borderRadius: '8px'
                                }}>
                                    <div style={{ textAlign: 'center' }}>
                                        <div style={{
                                            fontSize: '2rem',
                                            fontWeight: 700,
                                            color: (summary?.total_pnl || 0) >= 0 ? '#28a745' : '#dc3545'
                                        }}>
                                            {formatPnL(summary?.total_pnl || 0)}
                                        </div>
                                        <div style={{ color: '#888', fontSize: '0.85rem', marginTop: '0.25rem' }}>
                                            Total P&L
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        {/* Active Positions */}
                        {activePositions.length > 0 && (
                            <div className={styles.card} style={{ marginBottom: '1.25rem' }}>
                                <div className={styles.cardHeader}>
                                    <h2>🎯 Active Positions</h2>
                                    <span className={styles.countBadge}>{activePositions.length}</span>
                                </div>
                                <div className={styles.cardBody}>
                                    <div className={styles.positionsTable}>
                                        <table>
                                            <thead>
                                                <tr>
                                                    <th>Symbol</th>
                                                    <th>Status</th>
                                                    <th>Entry</th>
                                                    <th>Qty</th>
                                                    <th>Stop</th>
                                                    <th>Target</th>
                                                    <th>Entry Time</th>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {activePositions.map(trade => (
                                                    <tr key={trade.id}>
                                                        <td className={styles.symbol}>{trade.symbol}</td>
                                                        <td>{getPSMBadge(trade.status)}</td>
                                                        <td>{formatCurrency(trade.entry_price)}</td>
                                                        <td>{trade.quantity}</td>
                                                        <td className={styles.stopCell}>
                                                            {formatCurrency(trade.stop_price)}
                                                        </td>
                                                        <td className={styles.targetCell}>
                                                            {trade.target_price ? formatCurrency(trade.target_price) : '-'}
                                                        </td>
                                                        <td>{formatTime(trade.entry_time)}</td>
                                                    </tr>
                                                ))}
                                            </tbody>
                                        </table>
                                    </div>
                                </div>
                            </div>
                        )}

                        {/* Trade History */}
                        <div className={styles.card}>
                            <div className={styles.cardHeader}>
                                <h2>📜 Trade History</h2>
                                <div style={{ display: 'flex', gap: '0.5rem' }}>
                                    <select
                                        value={filter}
                                        onChange={(e) => setFilter(e.target.value)}
                                        className={styles.selectInput}
                                        style={{ minWidth: '120px' }}
                                    >
                                        <option value="all">All Trades</option>
                                        <option value="closed">Closed Only</option>
                                        <option value="open">Open Only</option>
                                    </select>
                                </div>
                            </div>
                            <div className={styles.cardBody}>
                                {closedTrades.length === 0 ? (
                                    <div className={styles.emptyMessage}>
                                        No trade history yet
                                    </div>
                                ) : (
                                    <div className={styles.positionsTable}>
                                        <table>
                                            <thead>
                                                <tr>
                                                    <th>Symbol</th>
                                                    <th>Status</th>
                                                    <th>Entry</th>
                                                    <th>Exit</th>
                                                    <th>Qty</th>
                                                    <th>P&L</th>
                                                    <th>Reason</th>
                                                    <th>Duration</th>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {closedTrades.map(trade => {
                                                    const pnl = parseFloat(trade.realized_pnl || '0')
                                                    let duration = '-'
                                                    if (trade.entry_time && trade.exit_time) {
                                                        const start = new Date(trade.entry_time)
                                                        const end = new Date(trade.exit_time)
                                                        const mins = Math.round((end.getTime() - start.getTime()) / 60000)
                                                        duration = mins < 60 ? `${mins}m` : `${Math.round(mins / 60)}h`
                                                    }

                                                    return (
                                                        <tr
                                                            key={trade.id}
                                                            onClick={() => setExpandedTrade(
                                                                expandedTrade === trade.id ? null : trade.id
                                                            )}
                                                            style={{ cursor: 'pointer' }}
                                                        >
                                                            <td className={styles.symbol}>{trade.symbol}</td>
                                                            <td>{getPSMBadge(trade.status)}</td>
                                                            <td>{formatCurrency(trade.entry_price)}</td>
                                                            <td>{trade.exit_price ? formatCurrency(trade.exit_price) : '-'}</td>
                                                            <td>{trade.quantity}</td>
                                                            <td className={pnl >= 0 ? styles.pnlPositive : styles.pnlNegative}>
                                                                {formatPnL(pnl)}
                                                            </td>
                                                            <td style={{ color: '#888', fontSize: '0.8rem' }}>
                                                                {trade.exit_reason || '-'}
                                                            </td>
                                                            <td style={{ color: '#888' }}>{duration}</td>
                                                        </tr>
                                                    )
                                                })}
                                            </tbody>
                                        </table>
                                    </div>
                                )}
                            </div>
                        </div>
                    </>
                )}
            </main>
        </>
    )
}
