/**
 * Data Explorer Page
 * 
 * Excel-like table viewer for trading data across 4 sources:
 * - Trade Events (audit log)
 * - Warrior Trades (PSM)
 * - NAC Trades (PSM)
 * - Scan History
 * 
 * Features: sortable columns, click-to-filter (multiple), pagination, export/copy,
 * column visibility, date filters, number formatting, full cell tooltips.
 */
import { useState, useEffect, useCallback } from 'react'
import Head from 'next/head'
import Link from 'next/link'
import styles from '@/styles/DataExplorer.module.css'
type TabType = 'trade-events' | 'warrior-trades' | 'nac-trades' | 'nac-scans' | 'warrior-scans' | 'catalyst-audits' | 'ai-comparisons' | 'quote-audits'

// Columns that are numeric for right-alignment
const NUMERIC_COLS = new Set([
    'entry_price', 'exit_price', 'stop_price', 'target_price', 'realized_pnl',
    'quantity', 'remaining_quantity', 'gap_percent', 'rvol', 'score', 'shares',
    'price', 'fill_price', 'pnl', 'entry_quote', 'exit_quote', 'slippage_cents',
    'divergence_pct', 'alpaca_price', 'fmp_price', 'schwab_price', 'selected_price'
])

// Columns that should NOT be comma-formatted
const NO_COMMA_COLS = new Set(['id', 'position_id', 'entry_order_id', 'exit_order_id', 'order_id'])

