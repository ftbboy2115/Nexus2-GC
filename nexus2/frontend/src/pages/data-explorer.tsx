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
    // Trade columns
    'entry_price', 'exit_price', 'stop_price', 'target_price', 'realized_pnl',
    'quantity', 'remaining_quantity', 'shares',
    'price', 'fill_price', 'pnl', 'entry_quote', 'exit_quote', 'slippage_cents',
    // Quote audit columns
    'divergence_pct', 'alpaca_price', 'fmp_price', 'schwab_price', 'selected_price',
    // Scan columns (warrior/nac)
    'gap_percent', 'gap_pct', 'rvol', 'score',
    // Catalyst audit columns
    'headline_num', 'confidence',
    // AI comparison columns
    'regex_conf', 'flash_ms',
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
    const [sortBy, setSortBy] = useState('created_at')  // Default sort by timestamp
    const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')
    const [filters, setFilters] = useState<Record<string, string>>({})
    const [hiddenColumns, setHiddenColumns] = useState<Set<string>>(new Set())
    const [showColumnMenu, setShowColumnMenu] = useState(false)
    const [dateFrom, setDateFrom] = useState('')
    const [dateTo, setDateTo] = useState('')
    const [timeFrom, setTimeFrom] = useState('')  // HH:MM format
    const [timeTo, setTimeTo] = useState('')      // HH:MM format
    const [expandedCell, setExpandedCell] = useState<{ row: number, col: string } | null>(null)
    const [filterDropdownCol, setFilterDropdownCol] = useState<string | null>(null)
    const [timeWindow, setTimeWindow] = useState<string>('')  // 1h, 4h, 8h, 24h, 7d, or '' for custom

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
            // Always set sort params (default to created_at desc for all tabs)
            params.set('sort_by', sortBy || 'created_at')
            params.set('sort_dir', sortDir)
            // Date and time filters for all tabs
            if (dateFrom) params.set('date_from', dateFrom)
            if (dateTo) params.set('date_to', dateTo)
            if (timeFrom) params.set('time_from', timeFrom)
            if (timeTo) params.set('time_to', timeTo)
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
    }, [activeTab, limit, offset, sortBy, sortDir, filters, dateFrom, dateTo, timeFrom, timeTo])

    useEffect(() => {
        // When switching tabs, reset tab-specific state but PRESERVE date/time filters
        // This allows investigating a trade's lifecycle across different tabs
        setOffset(0)
        // Only reset column-specific filters, NOT date/time/symbol filters
        setFilters(prev => {
            // Keep symbol filter if it exists - commonly used across tabs
            const result: Record<string, string> = {}
            if (prev.symbol) result.symbol = prev.symbol
            return result
        })
        setSortBy('created_at')  // Reset to default sort
        // PRESERVE: dateFrom, dateTo, timeFrom, timeTo, timeWindow
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
        setTimeFrom('')
        setTimeTo('')
        setTimeWindow('')
        setOffset(0)
    }

    // Time window filter - sets dateFrom/dateTo AND timeFrom/timeTo
    const handleTimeWindow = (window: string) => {
        setTimeWindow(window)
        if (!window) {
            // Custom - clear auto-dates, let user set manually
            return
        }
        const now = new Date()
        let fromDate: Date
        switch (window) {
            case '1h':
                fromDate = new Date(now.getTime() - 60 * 60 * 1000)
                break
            case '4h':
                fromDate = new Date(now.getTime() - 4 * 60 * 60 * 1000)
                break
            case '8h':
                fromDate = new Date(now.getTime() - 8 * 60 * 60 * 1000)
                break
            case '24h':
                fromDate = new Date(now.getTime() - 24 * 60 * 60 * 1000)
                break
            case '7d':
                fromDate = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000)
                break
            default:
                return
        }
        // Set both date and time for precise filtering
        setDateFrom(fromDate.toISOString().split('T')[0])
        setDateTo(now.toISOString().split('T')[0])
        // Extract time in HH:MM format (pad with zeros)
        const formatTime = (d: Date) => {
            const h = String(d.getHours()).padStart(2, '0')
            const m = String(d.getMinutes()).padStart(2, '0')
            return `${h}:${m}`
        }
        setTimeFrom(formatTime(fromDate))
        setTimeTo(formatTime(now))
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
                    {([
                        { id: 'warrior-scans', label: 'Warrior Scans', tooltip: 'Real-time scanner PASS/FAIL decisions from warrior_scan.log. Shows gap%, RVOL, and rejection reasons.' },
                        { id: 'nac-scans', label: 'Nac Scans', tooltip: 'NAC strategy scan history. Shows which stocks passed/failed MA checks.' },
                        { id: 'catalyst-audits', label: 'Catalyst Audits', tooltip: 'Headline classification audit trail. Shows how catalysts were identified and categorized.' },
                        { id: 'ai-comparisons', label: 'AI Comparisons', tooltip: 'Side-by-side comparison of Regex vs Flash-Lite vs Pro catalyst classification.' },
                        { id: 'trade-events', label: 'Trade Events', tooltip: 'Event stream from nexus.db. Every state transition: ENTRY, FILL, EXIT, STOP_RAISED, etc.' },
                        { id: 'warrior-trades', label: 'Warrior Trades', tooltip: 'Position lifecycle from warrior.db. One row per trade: entry → exit with P&L.' },
                        { id: 'nac-trades', label: 'Nac Trades', tooltip: 'NAC position lifecycle from nac.db. One row per trade with full position data.' },
                        { id: 'quote-audits', label: 'Quote Audits', tooltip: 'Cross-provider quote divergence audit. Shows when Alpaca/FMP/Schwab/Polygon disagree.' },
                    ] as { id: TabType; label: string; tooltip: string }[]).map(tab => (
                        <button
                            key={tab.id}
                            className={`${styles.tab} ${activeTab === tab.id ? styles.activeTab : ''}`}
                            onClick={() => setActiveTab(tab.id)}
                            title={tab.tooltip}
                        >
                            {tab.label}
                        </button>
                    ))}
                </div>

                {/* Filters & Pagination */}
                <div className={styles.controls}>
                    <div className={styles.controlsLeft}>
                        <span>Showing {data.length} of {total}</span>
                        <select
                            value={timeWindow}
                            onChange={e => handleTimeWindow(e.target.value)}
                            className={styles.dateInput}
                            title="Quick time filter"
                        >
                            <option value="">Time Window</option>
                            <option value="1h">Last 1 hour</option>
                            <option value="4h">Last 4 hours</option>
                            <option value="8h">Last 8 hours</option>
                            <option value="24h">Last 24 hours</option>
                            <option value="7d">Last 7 days</option>
                        </select>
                        <input
                            type="date"
                            value={dateFrom}
                            onChange={e => { setDateFrom(e.target.value); setTimeWindow(''); setOffset(0); }}
                            className={styles.dateInput}
                            title="From date"
                        />
                        <input
                            type="time"
                            value={timeFrom}
                            onChange={e => { setTimeFrom(e.target.value); setTimeWindow(''); setOffset(0); }}
                            className={styles.dateInput}
                            title="From time (optional)"
                            style={{ width: '90px' }}
                        />
                        <span style={{ color: '#888' }}>→</span>
                        <input
                            type="date"
                            value={dateTo}
                            onChange={e => { setDateTo(e.target.value); setTimeWindow(''); setOffset(0); }}
                            className={styles.dateInput}
                            title="To date"
                        />
                        <input
                            type="time"
                            value={timeTo}
                            onChange={e => { setTimeTo(e.target.value); setTimeWindow(''); setOffset(0); }}
                            className={styles.dateInput}
                            title="To time (optional)"
                            style={{ width: '90px' }}
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
                        {Object.entries(filters).map(([key, value]) => {
                            // Check if this is a symbol filter (for TradingView link)
                            const isSymbolFilter = key.toLowerCase() === 'symbol' && value !== '__EMPTY__'

                            return (
                                <span key={key} className={styles.filterTag}>
                                    {key}: {value.length > 20 ? value.slice(0, 20) + '...' : value}
                                    {isSymbolFilter && (
                                        <button
                                            onClick={() => {
                                                // Open TradingView chart in new fullscreen window
                                                const width = window.screen.width
                                                const height = window.screen.height
                                                window.open(
                                                    `https://www.tradingview.com/chart/D7F9NNnO/?symbol=${value}`,
                                                    '_blank',
                                                    `width=${width},height=${height},left=0,top=0,menubar=no,toolbar=no,location=no,status=no`
                                                )
                                            }}
                                            title="Open TradingView chart"
                                            style={{
                                                marginLeft: '4px',
                                                background: 'transparent',
                                                border: 'none',
                                                cursor: 'pointer',
                                                fontSize: '12px',
                                                padding: '0 2px',
                                            }}
                                        >
                                            📈
                                        </button>
                                    )}
                                    <button onClick={() => removeFilter(key)} className={styles.filterRemove}>×</button>
                                </span>
                            )
                        })}
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
                                                    {/* Search input with inline clear button */}
                                                    <div style={{ position: 'relative', marginBottom: '6px' }}>
                                                        <input
                                                            type="text"
                                                            placeholder={`Search ${col}...`}
                                                            defaultValue={filters[col] || ''}
                                                            onKeyDown={(e) => {
                                                                if (e.key === 'Enter') {
                                                                    const value = (e.target as HTMLInputElement).value.trim()
                                                                    if (value) {
                                                                        handleFilterByValue(col, value)
                                                                    } else {
                                                                        removeFilter(col)
                                                                    }
                                                                    setFilterDropdownCol(null)
                                                                }
                                                            }}
                                                            onClick={(e) => e.stopPropagation()}
                                                            style={{
                                                                width: '100%',
                                                                padding: '6px 28px 6px 8px',
                                                                background: '#2a2a2a',
                                                                border: '1px solid #555',
                                                                borderRadius: '3px',
                                                                color: '#fff',
                                                                fontSize: '12px',
                                                            }}
                                                            autoFocus
                                                        />
                                                        {filters[col] && (
                                                            <button
                                                                onClick={() => {
                                                                    removeFilter(col)
                                                                    setFilterDropdownCol(null)
                                                                }}
                                                                style={{
                                                                    position: 'absolute',
                                                                    right: '4px',
                                                                    top: '50%',
                                                                    transform: 'translateY(-50%)',
                                                                    background: 'transparent',
                                                                    border: 'none',
                                                                    color: '#f44336',
                                                                    cursor: 'pointer',
                                                                    fontSize: '14px',
                                                                    padding: '2px 6px',
                                                                }}
                                                                title="Clear filter"
                                                            >
                                                                ✕
                                                            </button>
                                                        )}
                                                    </div>
                                                    <div style={{ fontSize: '10px', color: '#888', marginBottom: '4px' }}>
                                                        Enter to search, or select:
                                                    </div>
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
