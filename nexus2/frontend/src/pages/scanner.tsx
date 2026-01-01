import { useState, useEffect } from 'react'
import Head from 'next/head'
import Link from 'next/link'
import styles from '@/styles/Scanner.module.css'

interface ScanResult {
    symbol: string
    name: string
    price: string
    quality_score: number
    passes_filter: boolean
    failed_criteria: string[]
    tier: string
    rs_percentile: number
    adr_percent: string
    price_vs_ma50: string
}

interface ScannerResults {
    results: ScanResult[]
    total: number
    scanned_at: string
}

interface RateStats {
    calls_this_minute: number
    limit_per_minute: number
    remaining: number
    usage_percent: number
}

interface Settings {
    partial_exit_fraction: number
    risk_per_trade: number
}

interface TradeModal {
    isOpen: boolean
    result: ScanResult | null
}

export default function Scanner() {
    const [results, setResults] = useState<ScanResult[]>([])
    const [loading, setLoading] = useState(false)
    const [lastScan, setLastScan] = useState<string | null>(null)
    const [error, setError] = useState<string | null>(null)
    const [rateStats, setRateStats] = useState<RateStats | null>(null)

    // Scan settings
    const [mode, setMode] = useState('gainers')

    // Load cached results on mount
    useEffect(() => {
        try {
            const cached = localStorage.getItem('scanner_results')
            if (cached) {
                const data = JSON.parse(cached)
                setResults(data.results || [])
                setLastScan(data.lastScan || null)
                setMode(data.mode || 'gainers')
                console.log('[Scanner] Loaded cached results:', data.results?.length || 0)
            }
        } catch (err) {
            console.error('Failed to load cached results:', err)
        }
    }, [])
    const [limit, setLimit] = useState(20)
    const [demo, setDemo] = useState(false)  // Default to real data for production

    // Sort state
    type SortKey = 'symbol' | 'price' | 'quality_score' | 'rs_percentile' | 'adr_percent' | 'price_vs_ma50' | 'tier'
    const [sortKey, setSortKey] = useState<SortKey>('quality_score')
    const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')

    // Sort toggle function
    const toggleSort = (key: SortKey) => {
        if (sortKey === key) {
            setSortDir(sortDir === 'asc' ? 'desc' : 'asc')
        } else {
            setSortKey(key)
            setSortDir('desc')  // Default to descending for new column
        }
    }

    // Sorted results
    const sortedResults = [...results].sort((a, b) => {
        let aVal: number, bVal: number
        switch (sortKey) {
            case 'symbol':
                return sortDir === 'asc'
                    ? a.symbol.localeCompare(b.symbol)
                    : b.symbol.localeCompare(a.symbol)
            case 'price':
                aVal = parseFloat(a.price)
                bVal = parseFloat(b.price)
                break
            case 'quality_score':
                aVal = a.quality_score
                bVal = b.quality_score
                break
            case 'rs_percentile':
                aVal = a.rs_percentile
                bVal = b.rs_percentile
                break
            case 'adr_percent':
                aVal = parseFloat(a.adr_percent)
                bVal = parseFloat(b.adr_percent)
                break
            case 'price_vs_ma50':
                aVal = parseFloat(a.price_vs_ma50)
                bVal = parseFloat(b.price_vs_ma50)
                break
            case 'tier':
                const tierOrder = { 'FOCUS': 3, 'WIDE': 2, 'SKIP': 1 }
                aVal = tierOrder[a.tier as keyof typeof tierOrder] || 0
                bVal = tierOrder[b.tier as keyof typeof tierOrder] || 0
                break
            default:
                return 0
        }
        return sortDir === 'asc' ? aVal - bVal : bVal - aVal
    })

    // Trade modal
    const [tradeModal, setTradeModal] = useState<TradeModal>({ isOpen: false, result: null })
    const [tradeShares, setTradeShares] = useState('')
    const [tradeStop, setTradeStop] = useState('')
    const [tradeSubmitting, setTradeSubmitting] = useState(false)
    const [settings, setSettings] = useState<Settings | null>(null)

    // Order notification toast
    const [orderNotification, setOrderNotification] = useState<string | null>(null)

    // Fetch settings on mount
    const fetchSettings = async () => {
        try {
            const res = await fetch('/api/settings')
            if (res.ok) {
                setSettings(await res.json())
            }
        } catch (err) {
            console.error('Failed to fetch settings:', err)
        }
    }

    // Fetch settings on mount
    useEffect(() => {
        fetchSettings()
    }, [])

    // WebSocket for order updates
    useEffect(() => {
        const wsUrl = 'ws://localhost:8000/ws/orders'
        const orderWs = new WebSocket(wsUrl)

        orderWs.onopen = () => {
            console.log('[Scanner WS Orders] Connected')
        }

        orderWs.onmessage = (event) => {
            const data = JSON.parse(event.data)
            if (data.type === 'order_update') {
                const emoji = data.status === 'filled' ? '✅' : data.status === 'pending' ? '⏳' : '📝'
                setOrderNotification(`${emoji} ${data.message}`)

                // Clear after 5 seconds
                setTimeout(() => setOrderNotification(null), 5000)
            }
        }

        orderWs.onerror = (error) => {
            console.error('[Scanner WS Orders] Error:', error)
        }

        return () => {
            orderWs.close()
        }
    }, [])

    const fetchRateStats = async () => {
        try {
            const res = await fetch('/api/scanner/rate-stats')
            if (res.ok) {
                setRateStats(await res.json())
            }
        } catch (err) {
            console.error('Failed to fetch rate stats:', err)
        }
    }

    // Poll rate stats every 5 seconds
    useEffect(() => {
        fetchRateStats()  // Initial fetch
        const interval = setInterval(fetchRateStats, 5000)
        return () => clearInterval(interval)
    }, [])

    const runScanner = async () => {
        setLoading(true)
        setError(null)

        try {
            const response = await fetch('/api/scanner/run', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ mode, limit, demo }),
            })

            if (response.ok) {
                const data: ScannerResults = await response.json()
                const scanTime = new Date(data.scanned_at).toLocaleTimeString()
                setResults(data.results)
                setLastScan(scanTime)

                // Cache results to localStorage
                try {
                    localStorage.setItem('scanner_results', JSON.stringify({
                        results: data.results,
                        lastScan: scanTime,
                        mode,
                        cachedAt: new Date().toISOString(),
                    }))
                } catch (err) {
                    console.error('Failed to cache results:', err)
                }
            } else {
                setError('Failed to run scanner')
            }
        } catch (err) {
            setError('Failed to connect to API')
        } finally {
            setLoading(false)
            await fetchRateStats()
        }
    }

    const getTierColor = (tier: string) => {
        switch (tier) {
            case 'focus': return styles.tierFocus
            case 'wide': return styles.tierWide
            default: return styles.tierUniverse
        }
    }

    const getRateMeterColor = () => {
        if (!rateStats) return styles.meterGreen
        if (rateStats.usage_percent > 80) return styles.meterRed
        if (rateStats.usage_percent > 50) return styles.meterYellow
        return styles.meterGreen
    }

    const openTradeModal = (result: ScanResult) => {
        const price = parseFloat(result.price)
        const adr = parseFloat(result.adr_percent) / 100
        // Suggest stop: 5% below or 1x ADR, whichever is tighter
        const stopPct = Math.min(0.05, adr)
        const suggestedStop = (price * (1 - stopPct)).toFixed(2)

        // Auto-size based on risk settings
        const risk = settings?.risk_per_trade || 250
        const stopDist = price - parseFloat(suggestedStop)
        const suggestedShares = stopDist > 0 ? Math.floor(risk / stopDist) : 100

        setTradeStop(suggestedStop)
        setTradeShares(suggestedShares.toString())
        setTradeModal({ isOpen: true, result })
    }

    const closeTradeModal = () => {
        setTradeModal({ isOpen: false, result: null })
        setTradeShares('')
        setTradeStop('')
    }

    const handleTrade = async () => {
        if (!tradeModal.result) return

        setTradeSubmitting(true)
        try {
            const response = await fetch('/api/trade', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    symbol: tradeModal.result.symbol,
                    shares: parseInt(tradeShares),
                    stop_price: parseFloat(tradeStop),
                    setup_type: mode === 'gainers' ? 'ep' : mode === 'actives' ? 'breakout' : 'flag',
                    order_type: 'market',  // Use market order for quick execution
                }),
            })

            if (response.ok) {
                closeTradeModal()
                alert(`✅ Trade executed: ${tradeShares} shares of ${tradeModal.result.symbol}`)
            } else {
                const err = await response.json()
                console.error('Trade error:', err)
                alert(`❌ Error: ${err.detail || 'Trade failed'}`)
            }
        } catch (err) {
            console.error('Trade exception:', err)
            alert('❌ Failed to execute trade')
        } finally {
            setTradeSubmitting(false)
        }
    }

    return (
        <>
            <Head>
                <title>Scanner - Nexus 2</title>
                <meta name="description" content="KK-style stock scanner" />
                <meta name="viewport" content="width=device-width, initial-scale=1" />
            </Head>

            <main className={styles.main}>
                {/* Order notification toast */}
                {orderNotification && (
                    <div className={styles.orderToast}>
                        {orderNotification}
                    </div>
                )}
                <header className={styles.header}>
                    <div className={styles.headerLeft}>
                        <h1 className={styles.title}>🔍 Scanner</h1>
                        <Link href="/" className={styles.navLink}>
                            🏠 Dashboard
                        </Link>
                        <Link href="/orders" className={styles.navLink}>
                            📋 Orders
                        </Link>
                        <Link href="/closed" className={styles.navLink}>
                            📊 Closed
                        </Link>
                    </div>
                    <div className={styles.headerRight}>
                        {rateStats && (
                            <div className={styles.rateMeter} title={`${rateStats.remaining} API calls remaining`}>
                                <div className={styles.meterLabel}>
                                    API: {rateStats.calls_this_minute}/{rateStats.limit_per_minute}
                                </div>
                                <div className={styles.meterBar}>
                                    <div
                                        className={`${styles.meterFill} ${getRateMeterColor()}`}
                                        style={{ width: `${rateStats.usage_percent}%` }}
                                    />
                                </div>
                            </div>
                        )}
                        {lastScan && (
                            <span className={styles.lastScan}>Last scan: {lastScan}</span>
                        )}
                        <select
                            className={styles.modeSelect}
                            value={mode}
                            onChange={(e) => setMode(e.target.value)}
                            disabled={loading}
                        >
                            <option value="gainers">🚀 EP Candidates (Gainers)</option>
                            <option value="actives">📊 Most Active</option>
                            <option value="trend_leaders">🏆 Quality Screener</option>
                        </select>
                        <select
                            className={styles.limitSelect}
                            value={limit}
                            onChange={(e) => setLimit(parseInt(e.target.value))}
                            disabled={loading}
                        >
                            <option value="10">10 stocks</option>
                            <option value="20">20 stocks</option>
                            <option value="50">50 stocks</option>
                        </select>
                        <label className={styles.demoToggle}>
                            <input
                                type="checkbox"
                                checked={demo}
                                onChange={(e) => setDemo(e.target.checked)}
                                disabled={loading}
                            />
                            Demo
                        </label>
                        <button
                            className={`${styles.scanBtn} ${loading ? styles.scanning : ''}`}
                            onClick={runScanner}
                            disabled={loading}
                        >
                            {loading ? '⟳ Scanning...' : '🔍 Run Scanner'}
                        </button>
                    </div>
                </header>

                {error && (
                    <div className={styles.error}>{error}</div>
                )}

                {results.length === 0 && !loading && (
                    <div className={styles.empty}>
                        <p>No scanner results yet</p>
                        <p className={styles.hint}>Click "Run Scanner" to scan for setups</p>
                    </div>
                )}

                {results.length > 0 && (
                    <div className={styles.results}>
                        <div className={styles.summary}>
                            <span>Found {results.filter(r => r.passes_filter).length} passing stocks</span>
                            <span className={styles.total}>({results.length} total)</span>
                        </div>

                        <div className={styles.tableContainer}>
                            <table className={styles.table}>
                                <thead>
                                    <tr>
                                        <th className={styles.sortable} onClick={() => toggleSort('symbol')}>
                                            Symbol {sortKey === 'symbol' && (sortDir === 'asc' ? '↑' : '↓')}
                                        </th>
                                        <th>Name</th>
                                        <th className={styles.sortable} onClick={() => toggleSort('price')}>
                                            Price {sortKey === 'price' && (sortDir === 'asc' ? '↑' : '↓')}
                                        </th>
                                        <th className={styles.sortable} onClick={() => toggleSort('quality_score')}>
                                            Quality {sortKey === 'quality_score' && (sortDir === 'asc' ? '↑' : '↓')}
                                        </th>
                                        <th className={styles.sortable} onClick={() => toggleSort('rs_percentile')}>
                                            RS {sortKey === 'rs_percentile' && (sortDir === 'asc' ? '↑' : '↓')}
                                        </th>
                                        <th className={styles.sortable} onClick={() => toggleSort('adr_percent')}>
                                            ADR {sortKey === 'adr_percent' && (sortDir === 'asc' ? '↑' : '↓')}
                                        </th>
                                        <th className={styles.sortable} onClick={() => toggleSort('price_vs_ma50')}>
                                            vs 50MA {sortKey === 'price_vs_ma50' && (sortDir === 'asc' ? '↑' : '↓')}
                                        </th>
                                        <th className={styles.sortable} onClick={() => toggleSort('tier')}>
                                            Tier {sortKey === 'tier' && (sortDir === 'asc' ? '↑' : '↓')}
                                        </th>
                                        <th>Status</th>
                                        <th>Action</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {sortedResults.map((result) => (
                                        <tr key={result.symbol} className={result.passes_filter ? '' : styles.failed}>
                                            <td className={styles.symbol}>{result.symbol}</td>
                                            <td className={styles.name}>{result.name}</td>
                                            <td>${parseFloat(result.price).toFixed(2)}</td>
                                            <td>
                                                <span
                                                    className={styles.qualityScore}
                                                    title={`Quality Score: ${result.quality_score}/10\n\nFactors (KK-style):\n• RS Percentile (higher = stronger)\n• Volume expansion vs average\n• Price vs 50/200 MA alignment\n• Gap/catalyst strength\n• Tightness of pattern\n• Distance from highs`}
                                                >
                                                    {result.quality_score}/10
                                                </span>
                                            </td>
                                            <td>{result.rs_percentile}%</td>
                                            <td>{parseFloat(result.adr_percent).toFixed(1)}%</td>
                                            <td className={parseFloat(result.price_vs_ma50) >= 0 ? styles.positive : styles.negative}>
                                                {parseFloat(result.price_vs_ma50) >= 0 ? '+' : ''}{parseFloat(result.price_vs_ma50).toFixed(1)}%
                                            </td>
                                            <td>
                                                <span className={`${styles.tier} ${getTierColor(result.tier)}`}>
                                                    {result.tier}
                                                </span>
                                            </td>
                                            <td>
                                                {result.passes_filter ? (
                                                    <span className={styles.pass}>✓ Pass</span>
                                                ) : (
                                                    <span className={styles.fail} title={result.failed_criteria.join('\n')}>
                                                        ✗ {result.failed_criteria.length} issues
                                                    </span>
                                                )}
                                            </td>
                                            <td>
                                                <button
                                                    className={styles.tradeBtn}
                                                    onClick={() => openTradeModal(result)}
                                                >
                                                    Trade
                                                </button>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>
                )}

                {/* Trade Modal */}
                {tradeModal.isOpen && tradeModal.result && (
                    <div className={styles.modalOverlay} onClick={closeTradeModal}>
                        <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
                            <h2 className={styles.modalTitle}>
                                📈 Trade {tradeModal.result.symbol}
                            </h2>
                            <p className={styles.modalSubtitle}>{tradeModal.result.name}</p>

                            <div className={styles.tradeInfo}>
                                <div className={styles.infoRow}>
                                    <span>Current Price:</span>
                                    <strong>${parseFloat(tradeModal.result.price).toFixed(2)}</strong>
                                </div>
                                <div className={styles.infoRow}>
                                    <span>Tier:</span>
                                    <span className={`${styles.tier} ${styles[tradeModal.result.tier.toLowerCase()]}`}>
                                        {tradeModal.result.tier}
                                    </span>
                                </div>
                                <div className={styles.infoRow}>
                                    <span>Setup Type:</span>
                                    <strong>{mode === 'gainers' ? 'EP' : mode === 'actives' ? 'Breakout' : 'Flag'}</strong>
                                </div>
                            </div>

                            <div className={styles.formGroup}>
                                <label>Shares</label>
                                <input
                                    type="number"
                                    value={tradeShares}
                                    onChange={(e) => setTradeShares(e.target.value)}
                                    className={styles.input}
                                />
                                <span className={styles.hint}>
                                    Position: ${(parseInt(tradeShares || '0') * parseFloat(tradeModal.result.price)).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                </span>
                            </div>

                            <div className={styles.formGroup}>
                                <label>Stop Price</label>
                                <input
                                    type="number"
                                    step="0.01"
                                    value={tradeStop}
                                    onChange={(e) => setTradeStop(e.target.value)}
                                    className={styles.input}
                                />
                                <span className={styles.hint}>
                                    {tradeStop && (
                                        <>Stop: {((1 - parseFloat(tradeStop) / parseFloat(tradeModal.result.price)) * 100).toFixed(1)}% below entry</>
                                    )}
                                </span>
                            </div>

                            {/* Risk Preview */}
                            <div className={styles.riskPreview}>
                                <div className={styles.riskRow}>
                                    <span>💰 Risk per trade:</span>
                                    <strong className={styles.riskAmount}>
                                        ${tradeShares && tradeStop
                                            ? ((parseFloat(tradeModal.result.price) - parseFloat(tradeStop)) * parseInt(tradeShares)).toFixed(2)
                                            : '—'}
                                    </strong>
                                </div>
                                <div className={styles.riskRow}>
                                    <span>🎯 Target (1R):</span>
                                    <strong>
                                        ${tradeStop
                                            ? (parseFloat(tradeModal.result.price) + (parseFloat(tradeModal.result.price) - parseFloat(tradeStop))).toFixed(2)
                                            : '—'}
                                    </strong>
                                </div>
                            </div>

                            <div className={styles.modalActions}>
                                <button
                                    className={styles.cancelBtn}
                                    onClick={closeTradeModal}
                                >
                                    Cancel
                                </button>
                                <button
                                    className={styles.executeBtn}
                                    onClick={handleTrade}
                                    disabled={tradeSubmitting || !tradeShares || !tradeStop}
                                >
                                    {tradeSubmitting ? '⟳ Executing...' : '✓ Execute Trade'}
                                </button>
                            </div>
                        </div>
                    </div>
                )}
            </main>
        </>
    )
}
