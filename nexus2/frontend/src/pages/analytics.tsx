import { useState, useEffect } from 'react'
import Head from 'next/head'
import Link from 'next/link'
import styles from '@/styles/Analytics.module.css'

interface QuickStats {
    total_trades: number
    win_rate: number
    net_profit: number
    avg_r: number
}

interface TradeStats {
    total_trades: number
    winners: number
    losers: number
    win_rate: number
    total_pnl: number
    avg_win: number
    avg_loss: number
    largest_win: number
    largest_loss: number
    avg_r: number
    expectancy: number
    profit_factor: number
    max_drawdown: number
    avg_hold_days: number
}

interface SetupStats {
    setup_type: string
    stats: TradeStats
}

interface ComparisonStats {
    description: string
    stats: TradeStats
}

export default function Analytics() {
    const [quickStats, setQuickStats] = useState<QuickStats | null>(null)
    const [detailedStats, setDetailedStats] = useState<TradeStats | null>(null)
    const [setupStats, setSetupStats] = useState<SetupStats[]>([])
    const [kkComparison, setKkComparison] = useState<{ kk_style: ComparisonStats, non_kk_style: ComparisonStats } | null>(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)
    const [activeTab, setActiveTab] = useState<'overview' | 'setup' | 'comparison'>('overview')

    // Fetch all analytics data on mount
    useEffect(() => {
        fetchAnalytics()
    }, [])

    const fetchAnalytics = async () => {
        setLoading(true)
        setError(null)

        try {
            // Fetch quick stats
            const quickRes = await fetch('http://localhost:8000/analytics/quick-stats')
            if (quickRes.ok) {
                const data = await quickRes.json()
                setQuickStats(data)
            }

            // Fetch detailed summary
            const summaryRes = await fetch('http://localhost:8000/analytics/summary')
            if (summaryRes.ok) {
                const data = await summaryRes.json()
                if (data.status === 'success') {
                    setDetailedStats(data.stats)
                }
            }

            // Fetch by setup
            const setupRes = await fetch('http://localhost:8000/analytics/by-setup')
            if (setupRes.ok) {
                const data = await setupRes.json()
                if (data.status === 'success') {
                    setSetupStats(data.by_setup || [])
                }
            }

            // Fetch KK comparison
            const kkRes = await fetch('http://localhost:8000/analytics/kk-comparison')
            if (kkRes.ok) {
                const data = await kkRes.json()
                if (data.status === 'success') {
                    setKkComparison({
                        kk_style: data.kk_style,
                        non_kk_style: data.non_kk_style
                    })
                }
            }

        } catch (err) {
            console.error('Analytics fetch error:', err)
            setError('Failed to load analytics data')
        } finally {
            setLoading(false)
        }
    }

    const formatCurrency = (value: number | null | undefined) => {
        if (value == null) return '$0.00'
        const sign = value >= 0 ? '+' : ''
        return `${sign}$${value.toFixed(2)}`
    }

    const formatPercent = (value: number | null | undefined) => {
        if (value == null) return '0.0%'
        return `${value.toFixed(1)}%`
    }

    const formatR = (value: number | null | undefined) => {
        if (value == null) return '0.00R'
        const sign = value >= 0 ? '+' : ''
        return `${sign}${value.toFixed(2)}R`
    }

    const safeNumber = (value: number | null | undefined): number => value ?? 0

    return (
        <>
            <Head>
                <title>Analytics - Nexus 2</title>
            </Head>

            <main className={styles.main}>
                <header className={styles.header}>
                    <div className={styles.headerLeft}>
                        <Link href="/" className={styles.backLink}>← Dashboard</Link>
                        <h1 className={styles.title}>📈 Performance Analytics</h1>
                    </div>
                    <div className={styles.headerRight}>
                        <button
                            onClick={fetchAnalytics}
                            className={styles.refreshBtn}
                            disabled={loading}
                        >
                            {loading ? 'Loading...' : '🔄 Refresh'}
                        </button>
                    </div>
                </header>

                {error && <div className={styles.error}>{error}</div>}

                {/* Quick Stats Cards */}
                <section className={styles.quickStats}>
                    <div className={styles.statCard}>
                        <span className={styles.statLabel}>Total Trades</span>
                        <span className={styles.statValue}>{quickStats?.total_trades || 0}</span>
                    </div>
                    <div className={styles.statCard}>
                        <span className={styles.statLabel}>Win Rate</span>
                        <span className={`${styles.statValue} ${(quickStats?.win_rate || 0) >= 50 ? styles.positive : styles.negative}`}>
                            {formatPercent(quickStats?.win_rate || 0)}
                        </span>
                    </div>
                    <div className={styles.statCard}>
                        <span className={styles.statLabel}>Net Profit</span>
                        <span className={`${styles.statValue} ${(quickStats?.net_profit || 0) >= 0 ? styles.positive : styles.negative}`}>
                            {formatCurrency(quickStats?.net_profit || 0)}
                        </span>
                    </div>
                    <div className={styles.statCard}>
                        <span className={styles.statLabel}>Avg R</span>
                        <span className={`${styles.statValue} ${(quickStats?.avg_r || 0) >= 0 ? styles.positive : styles.negative}`}>
                            {formatR(quickStats?.avg_r || 0)}
                        </span>
                    </div>
                </section>

                {/* Tab Navigation */}
                <nav className={styles.tabs}>
                    <button
                        className={`${styles.tab} ${activeTab === 'overview' ? styles.tabActive : ''}`}
                        onClick={() => setActiveTab('overview')}
                    >
                        Overview
                    </button>
                    <button
                        className={`${styles.tab} ${activeTab === 'setup' ? styles.tabActive : ''}`}
                        onClick={() => setActiveTab('setup')}
                    >
                        By Setup Type
                    </button>
                    <button
                        className={`${styles.tab} ${activeTab === 'comparison' ? styles.tabActive : ''}`}
                        onClick={() => setActiveTab('comparison')}
                    >
                        KK Comparison
                    </button>
                </nav>

                {/* Tab Content */}
                <section className={styles.content}>
                    {activeTab === 'overview' && detailedStats && (
                        <div className={styles.statsGrid}>
                            <div className={styles.statsSection}>
                                <h3>Win/Loss</h3>
                                <div className={styles.statRow}>
                                    <span>Winners</span>
                                    <span className={styles.positive}>{detailedStats.winners}</span>
                                </div>
                                <div className={styles.statRow}>
                                    <span>Losers</span>
                                    <span className={styles.negative}>{detailedStats.losers}</span>
                                </div>
                                <div className={styles.statRow}>
                                    <span>Win Rate</span>
                                    <span>{formatPercent(detailedStats.win_rate)}</span>
                                </div>
                            </div>

                            <div className={styles.statsSection}>
                                <h3>P&L</h3>
                                <div className={styles.statRow}>
                                    <span>Total P&L</span>
                                    <span className={detailedStats.total_pnl >= 0 ? styles.positive : styles.negative}>
                                        {formatCurrency(detailedStats.total_pnl)}
                                    </span>
                                </div>
                                <div className={styles.statRow}>
                                    <span>Avg Win</span>
                                    <span className={styles.positive}>{formatCurrency(detailedStats.avg_win)}</span>
                                </div>
                                <div className={styles.statRow}>
                                    <span>Avg Loss</span>
                                    <span className={styles.negative}>{formatCurrency(detailedStats.avg_loss)}</span>
                                </div>
                            </div>

                            <div className={styles.statsSection}>
                                <h3>Performance</h3>
                                <div className={styles.statRow}>
                                    <span>Avg R-Multiple</span>
                                    <span>{formatR(detailedStats.avg_r)}</span>
                                </div>
                                <div className={styles.statRow}>
                                    <span>Expectancy</span>
                                    <span>{formatCurrency(detailedStats.expectancy)}</span>
                                </div>
                                <div className={styles.statRow}>
                                    <span>Profit Factor</span>
                                    <span>{(detailedStats.profit_factor ?? 0).toFixed(2)}</span>
                                </div>
                            </div>

                            <div className={styles.statsSection}>
                                <h3>Risk</h3>
                                <div className={styles.statRow}>
                                    <span>Max Drawdown</span>
                                    <span className={styles.negative}>{formatCurrency(detailedStats.max_drawdown)}</span>
                                </div>
                                <div className={styles.statRow}>
                                    <span>Largest Win</span>
                                    <span className={styles.positive}>{formatCurrency(detailedStats.largest_win)}</span>
                                </div>
                                <div className={styles.statRow}>
                                    <span>Largest Loss</span>
                                    <span className={styles.negative}>{formatCurrency(detailedStats.largest_loss)}</span>
                                </div>
                            </div>
                        </div>
                    )}

                    {activeTab === 'overview' && !detailedStats && !loading && (
                        <div className={styles.empty}>
                            <p>No trade data available yet.</p>
                            <p>Start trading to see your performance analytics!</p>
                        </div>
                    )}

                    {activeTab === 'setup' && (
                        <div className={styles.setupGrid}>
                            {setupStats.length > 0 ? (
                                setupStats.map((setup) => (
                                    <div key={setup.setup_type} className={styles.setupCard}>
                                        <h3 className={styles.setupType}>{setup.setup_type.toUpperCase()}</h3>
                                        <div className={styles.setupStats}>
                                            <div className={styles.statRow}>
                                                <span>Trades</span>
                                                <span>{setup.stats.total_trades}</span>
                                            </div>
                                            <div className={styles.statRow}>
                                                <span>Win Rate</span>
                                                <span>{formatPercent(setup.stats.win_rate)}</span>
                                            </div>
                                            <div className={styles.statRow}>
                                                <span>Total P&L</span>
                                                <span className={setup.stats.total_pnl >= 0 ? styles.positive : styles.negative}>
                                                    {formatCurrency(setup.stats.total_pnl)}
                                                </span>
                                            </div>
                                            <div className={styles.statRow}>
                                                <span>Avg R</span>
                                                <span>{formatR(setup.stats.avg_r)}</span>
                                            </div>
                                        </div>
                                    </div>
                                ))
                            ) : (
                                <div className={styles.empty}>
                                    <p>No setup-specific data available yet.</p>
                                </div>
                            )}
                        </div>
                    )}

                    {activeTab === 'comparison' && kkComparison && (
                        <div className={styles.comparisonGrid}>
                            <div className={styles.comparisonCard}>
                                <h3 className={styles.comparisonTitle}>🎯 KK-Style (Single Stop)</h3>
                                <p className={styles.comparisonDesc}>{kkComparison.kk_style.description}</p>
                                <div className={styles.comparisonStats}>
                                    <div className={styles.statRow}>
                                        <span>Trades</span>
                                        <span>{kkComparison.kk_style.stats.total_trades}</span>
                                    </div>
                                    <div className={styles.statRow}>
                                        <span>Win Rate</span>
                                        <span>{formatPercent(kkComparison.kk_style.stats.win_rate)}</span>
                                    </div>
                                    <div className={styles.statRow}>
                                        <span>Total P&L</span>
                                        <span className={kkComparison.kk_style.stats.total_pnl >= 0 ? styles.positive : styles.negative}>
                                            {formatCurrency(kkComparison.kk_style.stats.total_pnl)}
                                        </span>
                                    </div>
                                    <div className={styles.statRow}>
                                        <span>Avg R</span>
                                        <span>{formatR(kkComparison.kk_style.stats.avg_r)}</span>
                                    </div>
                                </div>
                            </div>

                            <div className={styles.comparisonCard}>
                                <h3 className={styles.comparisonTitle}>🔬 Dual-Stop (Experimental)</h3>
                                <p className={styles.comparisonDesc}>{kkComparison.non_kk_style.description}</p>
                                <div className={styles.comparisonStats}>
                                    <div className={styles.statRow}>
                                        <span>Trades</span>
                                        <span>{kkComparison.non_kk_style.stats.total_trades}</span>
                                    </div>
                                    <div className={styles.statRow}>
                                        <span>Win Rate</span>
                                        <span>{formatPercent(kkComparison.non_kk_style.stats.win_rate)}</span>
                                    </div>
                                    <div className={styles.statRow}>
                                        <span>Total P&L</span>
                                        <span className={kkComparison.non_kk_style.stats.total_pnl >= 0 ? styles.positive : styles.negative}>
                                            {formatCurrency(kkComparison.non_kk_style.stats.total_pnl)}
                                        </span>
                                    </div>
                                    <div className={styles.statRow}>
                                        <span>Avg R</span>
                                        <span>{formatR(kkComparison.non_kk_style.stats.avg_r)}</span>
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}

                    {activeTab === 'comparison' && !kkComparison && !loading && (
                        <div className={styles.empty}>
                            <p>No comparison data available yet.</p>
                            <p>Trade with both stop strategies to compare performance.</p>
                        </div>
                    )}
                </section>
            </main>
        </>
    )
}
