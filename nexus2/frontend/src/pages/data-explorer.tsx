/**
 * Data Explorer Page
 * 
 * Excel-like table viewer for trading data across 4 sources:
 * - Trade Events (audit log)
 * - Warrior Trades (PSM)
 * - NAC Trades (PSM)
 * - Scan History
 * 
 * Features: sortable columns, click-to-filter, pagination, export/copy,
 * column visibility, date filters, number formatting.
 */
import { useState, useEffect, useCallback } from 'react'
import Head from 'next/head'
import Link from 'next/link'
import styles from '@/styles/DataExplorer.module.css'

type TabType = 'trade-events' | 'warrior-trades' | 'nac-trades' | 'scan-history'

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
    const [hiddenColumns, setHiddenColumns] = useState<Set<string>>(new Set())
    const [showColumnMenu, setShowColumnMenu] = useState(false)
    const [dateFrom, setDateFrom] = useState('')
    const [dateTo, setDateTo] = useState('')

    // Updated endpoints - all use /data/ routes with sort/filter support
    const tabEndpoints: Record<TabType, string> = {
        'trade-events': '/api/data/trade-events',
        'warrior-trades': '/api/data/warrior-trades',
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
            // Date filters for scan history
            if (activeTab === 'scan-history') {
                if (dateFrom) params.set('date_from', dateFrom)
                if (dateTo) params.set('date_to', dateTo)
            }
            Object.entries(filters).forEach(([key, value]) => {
                if (value) params.set(key, value)
            })

            const response = await fetch(`${tabEndpoints[activeTab]}?${params}`)
            if (response.ok) {
                const result = await response.json()
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
    }, [activeTab, limit, offset, sortBy, sortDir, filters, dateFrom, dateTo])

    useEffect(() => {
        setOffset(0)
        setFilters({})
        setSortBy('')
        setDateFrom('')
        setDateTo('')
        setHiddenColumns(new Set())
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
        setDateFrom('')
        setDateTo('')
        setOffset(0)
    }

    const toggleColumn = (col: string) => {
        setHiddenColumns(prev => {
            const next = new Set(prev)
            if (next.has(col)) next.delete(col)
            else next.add(col)
            return next
        })
    }

    const exportCsv = () => {
        if (data.length === 0) return
        const visibleCols = allColumns.filter(c => !hiddenColumns.has(c))
        const csv = [
            visibleCols.join(','),
            ...data.map(row => visibleCols.map(k => `"${String(row[k] ?? '')}"`).join(','))
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
        const visibleCols = allColumns.filter(c => !hiddenColumns.has(c))
        const text = data.map(row => visibleCols.map(k => row[k] ?? '').join('\t')).join('\n')
        navigator.clipboard.writeText(text)
    }

    const allColumns = data.length > 0 ? Object.keys(data[0]) : []
    const columns = allColumns.filter(c => !hiddenColumns.has(c))
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
                        <button onClick={() => setShowColumnMenu(!showColumnMenu)} className={styles.btn}>
                            ⚙️ Columns
                        </button>
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

                {/* Column visibility menu */}
                {showColumnMenu && allColumns.length > 0 && (
                    <div className={styles.columnMenu}>
                        <strong>Toggle Columns:</strong>
                        {allColumns.map(col => (
                            <label key={col} className={styles.columnToggle}>
                                <input
                                    type="checkbox"
                                    checked={!hiddenColumns.has(col)}
                                    onChange={() => toggleColumn(col)}
                                />
                                {col}
                            </label>
                        ))}
                    </div>
                )}

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
                        {activeTab === 'scan-history' && (
                            <>
                                <input
                                    type="date"
                                    value={dateFrom}
                                    onChange={e => { setDateFrom(e.target.value); setOffset(0); }}
                                    className={styles.dateInput}
                                    placeholder="From"
                                />
                                <input
                                    type="date"
                                    value={dateTo}
                                    onChange={e => { setDateTo(e.target.value); setOffset(0); }}
                                    className={styles.dateInput}
                                    placeholder="To"
                                />
                            </>
                        )}
                        {(Object.keys(filters).length > 0 || dateFrom || dateTo) && (
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
                            <option value={250}>250 per page</option>
                            <option value={500}>500 per page</option>
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
                                                {formatValue(col, row[col])}
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

function formatValue(column: string, val: any): string {
    if (val === null || val === undefined) return '-'

    // Format timestamps to milliseconds precision
    if (column === 'logged_at' || column.endsWith('_at') || column.endsWith('_time')) {
        if (typeof val === 'string' && val.includes('T')) {
            // Truncate to milliseconds
            const match = val.match(/^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3})/)
            return match ? match[1] : val.split('.')[0]
        }
    }

    // Format gap_percent and rvol with commas
    if (column === 'gap_percent' || column === 'rvol') {
        const num = parseFloat(val)
        if (!isNaN(num)) {
            return num.toLocaleString('en-US', {
                minimumFractionDigits: 1,
                maximumFractionDigits: 2
            })
        }
    }

    // Other numbers
    if (typeof val === 'number') {
        if (Number.isInteger(val) && val >= 1000) {
            return val.toLocaleString('en-US')
        }
        if (!Number.isInteger(val)) {
            return val.toFixed(2)
        }
    }

    if (typeof val === 'object') return JSON.stringify(val)
    return String(val)
}