export default function DataExplorer() {
    const [activeTab, setActiveTab] = useState<TabType>('warrior-scans')
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
    const [expandedCell, setExpandedCell] = useState<{ row: number, col: string } | null>(null)
    const [filterDropdownCol, setFilterDropdownCol] = useState<string | null>(null)

    const tabEndpoints: Record<TabType, string> = {
        'trade-events': '/api/data/trade-events',
        'warrior-trades': '/api/data/warrior-trades',
        'nac-trades': '/api/data/nac-trades',
        'nac-scans': '/api/data/scan-history',
        'warrior-scans': '/api/data/warrior-scan-history',
        'catalyst-audits': '/api/data/catalyst-audits',
        'ai-comparisons': '/api/data/ai-comparisons',
        'quote-audits': '/api/data/quote-audits',
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
            // Date filters for all tabs
            if (dateFrom) params.set('date_from', dateFrom)
            if (dateTo) params.set('date_to', dateTo)
            // Apply all filters
            Object.entries(filters).forEach(([key, value]) => {
                if (value) params.set(key, value)
            })

            const response = await fetch(`${tabEndpoints[activeTab]}?${params}`)
            if (response.ok) {
                const result = await response.json()
                const items = result.trades || result.events || result.entries || result.audits || result || []
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
        setExpandedCell(null)
        setFilterDropdownCol(null)
    }, [activeTab])

    useEffect(() => {
        fetchData()
    }, [fetchData])

    // Close filter dropdown when clicking outside
    useEffect(() => {
        if (!filterDropdownCol) return
        const handleClickOutside = () => setFilterDropdownCol(null)
        document.addEventListener('click', handleClickOutside)
        return () => document.removeEventListener('click', handleClickOutside)
    }, [filterDropdownCol])

    const handleSort = (column: string) => {
        if (sortBy === column) {
            setSortDir(sortDir === 'asc' ? 'desc' : 'asc')
        } else {
            setSortBy(column)
            setSortDir('desc')
        }
    }

    // Accumulate filters instead of replacing
    const handleFilterByValue = (column: string, value: any) => {
        // Use special marker for empty/null values
        if (value === null || value === undefined || value === '' || value === '-' || value === 'null') {
            setFilters(prev => ({ ...prev, [column]: '__EMPTY__' }))
        } else {
            setFilters(prev => ({ ...prev, [column]: String(value) }))
        }
        setOffset(0)
    }

    const removeFilter = (column: string) => {
        setFilters(prev => {
            const next = { ...prev }
            delete next[column]
            return next
        })
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

    // Derive columns from ALL rows (not just first) to avoid missing columns
    const allColumns = data.length > 0
        ? Array.from(new Set(data.flatMap(row => Object.keys(row))))
        : []
    const columns = allColumns.filter(c => !hiddenColumns.has(c))
    const pageCount = Math.ceil(total / limit)
    const currentPage = Math.floor(offset / limit) + 1
    const hasFilters = Object.keys(filters).length > 0 || dateFrom || dateTo

    // Get unique values for a column (for Excel-style filter dropdowns)
    const getUniqueValues = (col: string): string[] => {
        const values = new Set<string>()
        data.forEach(row => {
            const val = row[col]
            if (val === null || val === undefined || val === '') {
                values.add('(empty)')
            } else {
                values.add(String(val))
            }
        })
        return Array.from(values).sort()
    }

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
                    {(['warrior-scans', 'nac-scans', 'catalyst-audits', 'ai-comparisons', 'trade-events', 'warrior-trades', 'nac-trades', 'quote-audits'] as TabType[]).map(tab => (
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
                        <input
                            type="date"
                            value={dateFrom}
                            onChange={e => { setDateFrom(e.target.value); setOffset(0); }}
                            className={styles.dateInput}
                            title="From date"
                        />
                        <input
                            type="date"
                            value={dateTo}
                            onChange={e => { setDateTo(e.target.value); setOffset(0); }}
                            className={styles.dateInput}
                            title="To date"
                        />
                        {activeTab === 'warrior-trades' && (
                            <select
                                value={filters.is_sim || ''}
                                onChange={e => {
                                    const val = e.target.value;
                                    setFilters(prev => {
                                        if (!val) {
                                            const { is_sim, ...rest } = prev;
                                            return rest;
                                        }
                                        return { ...prev, is_sim: val };
                                    });
                                    setOffset(0);
                                }}
                                className={styles.dateInput}
                                title="Filter by SIM/LIVE"
                            >
                                <option value="">All Trades</option>
                                <option value="false">🔴 LIVE Only</option>
                                <option value="true">🧪 SIM Only</option>
                                <option value="null">❓ Unknown</option>
                            </select>
                        )}
                        {hasFilters && (
                            <button onClick={clearFilters} className={styles.clearBtn}>
                                ✕ Clear All
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

                {/* Active filters display */}
                {Object.keys(filters).length > 0 && (
                    <div className={styles.filterTags}>
                        {Object.entries(filters).map(([key, value]) => (
                            <span key={key} className={styles.filterTag}>
                                {key}: {value.length > 20 ? value.slice(0, 20) + '...' : value}
                                <button onClick={() => removeFilter(key)} className={styles.filterRemove}>×</button>
                            </span>
                        ))}
                    </div>
                )}

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
                                            className={`${styles.sortable} ${NUMERIC_COLS.has(col) ? styles.numericHeader : ''}`}
                                            style={{ position: 'relative' }}
                                        >
                                            <span onClick={() => handleSort(col)} style={{ cursor: 'pointer' }}>
                                                {col}
                                                {sortBy === col && (
                                                    <span className={styles.sortIndicator}>
                                                        {sortDir === 'asc' ? ' ▲' : ' ▼'}
                                                    </span>
                                                )}
                                            </span>
                                            <button
                                                onClick={(e) => {
                                                    e.stopPropagation()
                                                    setFilterDropdownCol(filterDropdownCol === col ? null : col)
                                                }}
                                                className={styles.filterBtn}
                                                title={`Filter by ${col}`}
                                                style={{
                                                    marginLeft: '6px',
                                                    padding: '2px 5px',
                                                    fontSize: '11px',
                                                    background: filters[col] ? '#4caf50' : '#333',
                                                    border: '1px solid #666',
                                                    borderRadius: '3px',
                                                    color: filters[col] ? '#fff' : '#ccc',
                                                    cursor: 'pointer',
                                                    fontWeight: 'bold',
                                                }}
                                            >
                                                ▼
                                            </button>
                                            {filterDropdownCol === col && (
                                                <div
                                                    className={styles.filterDropdown}
                                                    style={{
                                                        position: 'absolute',
                                                        top: '100%',
                                                        left: 0,
                                                        zIndex: 1000,
                                                        background: '#1e1e1e',
                                                        border: '1px solid #444',
                                                        borderRadius: '4px',
                                                        padding: '8px',
                                                        minWidth: '150px',
                                                        maxHeight: '300px',
                                                        overflowY: 'auto',
                                                        boxShadow: '0 4px 12px rgba(0,0,0,0.5)',
                                                    }}
                                                    onClick={(e) => e.stopPropagation()}
                                                >
                                                    <button
                                                        onClick={() => {
                                                            removeFilter(col)
                                                            setFilterDropdownCol(null)
                                                        }}
                                                        style={{
                                                            width: '100%',
                                                            padding: '6px',
                                                            marginBottom: '8px',
                                                            background: '#333',
                                                            border: 'none',
                                                            borderRadius: '3px',
                                                            color: '#fff',
                                                            cursor: 'pointer',
                                                        }}
                                                    >
                                                        Clear Filter
                                                    </button>
                                                    {getUniqueValues(col).map(val => (
                                                        <div
                                                            key={val}
                                                            onClick={() => {
                                                                handleFilterByValue(col, val === '(empty)' ? '' : val)
                                                                setFilterDropdownCol(null)
                                                            }}
                                                            style={{
                                                                padding: '6px 8px',
                                                                cursor: 'pointer',
                                                                borderRadius: '3px',
                                                                background: filters[col] === val ? '#4caf50' : 'transparent',
                                                                whiteSpace: 'nowrap',
                                                                overflow: 'hidden',
                                                                textOverflow: 'ellipsis',
                                                            }}
                                                            title={val}
                                                            onMouseEnter={(e) => (e.currentTarget.style.background = '#333')}
                                                            onMouseLeave={(e) => (e.currentTarget.style.background = filters[col] === val ? '#4caf50' : 'transparent')}
                                                        >
                                                            {val.length > 30 ? val.slice(0, 30) + '...' : val}
                                                        </div>
                                                    ))}
                                                </div>
                                            )}
                                        </th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody>
                                {data.map((row, i) => (
                                    <tr key={i}>
                                        {columns.map(col => {
                                            const rawVal = row[col]
                                            const displayVal = formatValue(col, rawVal)
                                            const fullVal = typeof rawVal === 'object' ? JSON.stringify(rawVal, null, 2) : String(rawVal ?? '')
                                            const isExpanded = expandedCell?.row === i && expandedCell?.col === col
                                            const isTruncated = fullVal.length > 50

                                            return (
                                                <td
                                                    key={col}
                                                    className={`${styles.clickable} ${NUMERIC_COLS.has(col) ? styles.numeric : ''}`}
                                                    title={fullVal}
                                                    onClick={(e) => {
                                                        if (e.shiftKey && isTruncated) {
                                                            setExpandedCell(isExpanded ? null : { row: i, col })
                                                        } else {
                                                            handleFilterByValue(col, rawVal)
                                                        }
                                                    }}
                                                >
                                                    {isExpanded ? (
                                                        <pre className={styles.expandedCell}>{fullVal}</pre>
                                                    ) : displayVal}
                                                </td>
                                            )
                                        })}
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

    // Never format ID columns with commas
    if (NO_COMMA_COLS.has(column)) {
        return String(val)
    }

    // Format timestamps - convert UTC to EST
    if (column === 'logged_at' || column.endsWith('_at') || column.endsWith('_time') || column === 'timestamp') {
        const strVal = String(val)
        // Handle ISO format (contains 'T') or space-separated (YYYY-MM-DD HH:MM:SS)
        if (strVal.includes('T') || /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}/.test(strVal)) {
            try {
                // Normalize to ISO format if space-separated
                const isoVal = strVal.includes('T') ? strVal : strVal.replace(' ', 'T')
                // Parse as UTC, display in EST
                const date = new Date(isoVal.endsWith('Z') ? isoVal : isoVal + 'Z')
                return date.toLocaleString('en-US', {
                    timeZone: 'America/New_York',
                    year: 'numeric',
                    month: '2-digit',
                    day: '2-digit',
                    hour: '2-digit',
                    minute: '2-digit',
                    second: '2-digit',
                    hour12: false
                })
            } catch {
                return strVal.split('.')[0]
            }
        }
    }

    // Format gap_percent and rvol with commas and decimals
    if (column === 'gap_percent' || column === 'rvol') {
        const num = parseFloat(val)
        if (!isNaN(num)) {
            return num.toLocaleString('en-US', {
                minimumFractionDigits: 1,
                maximumFractionDigits: 2
            })
        }
    }

    // Other numbers - only add commas if >= 1000 and not an ID
    if (typeof val === 'number') {
        if (Number.isInteger(val) && val >= 1000) {
            return val.toLocaleString('en-US')
        }
        if (!Number.isInteger(val)) {
            return val.toFixed(2)
        }
        return String(val)
    }

    // Objects - show as JSON but truncate
    if (typeof val === 'object') {
        const json = JSON.stringify(val)
        return json.length > 50 ? json.slice(0, 47) + '...' : json
    }

    return String(val)
}
