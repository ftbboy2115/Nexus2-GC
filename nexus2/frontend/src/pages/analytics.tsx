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
    const [sourceFilter, setSourceFilter] = useState<string>('') // '', 'nac', 'manual', 'external'
    const [dateFilter, setDateFilter] = useState<string>('today') // 'today', 'week', 'all'

    // Fetch all analytics data on mount and when filters change
    useEffect(() => {
        fetchAnalytics()
    }, [sourceFilter, dateFilter])

    const fetchAnalytics = async () => {
        setLoading(true)
        setError(null)

        // Build query params
        const params = new URLSearchParams()
        if (sourceFilter) params.append('source', sourceFilter)

        // Add date filter
        const today = new Date().toISOString().split('T')[0]
        if (dateFilter === 'today') {
            params.append('start_date', today)
            params.append('end_date', today)
        } else if (dateFilter === 'week') {
            const weekAgo = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString().split('T')[0]
            params.append('start_date', weekAgo)
        }

        const queryString = params.toString() ? `?${params.toString()}` : ''

        try {
            // Fetch quick stats
            const quickRes = await fetch(`http://localhost:8000/analytics/quick-stats${queryString}`)
            if (quickRes.ok) {
                const data = await quickRes.json()
                setQuickStats(data)
            }

            // Fetch detailed summary
            const summaryRes = await fetch(`http://localhost:8000/analytics/summary${queryString}`)
            if (summaryRes.ok) {
                const data = await summaryRes.json()
                if (data.status === 'success') {
                    setDetailedStats(data.stats)
                }
            }

            // Fetch by setup
            const setupRes = await fetch(`http://localhost:8000/analytics/by-setup${queryString}`)
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
                        <select
                            value={sourceFilter}
                            onChange={(e) => setSourceFilter(e.target.value)}
                            className={styles.sourceFilter}
                        >
                            <option value="">All Trades</option>
                            <option value="nac">NAC Only</option>
                            <option value="manual">Manual Only</option>
                            <option value="external">External Only</option>
                        </select>
                        <select
                            value={dateFilter}
                            onChange={(e) => setDateFilter(e.target.value)}
                            className={styles.sourceFilter}
                        >
                            <option value="today">Today</option>
                            <option value="week">This Week</option>
                            <option value="all">All Time</option>
                        </select>
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
                                    <span className={styles.positive}>{(detailedStats as any).win_count ?? (detailedStats as any).winners ?? 0}</span>
                                </div>
                                <div className={styles.statRow}>
                                    <span>Losers</span>
                                    <span className={styles.negative}>{(detailedStats as any).loss_count ?? (detailedStats as any).losers ?? 0}</span>
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
                                    <span className={((detailedStats as any).net_profit ?? (detailedStats as any).total_pnl ?? 0) >= 0 ? styles.positive : styles.negative}>
                                        {formatCurrency((detailedStats as any).net_profit ?? (detailedStats as any).total_pnl ?? 0)}
                                    </span>
                                </div>
                                <div className={styles.statRow}>
                                    <span>Avg Win</span>
                                    <span className={styles.positive}>{formatCurrency((detailedStats as any).avg_profit ?? (detailedStats as any).avg_win ?? 0)}</span>
                                </div>
                                <div className={styles.statRow}>
                                    <span>Avg Loss</span>
                                    <span className={styles.negative}>{formatCurrency((detailedStats as any).avg_loss ?? 0)}</span>
                                </div>
                            </div>

                            <div className={styles.statsSection}>
                                <h3>Performance</h3>
                                <div className={styles.statRow}>
                                    <span>Expectancy</span>
                                    <span>{formatCurrency((detailedStats as any).expectancy ?? 0)}</span>
                                </div>
                                <div className={styles.statRow}>
                                    <span>Total Trades</span>
                                    <span>{(detailedStats as any).total_trades ?? 0}</span>
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
                                setupStats.map((setup: any) => (
                                    <div key={setup.setup_type} className={styles.setupCard}>
                                        <h3 className={styles.setupType}>{setup.setup_type.toUpperCase()}</h3>
                                        <div className={styles.setupStats}>
                                            <div className={styles.statRow}>
                                                <span>Trades</span>
                                                <span>{setup.count || setup.stats?.total_trades || 0}</span>
                                            </div>
                                            <div className={styles.statRow}>
                                                <span>Win Rate</span>
                                                <span>{formatPercent(setup.win_rate ?? setup.stats?.win_rate ?? 0)}</span>
                                            </div>
                                            <div className={styles.statRow}>
                                                <span>Total P&L</span>
                                                <span className={(setup.net_profit ?? setup.stats?.total_pnl ?? 0) >= 0 ? styles.positive : styles.negative}>
                                                    {formatCurrency(setup.net_profit ?? setup.stats?.total_pnl ?? 0)}
                                                </span>
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
