import React, { useState, useEffect, useCallback } from 'react'
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

interface TradeEvent {
    id: number
    timestamp: string
    event_type: string
    old_value: string | null
    new_value: string | null
    reason: string | null
    symbol: string
    position_id: string
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

const formatEventTime = (iso: string | null) => {
    if (!iso) return '-'
    const utcIso = iso.endsWith('Z') ? iso : iso + 'Z'
    return new Date(utcIso).toLocaleTimeString('en-US', {
        timeZone: 'America/New_York',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
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

const getEventIcon = (eventType: string) => {
    const icons: Record<string, string> = {
        'ENTRY': '🚀',
        'EXIT': '🏁',
        'PARTIAL_EXIT': '📤',
        'STOP_MOVED': '🎯',
        'BREAKEVEN': '⚖️',
        'SCALE_IN': '➕',
    }
    return icons[eventType] || '📝'
}

// =============================================================================
// Trade Events Component
// =============================================================================

function TradeEventsTimeline({ tradeId }: { tradeId: string }) {
    const [events, setEvents] = useState<TradeEvent[]>([])
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        const fetchEvents = async () => {
            try {
                const res = await fetch(`/trade-events/position/${tradeId}?strategy=WARRIOR`)
                if (res.ok) {
                    const data = await res.json()
                    setEvents(data.events || [])
                }
            } catch (err) {
                console.error('Error fetching events:', err)
            } finally {
                setLoading(false)
            }
        }
        fetchEvents()
    }, [tradeId])

    if (loading) {
        return <div style={{ padding: '1rem', color: '#888', fontSize: '0.85rem' }}>Loading events...</div>
    }

    if (events.length === 0) {
        return <div style={{ padding: '1rem', color: '#666', fontSize: '0.85rem', fontStyle: 'italic' }}>No events recorded</div>
    }

    return (
        <div style={{
            padding: '1rem',
            background: 'rgba(0,0,0,0.3)',
            borderTop: '1px solid rgba(255,255,255,0.1)'
        }}>
            <div style={{ fontSize: '0.85rem', fontWeight: 600, marginBottom: '0.75rem', color: '#9ca3af' }}>
                📋 Trade Management Log
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                {events.map((event, idx) => (
                    <div key={event.id || idx} style={{
                        display: 'flex',
                        alignItems: 'flex-start',
                        gap: '0.75rem',
                        padding: '0.5rem',
                        background: 'rgba(255,255,255,0.03)',
                        borderRadius: '6px',
                        fontSize: '0.8rem'
                    }}>
                        <span style={{ fontSize: '1rem' }}>{getEventIcon(event.event_type)}</span>
                        <div style={{ flex: 1 }}>
                            <div style={{ fontWeight: 600, color: '#e0e0e0' }}>
                                {event.event_type.replace('_', ' ')}
                            </div>
                            {event.old_value && event.new_value && (
                                <div style={{ color: '#888', fontSize: '0.75rem' }}>
                                    {event.old_value} → {event.new_value}
                                </div>
                            )}
                            {event.new_value && !event.old_value && (
                                <div style={{ color: '#888', fontSize: '0.75rem' }}>
                                    {event.new_value}
                                </div>
                            )}
                            {event.reason && (
                                <div style={{ color: '#6b7280', fontSize: '0.75rem', fontStyle: 'italic' }}>
                                    {event.reason}
                                </div>
                            )}
                        </div>
                        <div style={{ color: '#6b7280', fontSize: '0.7rem', whiteSpace: 'nowrap' }}>
                            {formatEventTime(event.timestamp)}
                        </div>
                    </div>
                ))}
            </div>
        </div>
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
    const [symbolFilter, setSymbolFilter] = useState<string>('')
    const [dateFilter, setDateFilter] = useState<string>('all')
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

    // Get unique symbols for filter dropdown
    const uniqueSymbols = Array.from(new Set(trades.map(t => t.symbol))).sort()

    // Active positions (non-closed)
    const activePositions = trades.filter(t =>
        t.status !== 'closed' && t.status !== 'rejected'
    )

    // Date filter helper
    const getDateCutoff = (filterType: string): Date | null => {
        const now = new Date()
        switch (filterType) {
            case 'today':
                return new Date(now.getFullYear(), now.getMonth(), now.getDate())
            case 'week':
                const weekAgo = new Date(now)
                weekAgo.setDate(weekAgo.getDate() - 7)
                return weekAgo
            case 'month':
                const monthAgo = new Date(now)
                monthAgo.setMonth(monthAgo.getMonth() - 1)
                return monthAgo
            default:
                return null
        }
    }

    // Closed trades for history (with symbol and date filters)
    const closedTrades = trades.filter(t => {
        const isClosedOrRejected = t.status === 'closed' || t.status === 'rejected'
        const matchesSymbol = !symbolFilter || t.symbol === symbolFilter

        // Date filter
        const dateCutoff = getDateCutoff(dateFilter)
        const matchesDate = !dateCutoff || (t.entry_time && new Date(t.entry_time) >= dateCutoff)

        return isClosedOrRejected && matchesSymbol && matchesDate
    })

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
                        {/* Summary Stats - Schwab Style */}
                        {(() => {
                            // Calculate stats from filtered trades
                            const filteredStats = closedTrades.reduce((acc, t) => {
                                const pnl = parseFloat(t.realized_pnl || '0')
                                const entryPrice = parseFloat(t.entry_price || '0')
                                const exitPrice = parseFloat(t.exit_price || '0')
                                const qty = t.quantity || 0

                                acc.totalTrades++
                                if (pnl > 0) {
                                    acc.winners++
                                    acc.totalGains += pnl
                                } else if (pnl < 0) {
                                    acc.losers++
                                    acc.totalLosses += Math.abs(pnl)
                                }
                                acc.totalPnl += pnl
                                acc.costBasis += entryPrice * qty
                                acc.proceeds += exitPrice * qty
                                return acc
                            }, {
                                totalTrades: 0,
                                winners: 0,
                                losers: 0,
                                totalGains: 0,
                                totalLosses: 0,
                                totalPnl: 0,
                                costBasis: 0,
                                proceeds: 0
                            })

                            const winRate = filteredStats.totalTrades > 0
                                ? (filteredStats.winners / filteredStats.totalTrades)
                                : 0
                            const gainLossRatio = (filteredStats.totalGains + filteredStats.totalLosses) > 0
                                ? (filteredStats.totalGains / (filteredStats.totalGains + filteredStats.totalLosses)) * 100
                                : 0
                            const pnlPercent = filteredStats.costBasis > 0
                                ? (filteredStats.totalPnl / filteredStats.costBasis) * 100
                                : 0

                            return (
                                <div className={styles.card} style={{ marginBottom: '1.25rem' }}>
                                    <div className={styles.cardHeader}>
                                        <h2>📈 Performance Summary</h2>
                                        <span style={{ color: '#888', fontSize: '0.8rem' }}>
                                            {dateFilter === 'all' ? 'All Time' : dateFilter === 'today' ? 'Today' : dateFilter === 'week' ? 'This Week' : 'This Month'}
                                            {symbolFilter && ` • ${symbolFilter}`}
                                        </span>
                                    </div>
                                    <div className={styles.cardBody}>
                                        {/* Top Row: Trade Counts */}
                                        <div className={styles.statsGrid}>
                                            <div className={styles.statBox}>
                                                <div className={styles.statValue}>{filteredStats.totalTrades}</div>
                                                <div className={styles.statLabel}>Total Trades</div>
                                            </div>
                                            <div className={styles.statBox}>
                                                <div className={`${styles.statValue} ${styles.pnlPositive}`}>
                                                    {filteredStats.winners}
                                                </div>
                                                <div className={styles.statLabel}>Winners</div>
                                            </div>
                                            <div className={styles.statBox}>
                                                <div className={`${styles.statValue} ${styles.pnlNegative}`}>
                                                    {filteredStats.losers}
                                                </div>
                                                <div className={styles.statLabel}>Losers</div>
                                            </div>
                                            <div className={styles.statBox}>
                                                <div className={styles.statValue}>
                                                    {(winRate * 100).toFixed(0)}%
                                                </div>
                                                <div className={styles.statLabel}>Win Rate</div>
                                            </div>
                                        </div>

                                        {/* Middle Row: Schwab-Style Financial Summary */}
                                        <div style={{
                                            display: 'grid',
                                            gridTemplateColumns: 'repeat(3, 1fr)',
                                            gap: '1rem',
                                            marginTop: '1rem',
                                            padding: '1rem',
                                            background: 'rgba(0,0,0,0.2)',
                                            borderRadius: '8px'
                                        }}>
                                            {/* Left: Cost Basis & Proceeds */}
                                            <div>
                                                <div style={{ color: '#888', fontSize: '0.75rem', marginBottom: '0.5rem' }}>
                                                    Reporting Period
                                                </div>
                                                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.25rem' }}>
                                                    <span style={{ color: '#aaa', fontSize: '0.8rem' }}>Cost Basis</span>
                                                    <span style={{ color: '#e0e0e0', fontWeight: 500 }}>{formatCurrency(filteredStats.costBasis)}</span>
                                                </div>
                                                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                                    <span style={{ color: '#aaa', fontSize: '0.8rem' }}>Proceeds</span>
                                                    <span style={{ color: '#e0e0e0', fontWeight: 500 }}>{formatCurrency(filteredStats.proceeds)}</span>
                                                </div>
                                            </div>

                                            {/* Center: Gains/Losses */}
                                            <div>
                                                <div style={{ color: '#888', fontSize: '0.75rem', marginBottom: '0.5rem' }}>
                                                    Gain/Loss
                                                </div>
                                                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.25rem' }}>
                                                    <span style={{ color: '#aaa', fontSize: '0.8rem' }}>Total Gains</span>
                                                    <span style={{ color: '#28a745', fontWeight: 500 }}>+{formatCurrency(filteredStats.totalGains)}</span>
                                                </div>
                                                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.25rem' }}>
                                                    <span style={{ color: '#aaa', fontSize: '0.8rem' }}>Total Losses</span>
                                                    <span style={{ color: '#dc3545', fontWeight: 500 }}>-{formatCurrency(filteredStats.totalLosses)}</span>
                                                </div>
                                                <div style={{ display: 'flex', justifyContent: 'space-between', paddingTop: '0.25rem', borderTop: '1px solid rgba(255,255,255,0.1)' }}>
                                                    <span style={{ color: '#aaa', fontSize: '0.8rem' }}>Net Gain</span>
                                                    <span style={{
                                                        color: filteredStats.totalPnl >= 0 ? '#28a745' : '#dc3545',
                                                        fontWeight: 600
                                                    }}>
                                                        {formatPnL(filteredStats.totalPnl)}
                                                        <span style={{ fontSize: '0.7rem', marginLeft: '4px', opacity: 0.8 }}>
                                                            ({pnlPercent >= 0 ? '+' : ''}{pnlPercent.toFixed(2)}%)
                                                        </span>
                                                    </span>
                                                </div>
                                            </div>

                                            {/* Right: Gain/Loss Ratio Gauge */}
                                            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                                                <div style={{ color: '#888', fontSize: '0.75rem', marginBottom: '0.75rem' }}>
                                                    Gain/Loss Ratio
                                                </div>
                                                {/* Gauge */}
                                                <div style={{
                                                    position: 'relative',
                                                    width: '100px',
                                                    height: '50px',
                                                    overflow: 'hidden',
                                                    marginTop: '5px'
                                                }}>
                                                    {/* Background arc */}
                                                    <div style={{
                                                        position: 'absolute',
                                                        width: '100px',
                                                        height: '100px',
                                                        borderRadius: '50%',
                                                        background: `conic-gradient(
                                                            #dc3545 0deg,
                                                            #ffc107 90deg,
                                                            #28a745 180deg
                                                        )`,
                                                        opacity: 0.3
                                                    }} />
                                                    {/* Filled arc based on ratio */}
                                                    <div style={{
                                                        position: 'absolute',
                                                        width: '100px',
                                                        height: '100px',
                                                        borderRadius: '50%',
                                                        background: `conic-gradient(
                                                            ${gainLossRatio < 40 ? '#dc3545' : gainLossRatio < 60 ? '#ffc107' : '#28a745'} 0deg,
                                                            ${gainLossRatio < 40 ? '#dc3545' : gainLossRatio < 60 ? '#ffc107' : '#28a745'} ${gainLossRatio * 1.8}deg,
                                                            transparent ${gainLossRatio * 1.8}deg
                                                        )`
                                                    }} />
                                                    {/* Center cutout */}
                                                    <div style={{
                                                        position: 'absolute',
                                                        top: '15px',
                                                        left: '15px',
                                                        width: '70px',
                                                        height: '70px',
                                                        borderRadius: '50%',
                                                        background: '#1a1a2e'
                                                    }} />
                                                </div>
                                                {/* Value */}
                                                <div style={{
                                                    fontSize: '1.25rem',
                                                    fontWeight: 700,
                                                    color: gainLossRatio < 40 ? '#dc3545' : gainLossRatio < 60 ? '#ffc107' : '#28a745',
                                                    marginTop: '8px'
                                                }}>
                                                    {gainLossRatio.toFixed(1)}%
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            )
                        })()}

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
                                    {/* Expanded Events for Active Positions */}
                                    {expandedTrade && activePositions.some(t => t.id === expandedTrade) && (
                                        <TradeEventsTimeline tradeId={expandedTrade} />
                                    )}
                                </div>
                            </div>
                        )}

                        {/* Trade History */}
                        <div className={styles.card}>
                            <div className={styles.cardHeader}>
                                <h2>📜 Trade History</h2>
                                <div style={{ display: 'flex', gap: '0.5rem' }}>
                                    {/* Symbol Filter */}
                                    <select
                                        value={symbolFilter}
                                        onChange={(e) => setSymbolFilter(e.target.value)}
                                        className={styles.selectInput}
                                        style={{ minWidth: '100px' }}
                                    >
                                        <option value="">All Symbols</option>
                                        {uniqueSymbols.map(sym => (
                                            <option key={sym} value={sym}>{sym}</option>
                                        ))}
                                    </select>
                                    {/* Date Filter */}
                                    <select
                                        value={dateFilter}
                                        onChange={(e) => setDateFilter(e.target.value)}
                                        className={styles.selectInput}
                                        style={{ minWidth: '100px' }}
                                    >
                                        <option value="all">All Time</option>
                                        <option value="today">Today</option>
                                        <option value="week">This Week</option>
                                        <option value="month">This Month</option>
                                    </select>
                                    {/* Status Filter */}
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
                                        {symbolFilter ? `No trades for ${symbolFilter}` : 'No trade history yet'}
                                    </div>
                                ) : (
                                    <div className={styles.positionsTable}>
                                        <table>
                                            <thead>
                                                <tr>
                                                    <th></th>
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
                                                    const isExpanded = expandedTrade === trade.id

                                                    return (
                                                        <React.Fragment key={trade.id}>
                                                            <tr
                                                                onClick={() => setExpandedTrade(
                                                                    isExpanded ? null : trade.id
                                                                )}
                                                                style={{
                                                                    cursor: 'pointer',
                                                                    background: isExpanded ? 'rgba(99, 102, 241, 0.1)' : undefined
                                                                }}
                                                            >
                                                                <td style={{ width: '30px', color: '#666' }}>
                                                                    {isExpanded ? '▼' : '▶'}
                                                                </td>
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
                                                            {isExpanded && (
                                                                <tr>
                                                                    <td colSpan={9} style={{ padding: 0 }}>
                                                                        <TradeEventsTimeline tradeId={trade.id} />
                                                                    </td>
                                                                </tr>
                                                            )}
                                                        </React.Fragment>
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
