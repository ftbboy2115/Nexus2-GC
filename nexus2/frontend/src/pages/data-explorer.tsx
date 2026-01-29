import { useState, useEffect, useCallback } from 'react'
import Head from 'next/head'
import Link from 'next/link'
import styles from '@/styles/DataExplorer.module.css'

type TabType = 'trade-events' | 'warrior-trades' | 'nac-trades' | 'scan-history'

interface Column {
    key: string
    label: string
    visible: boolean
}

export default function DataExplorer() {
    const [activeTab, setActiveTab] = useState<TabType>('trade-events')
    const [data, setData] = useState<any[]>([])
    const [total, setTotal] = useState(0)
    const [loading, setLoading] = useState(true)
    const [limit, setLimit] = useState(50)
    const [offset, setOffset] = useState(0)
    const [sortBy, setSortBy] = useState('')
    const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')
    const [filters, setFilters] = useState<Record<string, string>>({})

    const tabEndpoints: Record<TabType, string> = {
        'trade-events': '/api/trade-events/recent',
        'warrior-trades': '/api/warrior/trades',
        'nac-trades': '/api/data/nac-trades',
        'scan-history': '/api/data/scan-history',
    }

    const fetchData = useCallback(async () => {
        setLoading(true)
        try {
            const params = new URLSearchParams()
            params.set('limit', String(limit))
            params.set('offset', String(offset))
            if (sortBy) {
                params.set('sort_by', sortBy)
                params.set('sort_dir', sortDir)
            }
            Object.entries(filters).forEach(([key, value]) => {
                if (value) params.set(key, value)
            })

            const response = await fetch(`${tabEndpoints[activeTab]}?${params}`)
            if (response.ok) {
                const result = await response.json()
                // Handle different response shapes
                const items = result.trades || result.events || result.entries || result || []
                setData(Array.isArray(items) ? items : [])
                setTotal(result.total || items.length)
            }
        } catch (err) {
            console.error('Fetch error:', err)
            setData([])
        } finally {
            setLoading(false)
        }
    }, [activeTab, limit, offset, sortBy, sortDir, filters])

    useEffect(() => {
        setOffset(0)
        setFilters({})
        setSortBy('')
        fetchData()
    }, [activeTab])

    useEffect(() => {
        fetchData()
    }, [fetchData])

    const handleSort = (column: string) => {
        if (sortBy === column) {
            setSortDir(sortDir === 'asc' ? 'desc' : 'asc')
        } else {
            setSortBy(column)
            setSortDir('desc')
        }
    }

    const handleFilterByValue = (column: string, value: any) => {
        setFilters(prev => ({ ...prev, [column]: String(value) }))
        setOffset(0)
    }

    const clearFilters = () => {
        setFilters({})
        setOffset(0)
    }

    const exportCsv = () => {
        if (data.length === 0) return
        const keys = Object.keys(data[0])
        const csv = [
            keys.join(','),
            ...data.map(row => keys.map(k => `"${String(row[k] ?? '')}"`).join(','))
        ].join('\n')
        const blob = new Blob([csv], { type: 'text/csv' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `${activeTab}_${new Date().toISOString().split('T')[0]}.csv`
        a.click()
        URL.revokeObjectURL(url)
    }

    const copyToClipboard = () => {
        if (data.length === 0) return
        const keys = Object.keys(data[0])
        const text = data.map(row => keys.map(k => row[k] ?? '').join('\t')).join('\n')
        navigator.clipboard.writeText(text)
    }

    const columns = data.length > 0 ? Object.keys(data[0]) : []
    const pageCount = Math.ceil(total / limit)
    const currentPage = Math.floor(offset / limit) + 1

    return (
        <>
            <Head>
                <title>Data Explorer - Nexus 2</title>
                <meta name="description" content="Explore trading data" />
                <meta name="viewport" content="width=device-width, initial-scale=1" />
            </Head>

            <main className={styles.main}>
                <header className={styles.header}>
                    <div className={styles.headerLeft}>
                        <h1 className={styles.title}>📊 Data Explorer</h1>
                        <Link href="/" className={styles.navLink}>🏠 Dashboard</Link>
                        <Link href="/warrior" className={styles.navLink}>⚔️ Warrior</Link>
                    </div>
                    <div className={styles.headerRight}>
                        <button onClick={exportCsv} className={styles.btn} disabled={data.length === 0}>
                            📥 Export CSV
                        </button>
                        <button onClick={copyToClipboard} className={styles.btn} disabled={data.length === 0}>
                            📋 Copy
                        </button>
                        <button onClick={fetchData} className={styles.btn} disabled={loading}>
                            {loading ? '...' : '🔄 Refresh'}
                        </button>
                    </div>
                </header>

                {/* Tabs */}
                <div className={styles.tabs}>
                    {(['trade-events', 'warrior-trades', 'nac-trades', 'scan-history'] as TabType[]).map(tab => (
                        <button
                            key={tab}
                            className={`${styles.tab} ${activeTab === tab ? styles.activeTab : ''}`}
                            onClick={() => setActiveTab(tab)}
                        >
                            {tab.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
                        </button>
                    ))}
                </div>

                {/* Filters & Pagination */}
                <div className={styles.controls}>
                    <div className={styles.controlsLeft}>
                        <span>Showing {data.length} of {total}</span>
                        {Object.keys(filters).length > 0 && (
                            <button onClick={clearFilters} className={styles.clearBtn}>
                                ✕ Clear Filters
                            </button>
                        )}
                    </div>
                    <div className={styles.controlsRight}>
                        <select value={limit} onChange={e => { setLimit(Number(e.target.value)); setOffset(0); }}>
                            <option value={25}>25 per page</option>
                            <option value={50}>50 per page</option>
                            <option value={100}>100 per page</option>
                        </select>
                        <button
                            onClick={() => setOffset(Math.max(0, offset - limit))}
                            disabled={offset === 0}
                            className={styles.pageBtn}
                        >
                            ← Prev
                        </button>
                        <span>Page {currentPage} of {pageCount || 1}</span>
                        <button
                            onClick={() => setOffset(offset + limit)}
                            disabled={offset + limit >= total}
                            className={styles.pageBtn}
                        >
                            Next →
                        </button>
                    </div>
                </div>

                {/* Table */}
                <div className={styles.tableContainer}>
                    {loading && data.length === 0 ? (
                        <div className={styles.loading}>Loading...</div>
                    ) : data.length === 0 ? (
                        <div className={styles.empty}>No data found</div>
                    ) : (
                        <table className={styles.table}>
                            <thead>
                                <tr>
                                    {columns.map(col => (
                                        <th
                                            key={col}
                                            onClick={() => handleSort(col)}
                                            className={styles.sortable}
                                        >
                                            {col}
                                            {sortBy === col && (
                                                <span className={styles.sortIndicator}>
                                                    {sortDir === 'asc' ? ' ▲' : ' ▼'}
                                                </span>
                                            )}
                                        </th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody>
                                {data.map((row, i) => (
                                    <tr key={i}>
                                        {columns.map(col => (
                                            <td
                                                key={col}
                                                onClick={() => handleFilterByValue(col, row[col])}
                                                className={styles.clickable}
                                                title="Click to filter by this value"
                                            >
                                                {formatValue(row[col])}
                                            </td>
                                        ))}
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    )}
                </div>
            </main>
        </>
    )
}

function formatValue(val: any): string {
    if (val === null || val === undefined) return '-'
    if (typeof val === 'object') return JSON.stringify(val)
    if (typeof val === 'number') {
        if (Number.isInteger(val)) return val.toString()
        return val.toFixed(2)
    }
    return String(val)
}
