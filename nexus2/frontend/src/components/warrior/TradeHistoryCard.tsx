/**
 * TradeHistoryCard - Closed trades with AI analysis
 */
import styles from '@/styles/Warrior.module.css'

interface Trade {
    id: string | number
    symbol: string
    entry_price?: number | string
    exit_price?: number | string
    realized_pnl?: number | string
    entry_time?: string
    exit_time?: string
    source?: string  // 'sim' or 'live'
}

interface TradeAnalysis {
    symbol: string
    grades?: Record<string, string>
    summary?: string
    what_went_well?: string[]
    lessons_learned?: string[]
}

interface TradeHistoryCardProps {
    tradeHistory: Trade[]
    showTradeHistory: boolean
    setShowTradeHistory: (show: boolean) => void
    analyzeTradeWithAI: (tradeId: string) => void
    analyzingTrade: string | null
    tradeAnalysis: TradeAnalysis | null
    setTradeAnalysis: (analysis: TradeAnalysis | null) => void
}

export function TradeHistoryCard({
    tradeHistory,
    showTradeHistory,
    setShowTradeHistory,
    analyzeTradeWithAI,
    analyzingTrade,
    tradeAnalysis,
    setTradeAnalysis,
}: TradeHistoryCardProps) {
    const toggleHistory = () => {
        const next = !showTradeHistory
        setShowTradeHistory(next)
        localStorage.setItem('warrior_showTradeHistory', String(next))
    }

    const getGradeColor = (grade?: string): string => {
        if (grade === 'A') return '#22c55e'
        if (grade === 'B') return '#84cc16'
        if (grade === 'C') return '#eab308'
        if (grade === 'D') return '#f97316'
        return '#ef4444'
    }

    // Format datetime for display - convert UTC to Eastern Time
    const formatDateTime = (isoString?: string): string => {
        if (!isoString) return '--'
        const date = new Date(isoString)
        return date.toLocaleString('en-US', {
            month: 'numeric',
            day: 'numeric',
            hour: 'numeric',
            minute: '2-digit',
            hour12: true,
            timeZone: 'America/New_York',  // Force Eastern Time
        })
    }

    // Get source icon based on trigger_type
    // - 'external' = Mock Market (sim) trades
    // - anything else = real LIVE trades
    const getSourceIcon = (trade: Trade): string => {
        const triggerType = (trade as any).trigger_type
        if (triggerType === 'external') return '🧪'
        return '📈'
    }

    return (
        <div className={styles.card} style={{ marginTop: '1rem' }}>
            <div
                className={styles.cardHeader}
                style={{ cursor: 'pointer' }}
                onClick={toggleHistory}
            >
                <h2>📊 Trade History {showTradeHistory ? '▼' : '▶'}</h2>
                <span style={{ fontSize: '0.85rem', color: '#888' }}>
                    {tradeHistory.length} closed trades
                </span>
            </div>
            {showTradeHistory && (
                <div className={styles.cardBody} style={{ padding: '12px' }}>
                    {tradeHistory.length === 0 ? (
                        <p style={{ color: '#888', fontStyle: 'italic' }}>No closed trades yet</p>
                    ) : (
                        <>
                            <div style={{ maxHeight: '400px', overflowY: 'auto' }}>
                                <table className={styles.positionsTable} style={{ fontSize: '0.85rem' }}>
                                    <thead style={{ position: 'sticky', top: 0, background: '#1a1a2e', zIndex: 1 }}>
                                        <tr>
                                            <th>Symbol</th>
                                            <th>Source</th>
                                            <th>Entry $</th>
                                            <th>Exit $</th>
                                            <th>P&L</th>
                                            <th>Entry Time</th>
                                            <th>Exit Time</th>
                                            <th>Action</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {[...tradeHistory]
                                            .sort((a, b) => new Date(b.exit_time || 0).getTime() - new Date(a.exit_time || 0).getTime())
                                            .map((trade) => (
                                                <tr key={trade.id}>
                                                    <td><strong>{trade.symbol}</strong></td>
                                                    <td style={{ textAlign: 'center' }} title={(trade as any).trigger_type || 'live'}>
                                                        {getSourceIcon(trade)}
                                                    </td>
                                                    <td>${parseFloat(String(trade.entry_price || 0)).toFixed(2)}</td>
                                                    <td>${parseFloat(String(trade.exit_price || 0)).toFixed(2)}</td>
                                                    <td style={{
                                                        color: parseFloat(String(trade.realized_pnl || 0)) >= 0 ? '#22c55e' : '#ef4444'
                                                    }}>
                                                        ${parseFloat(String(trade.realized_pnl || 0)).toFixed(2)}
                                                    </td>
                                                    <td style={{ whiteSpace: 'nowrap', fontSize: '0.75rem', color: '#888' }}>
                                                        {formatDateTime(trade.entry_time)}
                                                    </td>
                                                    <td style={{ whiteSpace: 'nowrap', fontSize: '0.75rem' }}>
                                                        {formatDateTime(trade.exit_time)}
                                                    </td>
                                                    <td>
                                                        <button
                                                            onClick={() => analyzeTradeWithAI(String(trade.id))}
                                                            disabled={analyzingTrade === String(trade.id)}
                                                            style={{
                                                                padding: '4px 8px',
                                                                fontSize: '0.75rem',
                                                                backgroundColor: '#3b82f6',
                                                                color: 'white',
                                                                border: 'none',
                                                                borderRadius: '4px',
                                                                cursor: 'pointer',
                                                                opacity: analyzingTrade === trade.id ? 0.5 : 1,
                                                            }}
                                                        >
                                                            {analyzingTrade === trade.id ? '⏳...' : '🤖 Analyze'}
                                                        </button>
                                                    </td>
                                                </tr>
                                            ))}
                                    </tbody>
                                </table>
                            </div>

                            {/* AI Analysis Result */}
                            {tradeAnalysis && (
                                <div style={{
                                    marginTop: '1rem',
                                    padding: '1rem',
                                    backgroundColor: '#1a1a2e',
                                    borderRadius: '8px',
                                    border: '1px solid #333',
                                }}>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                                        <h3 style={{ margin: 0 }}>🤖 AI Analysis: {tradeAnalysis.symbol}</h3>
                                        <button onClick={() => setTradeAnalysis(null)} style={{ background: 'none', border: 'none', color: '#888', cursor: 'pointer' }}>✕</button>
                                    </div>

                                    {/* Grades */}
                                    <div style={{ display: 'flex', gap: '1rem', marginBottom: '1rem' }}>
                                        {['entry', 'exit', 'management', 'overall'].map(key => (
                                            <div key={key} style={{ textAlign: 'center' }}>
                                                <div style={{ fontSize: '0.7rem', color: '#888', textTransform: 'uppercase' }}>{key}</div>
                                                <div style={{
                                                    fontSize: '1.5rem',
                                                    fontWeight: 'bold',
                                                    color: getGradeColor(tradeAnalysis.grades?.[key])
                                                }}>
                                                    {tradeAnalysis.grades?.[key] || '?'}
                                                </div>
                                            </div>
                                        ))}
                                    </div>

                                    {/* Summary */}
                                    <p style={{ color: '#ccc', marginBottom: '0.5rem' }}>{tradeAnalysis.summary}</p>

                                    {/* What Went Well */}
                                    {tradeAnalysis.what_went_well && tradeAnalysis.what_went_well.length > 0 && (
                                        <div style={{ marginBottom: '0.5rem' }}>
                                            <strong style={{ color: '#22c55e' }}>✓ What Went Well:</strong>
                                            <ul style={{ margin: '0.25rem 0', paddingLeft: '1.5rem', color: '#aaa' }}>
                                                {tradeAnalysis.what_went_well.map((item, i) => (
                                                    <li key={i}>{item}</li>
                                                ))}
                                            </ul>
                                        </div>
                                    )}

                                    {/* Lessons Learned */}
                                    {tradeAnalysis.lessons_learned && tradeAnalysis.lessons_learned.length > 0 && (
                                        <div>
                                            <strong style={{ color: '#eab308' }}>📝 Lessons:</strong>
                                            <ul style={{ margin: '0.25rem 0', paddingLeft: '1.5rem', color: '#aaa' }}>
                                                {tradeAnalysis.lessons_learned.map((item, i) => (
                                                    <li key={i}>{item}</li>
                                                ))}
                                            </ul>
                                        </div>
                                    )}
                                </div>
                            )}
                        </>
                    )}
                </div>
            )}
        </div>
    )
}
