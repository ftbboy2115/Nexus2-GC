import { useState, useEffect, useCallback } from 'react'
import Head from 'next/head'
import Link from 'next/link'
import styles from '@/styles/Closed.module.css'

interface ClosedPosition {
    id: string
    symbol: string
    setup_type: string | null
    entry_price: string
    shares: number
    initial_stop: string | null
    avg_exit_price: string | null  // Weighted average of all exits
    realized_pnl: string
    opened_at: string | null
    closed_at: string | null
    days_held: number
}

interface ClosedPositionsResponse {
    positions: ClosedPosition[]
    total: number
    total_pnl: string
}

export default function ClosedPositions() {
    const [positions, setPositions] = useState<ClosedPosition[]>([])
    const [totalPnl, setTotalPnl] = useState('0')
    const [loading, setLoading] = useState(true)
    const [demo, setDemo] = useState(false)  // Default to real data

    const generateDemoPositions = (): ClosedPosition[] => {
        const symbols = ['NVDA', 'AAPL', 'META', 'TSLA', 'AMD']
        const now = new Date()

        return symbols.map((symbol, i) => {
            const entry = Math.round((50 + Math.random() * 300) * 100) / 100
            const exitPrice = entry * (1 + (Math.random() - 0.3) * 0.2)
            const pnl = Math.round((Math.random() - 0.3) * 500 * 100) / 100
            const days = Math.floor(Math.random() * 10) + 1
            const openDate = new Date(now.getTime() - (days + 5) * 24 * 60 * 60 * 1000)
            const closeDate = new Date(now.getTime() - i * 24 * 60 * 60 * 1000)

            return {
                id: `demo-${i + 1}`,
                symbol,
                setup_type: ['ep', 'breakout', 'flag'][i % 3],
                entry_price: entry.toFixed(2),
                shares: Math.floor(Math.random() * 100) + 20,
                initial_stop: (entry * 0.95).toFixed(2),
                avg_exit_price: exitPrice.toFixed(2),
                realized_pnl: pnl.toFixed(2),
                opened_at: openDate.toISOString(),
                closed_at: closeDate.toISOString(),
                days_held: days,
            }
        })
    }

    const fetchPositions = useCallback(async () => {
        setLoading(true)

        if (demo) {
            const demoData = generateDemoPositions()
            setPositions(demoData)
            const total = demoData.reduce((sum, p) => sum + parseFloat(p.realized_pnl), 0)
            setTotalPnl(total.toFixed(2))
            setLoading(false)
            return
        }

        try {
            const response = await fetch('/api/positions/closed')
            if (response.ok) {
                const data: ClosedPositionsResponse = await response.json()
                setPositions(data.positions)
                setTotalPnl(data.total_pnl)
            }
        } catch (err) {
            console.error('Failed to fetch closed positions:', err)
        } finally {
            setLoading(false)
        }
    }, [demo])

    useEffect(() => {
        fetchPositions()
    }, [fetchPositions])

    const formatDate = (dateStr: string | null) => {
        if (!dateStr) return '-'
        return new Date(dateStr).toLocaleDateString()
    }

    const getPnlColor = (pnl: string) => {
        const value = parseFloat(pnl)
        if (value > 0) return styles.positive
        if (value < 0) return styles.negative
        return ''
    }

    const winners = positions.filter(p => parseFloat(p.realized_pnl) > 0).length
    const losers = positions.filter(p => parseFloat(p.realized_pnl) < 0).length
    const winRate = positions.length > 0 ? ((winners / positions.length) * 100).toFixed(0) : '0'

    return (
        <>
            <Head>
                <title>Closed Positions - Nexus 2</title>
                <meta name="description" content="View closed trades" />
                <meta name="viewport" content="width=device-width, initial-scale=1" />
            </Head>

            <main className={styles.main}>
                <header className={styles.header}>
                    <div className={styles.headerLeft}>
                        <h1 className={styles.title}>📊 Closed Positions</h1>
                        <Link href="/" className={styles.navLink}>
                            🏠 Dashboard
                        </Link>
                        <Link href="/scanner" className={styles.navLink}>
                            🔍 Scanner
                        </Link>
                        <Link href="/orders" className={styles.navLink}>
                            📋 Orders
                        </Link>
                    </div>
                    <div className={styles.headerRight}>
                        <label className={styles.demoToggle}>
                            <input
                                type="checkbox"
                                checked={demo}
                                onChange={(e) => setDemo(e.target.checked)}
                            />
                            Demo
                        </label>
                        <button
                            className={styles.refreshBtn}
                            onClick={fetchPositions}
                            disabled={loading}
                        >
                            {loading ? 'Loading...' : '🔄 Refresh'}
                        </button>
                    </div>
                </header>

                {/* Stats Summary */}
                <div className={styles.stats}>
                    <div className={styles.statCard}>
                        <span className={styles.statLabel}>Total P&L</span>
                        <span className={`${styles.statValue} ${getPnlColor(totalPnl)}`}>
                            ${parseFloat(totalPnl).toLocaleString('en-US', { minimumFractionDigits: 2 })}
                        </span>
                    </div>
                    <div className={styles.statCard}>
                        <span className={styles.statLabel}>Trades</span>
                        <span className={styles.statValue}>{positions.length}</span>
                    </div>
                    <div className={styles.statCard}>
                        <span className={styles.statLabel}>Win Rate</span>
                        <span className={styles.statValue}>{winRate}%</span>
                    </div>
                    <div className={styles.statCard}>
                        <span className={styles.statLabel}>Winners / Losers</span>
                        <span className={styles.statValue}>
                            <span className={styles.positive}>{winners}</span> / <span className={styles.negative}>{losers}</span>
                        </span>
                    </div>
                </div>

                {loading && positions.length === 0 && (
                    <div className={styles.loading}>Loading closed positions...</div>
                )}

                {!loading && positions.length === 0 && (
                    <div className={styles.empty}>
                        <p>No closed positions yet</p>
                        <p className={styles.hint}>Close a position from the Dashboard to see it here</p>
                    </div>
                )}

                {positions.length > 0 && (
                    <div className={styles.results}>
                        <div className={styles.tableContainer}>
                            <table className={styles.table}>
                                <thead>
                                    <tr>
                                        <th>Symbol</th>
                                        <th>Setup</th>
                                        <th>Shares</th>
                                        <th>Entry</th>
                                        <th>Avg Exit</th>
                                        <th>P&L</th>
                                        <th>Days</th>
                                        <th>Closed</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {positions.map((pos) => (
                                        <tr key={pos.id}>
                                            <td className={styles.symbol}>{pos.symbol}</td>
                                            <td>
                                                <span className={styles.setup}>
                                                    {pos.setup_type?.toUpperCase() || '-'}
                                                </span>
                                            </td>
                                            <td>{pos.shares}</td>
                                            <td>${parseFloat(pos.entry_price).toFixed(2)}</td>
                                            <td>
                                                {pos.avg_exit_price
                                                    ? `$${parseFloat(pos.avg_exit_price).toFixed(2)}`
                                                    : '-'}
                                            </td>
                                            <td className={getPnlColor(pos.realized_pnl)}>
                                                ${parseFloat(pos.realized_pnl).toFixed(2)}
                                            </td>
                                            <td>{pos.days_held}</td>
                                            <td className={styles.date}>
                                                {formatDate(pos.closed_at)}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>
                )}
            </main>
        </>
    )
}
