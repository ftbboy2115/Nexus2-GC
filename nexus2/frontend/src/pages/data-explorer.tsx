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
import { useLoading } from '@/components/GlobalLoadingBar'
import {
    DndContext,
    closestCenter,
    KeyboardSensor,
    PointerSensor,
    useSensor,
    useSensors,
    DragEndEvent,
} from '@dnd-kit/core'
import {
    arrayMove,
    SortableContext,
    sortableKeyboardCoordinates,
    horizontalListSortingStrategy,
    useSortable,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
type TabType = 'trade-events' | 'warrior-trades' | 'nac-trades' | 'nac-scans' | 'warrior-scans' | 'catalyst-audits' | 'ai-comparisons' | 'quote-audits' | 'validation-log'

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
    'headline_index', 'confidence',
    // AI comparison columns
    'regex_conf', 'flash_ms',
])

// Columns that should NOT be comma-formatted
const NO_COMMA_COLS = new Set(['id', 'position_id', 'entry_order_id', 'exit_order_id', 'order_id'])

// Per-tab filter state type
interface TabFilterState {
    filters: Record<string, Set<string>>
    dateFrom: string
    dateTo: string
    timeFrom: string
    timeTo: string
    timeWindow: string
    sortBy: string
    sortDir: 'asc' | 'desc'
}

// Props for the sortable header component
interface SortableHeaderProps {
    id: string
    col: string
    isNumeric: boolean
    isSorted: boolean
    sortDir: 'asc' | 'desc'
    tooltip: string
    hasFilter: boolean
    onSort: () => void
    onFilterClick: (e: React.MouseEvent) => void
    children?: React.ReactNode
}

// Sortable header component for drag-and-drop
function SortableHeader({
    id,
    col,
    isNumeric,
    isSorted,
    sortDir,
    tooltip,
    hasFilter,
    onSort,
    onFilterClick,
    children,
}: SortableHeaderProps) {
    const {
        attributes,
        listeners,
        setNodeRef,
        transform,
        transition,
        isDragging,
    } = useSortable({ id })

    const style: React.CSSProperties = {
        transform: CSS.Transform.toString(transform),
        transition,
        opacity: isDragging ? 0.5 : 1,
        cursor: 'grab',
        position: 'relative',
        textAlign: isNumeric ? 'right' : 'left',
    }

    return (
        <th
            ref={setNodeRef}
            style={style}
            className={`${styles.sortable} ${isNumeric ? styles.numericHeader : ''}`}
        >
            <span
                {...attributes}
                {...listeners}
                style={{ cursor: 'grab', marginRight: '4px', opacity: 0.5 }}
                title="Drag to reorder"
            >
                ⋮⋮
            </span>
            <span
                onClick={onSort}
                style={{ cursor: 'pointer' }}
                title={tooltip}
            >
                {col}
                {isSorted && (
                    <span className={styles.sortIndicator}>
                        {sortDir === 'asc' ? ' ▲' : ' ▼'}
                    </span>
                )}
            </span>
            <button
                onClick={onFilterClick}
                className={styles.filterBtn}
                title={`Filter by ${col}`}
                style={{
                    marginLeft: '6px',
                    padding: '2px 5px',
                    fontSize: '11px',
                    background: hasFilter ? '#4caf50' : '#333',
                    border: '1px solid #666',
                    borderRadius: '3px',
                    color: hasFilter ? '#fff' : '#ccc',
                    cursor: 'pointer',
                    fontWeight: 'bold',
                }}
            >
                ▼
            </button>
            {children}
        </th>
    )
}

export default function DataExplorer() {
    const [activeTab, setActiveTab] = useState<TabType>('warrior-scans')
    const [data, setData] = useState<any[]>([])
    const [total, setTotal] = useState(0)
    const [loading, setLoading] = useState(true)
    const [limit, setLimit] = useState(50)
    const [offset, setOffset] = useState(0)
    const [sortBy, setSortBy] = useState('created_at')  // Default sort by timestamp
    const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')
    const [filters, setFilters] = useState<Record<string, Set<string>>>({})
    const [hiddenColumns, setHiddenColumns] = useState<Set<string>>(new Set())
    const [showColumnMenu, setShowColumnMenu] = useState(false)
    const [dateFrom, setDateFrom] = useState('')
    const [dateTo, setDateTo] = useState('')
    const [timeFrom, setTimeFrom] = useState('')  // HH:MM format
    const [timeTo, setTimeTo] = useState('')      // HH:MM format
    const [expandedCell, setExpandedCell] = useState<{ row: number, col: string } | null>(null)
    const [filterDropdownCol, setFilterDropdownCol] = useState<string | null>(null)
    const [filterSearchText, setFilterSearchText] = useState<string>('')  // Live filter text for dropdown
    const [timeWindow, setTimeWindow] = useState<string>('')  // 1h, 4h, 8h, 24h, 7d, or '' for custom

    // Store filter state per tab so each tab has independent filters
    const [tabFilterStates, setTabFilterStates] = useState<Partial<Record<TabType, TabFilterState>>>({})
    const [previousTab, setPreviousTab] = useState<TabType | null>(null)

    // Custom column order per tab (persisted to localStorage)
    const [customColumnOrder, setCustomColumnOrder] = useState<Partial<Record<TabType, string[]>>>(() => {
        if (typeof window !== 'undefined') {
            const saved = localStorage.getItem('dataExplorer_columnOrder')
            return saved ? JSON.parse(saved) : {}
        }
        return {}
    })

    // DnD sensors for drag-and-drop
    const sensors = useSensors(
        useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
        useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
    )

    const tabEndpoints: Record<TabType, string> = {
        'trade-events': '/api/data/trade-events',
        'warrior-trades': '/api/data/warrior-trades',
        'nac-trades': '/api/data/nac-trades',
        'nac-scans': '/api/data/scan-history',
        'warrior-scans': '/api/data/warrior-scan-history',
        'catalyst-audits': '/api/data/catalyst-audits',
        'ai-comparisons': '/api/data/ai-comparisons',
        'quote-audits': '/api/data/quote-audits',
        'validation-log': '/api/data/validation-log',
    }

    // Default sort column per tab - different tabs use different timestamp column names
    const DEFAULT_SORT_COLUMNS: Record<TabType, string> = {
        'warrior-scans': 'timestamp',
        'nac-scans': 'timestamp',
        'catalyst-audits': 'timestamp',
        'ai-comparisons': 'timestamp',
        'trade-events': 'created_at',
        'warrior-trades': 'entry_time',
        'nac-trades': 'entry_time',
        'quote-audits': 'timestamp',
        'validation-log': 'created_at',
    }

    // Column display names and tooltips for clarity
    const COLUMN_TOOLTIPS: Record<string, string> = {
        'regex_result': 'PASS = regex matched a catalyst pattern, FAIL = no match',
        'regex_match_type': 'Pattern that matched: earnings, fda, contract, acquisition, ipo, clinical_advance, or no_match',
        'headline_index': 'Position 1-5 of headlines evaluated for this symbol',
        'confidence': 'Regex tier: 0.9 = primary catalyst (earnings/fda/contract), 0.5 = supportive only, 0.0 = no match. Threshold ≥0.6 to pass.',
        'flash_valid': 'Whether Flash-Lite AI model classified the headline as a valid catalyst',
        'pro_valid': 'Whether Pro AI model classified the headline as a valid catalyst (tiebreaker)',
        'tiebreaker_used': 'True if Regex and Flash-Lite disagreed, requiring Pro model tiebreaker',
        'regex_conf': 'Regex confidence score (0.0-0.9)',
        'flash_ms': 'Flash-Lite model response latency in milliseconds',
        'gap_pct': 'Pre-market gap percentage vs previous close',
        'rvol': 'Relative volume vs 20-day average',
        'score': 'Composite scanner score based on multiple criteria',
    }

    // Preferred column order per tab - ensures stable column positions
    const PREFERRED_COLUMN_ORDER: Record<TabType, string[]> = {
        'warrior-scans': ['timestamp', 'source', 'symbol', 'result', 'gap_pct', 'score', 'rvol', 'float', 'catalyst', 'reason'],
        'nac-scans': ['timestamp', 'symbol', 'result', 'gap_pct', 'rvol', 'volume', 'catalyst', 'reason'],
        'catalyst-audits': ['timestamp', 'symbol', 'regex_result', 'regex_match_type', 'headline_index', 'confidence', 'headline', 'passed'],
        'ai-comparisons': ['timestamp', 'symbol', 'flash_valid', 'pro_valid', 'tiebreaker_used', 'regex_conf', 'flash_ms', 'reason'],
        'trade-events': ['created_at', 'strategy', 'symbol', 'event_type', 'shares', 'metadata'],
        'warrior-trades': ['entry_time', 'symbol', 'status', 'entry_price', 'exit_price', 'stop_price', 'target_price', 'quantity', 'realized_pnl', 'exit_reason', 'trigger_type', 'stop_method', 'is_sim'],
        'nac-trades': ['entry_time', 'symbol', 'status', 'entry_price', 'exit_price', 'stop_price', 'quantity', 'realized_pnl', 'exit_reason'],
        'quote-audits': ['timestamp', 'symbol', 'selected_source', 'alpaca_price', 'fmp_price', 'schwab_price', 'selected_price', 'divergence_pct'],
        'validation-log': ['created_at', 'symbol', 'entry_price', 'entry_trigger', 'expected_target', 'expected_stop', 'entry_confidence', 'ross_entry', 'entry_delta', 'ross_pnl', 'mfe', 'mae', 'realized_pnl', 'target_hit', 'is_sim'],
    }

    const { startLoading, stopLoading } = useLoading()
    const fetchData = useCallback(async () => {
        setLoading(true)
        startLoading()
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
            // Apply all filters (multi-select: send as comma-separated values)
            Object.entries(filters).forEach(([key, valueSet]) => {
                if (valueSet && valueSet.size > 0) {
                    // Convert Set to comma-separated string for backend
                    params.set(key, Array.from(valueSet).join(','))
                }
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
            stopLoading()
        }
    }, [activeTab, limit, offset, sortBy, sortDir, filters, dateFrom, dateTo, timeFrom, timeTo])

    useEffect(() => {
        // Save current tab's filter state before switching
        if (previousTab) {
            setTabFilterStates(prev => ({
                ...prev,
                [previousTab]: {
                    filters,
                    dateFrom,
                    dateTo,
                    timeFrom,
                    timeTo,
                    timeWindow,
                    sortBy,
                    sortDir,
                }
            }))
        }

        // Restore the new tab's filter state or reset to defaults
        const savedState = tabFilterStates[activeTab]
        if (savedState) {
            setFilters(savedState.filters)
            setDateFrom(savedState.dateFrom)
            setDateTo(savedState.dateTo)
            setTimeFrom(savedState.timeFrom)
            setTimeTo(savedState.timeTo)
            setTimeWindow(savedState.timeWindow)
            setSortBy(savedState.sortBy)
            setSortDir(savedState.sortDir)
        } else {
            // Fresh tab - reset to defaults
            setFilters({})
            setDateFrom('')
            setDateTo('')
            setTimeFrom('')
            setTimeTo('')
            setTimeWindow('')
            setSortBy(DEFAULT_SORT_COLUMNS[activeTab])
            setSortDir('desc')
        }

        // Always reset these on tab switch
        setOffset(0)
        setHiddenColumns(new Set())
        setExpandedCell(null)
        setFilterDropdownCol(null)

        // Track previous tab for next switch
        setPreviousTab(activeTab)
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

    // Toggle a single value in the multi-select filter
    const toggleFilterValue = (column: string, value: string, allValues: string[]) => {
        setFilters(prev => {
            const currentSet = prev[column] ? new Set(prev[column]) : new Set(allValues)
            if (currentSet.has(value)) {
                currentSet.delete(value)
            } else {
                currentSet.add(value)
            }
            // If all selected, remove the filter entirely (no filtering)
            if (currentSet.size === allValues.length) {
                const next = { ...prev }
                delete next[column]
                return next
            }
            // If none selected, keep empty set (show nothing)
            return { ...prev, [column]: currentSet }
        })
        setOffset(0)
    }

    // Select All / Deselect All toggle
    const toggleSelectAll = (column: string, allValues: string[], selectAll: boolean) => {
        setFilters(prev => {
            if (selectAll) {
                // Select all = remove filter (show everything)
                const next = { ...prev }
                delete next[column]
                return next
            } else {
                // Deselect all = empty set (show nothing)
                return { ...prev, [column]: new Set<string>() }
            }
        })
        setOffset(0)
    }

    // Check if a value is selected (not filtered out)
    const isValueSelected = (column: string, value: string, allValues: string[]): boolean => {
        const filterSet = filters[column]
        if (!filterSet) return true // No filter = all selected
        return filterSet.has(value)
    }

    // Check if all values are selected (no filter active)
    const isAllSelected = (column: string): boolean => {
        return !filters[column]
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
        // Use ET for dates (YYYY-MM-DD) and times (HH:MM)
        const toETDate = (d: Date) => d.toLocaleDateString('en-CA', { timeZone: 'America/New_York' })
        const toETTime = (d: Date) => d.toLocaleTimeString('en-GB', {
            timeZone: 'America/New_York',
            hour: '2-digit',
            minute: '2-digit',
            hour12: false
        })

        setDateFrom(toETDate(fromDate))
        setDateTo(toETDate(now))
        setTimeFrom(toETTime(fromDate))
        setTimeTo(toETTime(now))
        setOffset(0)
    }

    // Date presets - sets date range to specific periods (no time filtering)
    const handleDatePreset = (preset: string) => {
        // Use Eastern Time for date calculations
        const now = new Date()

        // Get date in ET as YYYY-MM-DD using en-CA locale
        const toETDate = (d: Date): string => {
            return d.toLocaleDateString('en-CA', { timeZone: 'America/New_York' })
        }

        const today = toETDate(now)

        // Get Monday of current week (Monday = 1, Sunday = 0)
        const getMonday = (d: Date) => {
            const date = new Date(d)
            const day = date.getDay()
            const diff = date.getDate() - day + (day === 0 ? -6 : 1)
            return new Date(date.setDate(diff))
        }

        switch (preset) {
            case 'today':
                setDateFrom(today)
                setDateTo(today)
                break
            case 'yesterday': {
                const yesterday = new Date(now)
                yesterday.setDate(yesterday.getDate() - 1)
                setDateFrom(toETDate(yesterday))
                setDateTo(toETDate(yesterday))
                break
            }
            case 'this-week': {
                const monday = getMonday(now)
                setDateFrom(toETDate(monday))
                setDateTo(today)
                break
            }
            case 'last-week': {
                const lastMonday = getMonday(now)
                lastMonday.setDate(lastMonday.getDate() - 7)
                const lastSunday = new Date(lastMonday)
                lastSunday.setDate(lastSunday.getDate() + 6)
                setDateFrom(toETDate(lastMonday))
                setDateTo(toETDate(lastSunday))
                break
            }
            default:
                return
        }
        // Clear time filters and time window when using date presets
        setTimeFrom('')
        setTimeTo('')
        setTimeWindow('')
        setOffset(0)
    }

    // Clear only date/time filters (preserve other column filters)
    const clearTimeFilters = () => {
        setDateFrom('')
        setDateTo('')
        setTimeFrom('')
        setTimeTo('')
        setTimeWindow('')
        setOffset(0)
    }

    // Get article URL from catalyst audit row (handles different provider schemas)
    const getArticleUrl = (row: any): string | null => {
        return row.article_url || row.url || null
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

    // Helper to write text to clipboard with fallback for non-HTTPS
    const writeToClipboard = (text: string) => {
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(text)
        } else {
            // Legacy fallback using textarea
            const textarea = document.createElement('textarea')
            textarea.value = text
            textarea.style.position = 'fixed'
            textarea.style.opacity = '0'
            document.body.appendChild(textarea)
            textarea.select()
            document.execCommand('copy')
            document.body.removeChild(textarea)
        }
    }

    const copyToClipboard = () => {
        if (data.length === 0) return
        const visibleCols = allColumns.filter(c => !hiddenColumns.has(c))
        // Include headers
        const header = visibleCols.join('\t')
        const rows = data.map(row => visibleCols.map(k => row[k] ?? '').join('\t')).join('\n')
        writeToClipboard(`${header}\n${rows}`)
    }

    const copyAsJson = () => {
        if (data.length === 0) return
        const visibleCols = allColumns.filter(c => !hiddenColumns.has(c))
        // Filter each row to only include visible columns
        const filtered = data.map(row => {
            const obj: Record<string, any> = {}
            visibleCols.forEach(col => { obj[col] = row[col] ?? null })
            return obj
        })
        writeToClipboard(JSON.stringify(filtered, null, 2))
    }

    // Derive columns from ALL rows (not just first) to avoid missing columns
    // Then sort by preferred order for this tab - unknown columns go at the end
    const rawColumns = data.length > 0
        ? Array.from(new Set(data.flatMap(row => Object.keys(row))))
        : []

    // Use custom order if set, otherwise use default preferred order
    const customOrder = customColumnOrder[activeTab]
    const preferredOrder = customOrder || PREFERRED_COLUMN_ORDER[activeTab] || []

    const allColumns = rawColumns.sort((a, b) => {
        const aIdx = preferredOrder.indexOf(a)
        const bIdx = preferredOrder.indexOf(b)
        // Known columns come before unknown
        if (aIdx >= 0 && bIdx >= 0) return aIdx - bIdx
        if (aIdx >= 0) return -1
        if (bIdx >= 0) return 1
        // Both unknown: sort alphabetically
        return a.localeCompare(b)
    })
    const columns = allColumns.filter(c => !hiddenColumns.has(c))
    const pageCount = Math.ceil(total / limit)
    const currentPage = Math.floor(offset / limit) + 1
    const hasFilters = Object.keys(filters).length > 0 || dateFrom || dateTo

    // Handle drag-end for column reordering
    const handleDragEnd = (event: DragEndEvent) => {
        const { active, over } = event
        if (!over || active.id === over.id) return

        const oldIndex = columns.indexOf(active.id as string)
        const newIndex = columns.indexOf(over.id as string)

        if (oldIndex !== -1 && newIndex !== -1) {
            const newOrder = arrayMove(columns, oldIndex, newIndex)
            // Merge with hidden columns to preserve full order
            const fullOrder = [...newOrder, ...Array.from(hiddenColumns)]

            setCustomColumnOrder(prev => {
                const updated = { ...prev, [activeTab]: fullOrder }
                localStorage.setItem('dataExplorer_columnOrder', JSON.stringify(updated))
                return updated
            })
        }
    }

    // Reset column order to default for current tab
    const resetColumnOrder = () => {
        setCustomColumnOrder(prev => {
            const updated = { ...prev }
            delete updated[activeTab]
            localStorage.setItem('dataExplorer_columnOrder', JSON.stringify(updated))
            return updated
        })
    }

    // Tabs that have backend /distinct endpoints for comprehensive filtering
    const DISTINCT_ENDPOINT_TABS: Record<string, string> = {
        'warrior-scans': '/api/data/warrior-scan-history/distinct',
        'catalyst-audits': '/api/data/catalyst-audits/distinct',
        'ai-comparisons': '/api/data/ai-comparisons/distinct',
    }

    // State to cache distinct values from backend
    const [distinctValues, setDistinctValues] = useState<Record<string, string[]>>({})
    const [loadingDistinct, setLoadingDistinct] = useState<string | null>(null)

    // Fetch distinct values from backend when filter dropdown opens
    const fetchDistinctValues = async (col: string) => {
        const endpoint = DISTINCT_ENDPOINT_TABS[activeTab]
        if (!endpoint) {
            // No backend endpoint - fall back to current page data
            return null
        }

        setLoadingDistinct(col)
        try {
            const res = await fetch(`${endpoint}?column=${col}`)
            if (res.ok) {
                const result = await res.json()
                setDistinctValues(prev => ({
                    ...prev,
                    [`${activeTab}-${col}`]: result.values || []
                }))
            }
        } catch (e) {
            console.error('Failed to fetch distinct values:', e)
        } finally {
            setLoadingDistinct(null)
        }
    }

    // Get unique values for a column (for Excel-style filter dropdowns)
    // Uses backend data if available, otherwise falls back to current page
    const getUniqueValues = (col: string): string[] => {
        const cacheKey = `${activeTab}-${col}`
        const cached = distinctValues[cacheKey]
        if (cached && cached.length > 0) {
            return cached
        }

        // Fall back to current page data
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
                        <button onClick={copyAsJson} className={styles.btn} disabled={data.length === 0} title="Copy as JSON">
                            { } JSON
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
                        { id: 'catalyst-audits', label: 'Catalyst Audits', tooltip: 'Regex-based headline classification (Tier 0.9/0.5/0.0). Shows which headlines matched catalyst patterns like earnings, FDA approvals, etc.' },
                        { id: 'ai-comparisons', label: 'AI Comparisons', tooltip: 'Side-by-side comparison of Regex vs Flash-Lite vs Pro catalyst classification.' },
                        { id: 'trade-events', label: 'Trade Events', tooltip: 'Event stream from nexus.db. Every state transition: ENTRY, FILL, EXIT, STOP_RAISED, etc.' },
                        { id: 'warrior-trades', label: 'Warrior Trades', tooltip: 'Position lifecycle from warrior.db. One row per trade: entry → exit with P&L.' },
                        { id: 'nac-trades', label: 'Nac Trades', tooltip: 'NAC position lifecycle from nac.db. One row per trade with full position data.' },
                        { id: 'quote-audits', label: 'Quote Audits', tooltip: 'Cross-provider quote divergence audit. Shows when Alpaca/FMP/Schwab/Polygon disagree.' },
                        { id: 'validation-log', label: 'Validation Log', tooltip: 'Entry validation audit trail. Compares bot entry vs Ross entry, tracks MFE/MAE and target/stop outcomes.' },
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
                        <div style={{ display: 'flex', alignItems: 'center', gap: '2px' }}>
                            <input
                                type="time"
                                value={timeFrom}
                                onChange={e => { setTimeFrom(e.target.value); setTimeWindow(''); setOffset(0); }}
                                className={styles.dateInput}
                                title="From time (optional)"
                                style={{ width: '90px' }}
                            />
                            {timeFrom && (
                                <button
                                    onClick={() => { setTimeFrom(''); setOffset(0); }}
                                    style={{
                                        padding: '2px 5px',
                                        fontSize: '10px',
                                        background: '#666',
                                        border: 'none',
                                        borderRadius: '3px',
                                        color: '#fff',
                                        cursor: 'pointer',
                                        lineHeight: 1
                                    }}
                                    title="Clear from time"
                                >✕</button>
                            )}
                        </div>
                        <span style={{ color: '#888' }}>→</span>
                        <input
                            type="date"
                            value={dateTo}
                            onChange={e => { setDateTo(e.target.value); setTimeWindow(''); setOffset(0); }}
                            className={styles.dateInput}
                            title="To date"
                        />
                        <div style={{ display: 'flex', alignItems: 'center', gap: '2px' }}>
                            <input
                                type="time"
                                value={timeTo}
                                onChange={e => { setTimeTo(e.target.value); setTimeWindow(''); setOffset(0); }}
                                className={styles.dateInput}
                                title="To time (optional)"
                                style={{ width: '90px' }}
                            />
                            {timeTo && (
                                <button
                                    onClick={() => { setTimeTo(''); setOffset(0); }}
                                    style={{
                                        padding: '2px 5px',
                                        fontSize: '10px',
                                        background: '#666',
                                        border: 'none',
                                        borderRadius: '3px',
                                        color: '#fff',
                                        cursor: 'pointer',
                                        lineHeight: 1
                                    }}
                                    title="Clear to time"
                                >✕</button>
                            )}
                        </div>
                        {/* Date presets */}
                        <div style={{ display: 'flex', gap: '4px', marginLeft: '8px' }}>
                            <button
                                onClick={() => handleDatePreset('today')}
                                className={styles.btn}
                                style={{ padding: '4px 8px', fontSize: '11px' }}
                                title="Show today only"
                            >
                                Today
                            </button>
                            <button
                                onClick={() => handleDatePreset('yesterday')}
                                className={styles.btn}
                                style={{ padding: '4px 8px', fontSize: '11px' }}
                                title="Show yesterday only"
                            >
                                Yesterday
                            </button>
                            <button
                                onClick={() => handleDatePreset('this-week')}
                                className={styles.btn}
                                style={{ padding: '4px 8px', fontSize: '11px' }}
                                title="Show this week (Mon-Today)"
                            >
                                This Week
                            </button>
                            <button
                                onClick={() => handleDatePreset('last-week')}
                                className={styles.btn}
                                style={{ padding: '4px 8px', fontSize: '11px' }}
                                title="Show last week (Mon-Sun)"
                            >
                                Last Week
                            </button>
                        </div>
                        {/* Clear time button - only shows when time filters are set */}
                        {(timeFrom || timeTo) && (
                            <button
                                onClick={clearTimeFilters}
                                className={styles.btn}
                                style={{ padding: '4px 8px', fontSize: '11px', marginLeft: '4px', background: '#c9302c' }}
                                title="Clear all date/time filters"
                            >
                                ✕ Time
                            </button>
                        )}
                        {activeTab === 'warrior-trades' && (
                            <select
                                value={filters.is_sim ? Array.from(filters.is_sim)[0] || '' : ''}
                                onChange={e => {
                                    const val = e.target.value;
                                    setFilters(prev => {
                                        if (!val) {
                                            const next = { ...prev };
                                            delete next.is_sim;
                                            return next;
                                        }
                                        return { ...prev, is_sim: new Set([val]) };
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
                        {Object.entries(filters).map(([key, valueSet]) => {
                            const valuesArray = Array.from(valueSet)
                            const displayValue = valuesArray.length > 2
                                ? `${valuesArray.slice(0, 2).join(', ')} (+${valuesArray.length - 2})`
                                : valuesArray.join(', ')
                            // Check if this is a symbol filter with single value (for TradingView link)
                            const isSymbolFilter = key.toLowerCase() === 'symbol' && valuesArray.length === 1

                            return (
                                <span key={key} className={styles.filterTag}>
                                    {key}: {displayValue.length > 30 ? displayValue.slice(0, 30) + '...' : displayValue}
                                    {isSymbolFilter && (
                                        <button
                                            onClick={() => {
                                                // Open TradingView chart in new fullscreen window
                                                const width = window.screen.width
                                                const height = window.screen.height
                                                window.open(
                                                    `https://www.tradingview.com/chart/D7F9NNnO/?symbol=${valuesArray[0]}`,
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
                            <DndContext
                                sensors={sensors}
                                collisionDetection={closestCenter}
                                onDragEnd={handleDragEnd}
                            >
                                <thead>
                                    <tr>
                                        <SortableContext items={columns} strategy={horizontalListSortingStrategy}>
                                            {columns.map(col => (
                                                <SortableHeader
                                                    key={col}
                                                    id={col}
                                                    col={col}
                                                    isNumeric={NUMERIC_COLS.has(col)}
                                                    isSorted={sortBy === col}
                                                    sortDir={sortDir}
                                                    tooltip={COLUMN_TOOLTIPS[col] || ''}
                                                    hasFilter={!!filters[col]}
                                                    onSort={() => handleSort(col)}
                                                    onFilterClick={(e) => {
                                                        e.stopPropagation()
                                                        if (filterDropdownCol === col) {
                                                            setFilterDropdownCol(null)
                                                        } else {
                                                            setFilterDropdownCol(col)
                                                            setFilterSearchText('')
                                                            fetchDistinctValues(col)
                                                        }
                                                    }}
                                                >
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
                                                            {/* Search input */}
                                                            <div style={{ position: 'relative', marginBottom: '6px' }}>
                                                                <input
                                                                    type="text"
                                                                    placeholder={`Search ${col}...`}
                                                                    value={filterSearchText}
                                                                    onChange={(e) => setFilterSearchText(e.target.value)}
                                                                    onClick={(e) => e.stopPropagation()}
                                                                    style={{
                                                                        width: '100%',
                                                                        padding: '6px 8px',
                                                                        background: '#2a2a2a',
                                                                        border: '1px solid #555',
                                                                        borderRadius: '3px',
                                                                        color: '#fff',
                                                                        fontSize: '12px',
                                                                    }}
                                                                    autoFocus
                                                                />
                                                            </div>
                                                            {/* Select All checkbox */}
                                                            {(() => {
                                                                const allValues = getUniqueValues(col)
                                                                const filteredValues = allValues.filter(val =>
                                                                    !filterSearchText || val.toLowerCase().includes(filterSearchText.toLowerCase())
                                                                )
                                                                const allSelected = isAllSelected(col)
                                                                return (
                                                                    <>
                                                                        <label
                                                                            style={{
                                                                                display: 'flex',
                                                                                alignItems: 'center',
                                                                                padding: '6px 8px',
                                                                                cursor: 'pointer',
                                                                                borderBottom: '1px solid #333',
                                                                                marginBottom: '4px',
                                                                                fontWeight: 'bold',
                                                                            }}
                                                                            onClick={(e) => e.stopPropagation()}
                                                                        >
                                                                            <input
                                                                                type="checkbox"
                                                                                checked={allSelected}
                                                                                onChange={() => toggleSelectAll(col, allValues, !allSelected)}
                                                                                style={{ marginRight: '8px', accentColor: '#4dabf7' }}
                                                                            />
                                                                            (Select All)
                                                                        </label>
                                                                        {/* Individual value checkboxes */}
                                                                        {filteredValues.slice(0, 50).map(val => (
                                                                            <label
                                                                                key={val}
                                                                                style={{
                                                                                    display: 'flex',
                                                                                    alignItems: 'center',
                                                                                    padding: '4px 8px',
                                                                                    cursor: 'pointer',
                                                                                    borderRadius: '3px',
                                                                                }}
                                                                                onClick={(e) => e.stopPropagation()}
                                                                                onMouseEnter={(e) => (e.currentTarget.style.background = '#333')}
                                                                                onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
                                                                            >
                                                                                <input
                                                                                    type="checkbox"
                                                                                    checked={isValueSelected(col, val, allValues)}
                                                                                    onChange={() => toggleFilterValue(col, val, allValues)}
                                                                                    style={{ marginRight: '8px', accentColor: '#4dabf7' }}
                                                                                />
                                                                                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={val}>
                                                                                    {val.length > 30 ? val.slice(0, 30) + '...' : val}
                                                                                </span>
                                                                            </label>
                                                                        ))}
                                                                        {filteredValues.length > 50 && (
                                                                            <div style={{ padding: '4px 8px', color: '#888', fontSize: '11px' }}>
                                                                                ...and {filteredValues.length - 50} more
                                                                            </div>
                                                                        )}
                                                                    </>
                                                                )
                                                            })()}
                                                        </div>
                                                    )}
                                                </SortableHeader>
                                            ))}
                                        </SortableContext>
                                    </tr>
                                </thead>
                            </DndContext>
                            <tbody>
                                {data.map((row, i) => (
                                    <tr key={i}>
                                        {columns.map(col => {
                                            const rawVal = row[col]
                                            const displayVal = formatValue(col, rawVal)
                                            const fullVal = typeof rawVal === 'object' ? JSON.stringify(rawVal, null, 2) : String(rawVal ?? '')
                                            const isExpanded = expandedCell?.row === i && expandedCell?.col === col
                                            const isTruncated = fullVal.length > 50

                                            // Special handling for headline column in catalyst-audits: make clickable if URL exists
                                            const isHeadlineWithUrl = activeTab === 'catalyst-audits' && col === 'headline' && getArticleUrl(row)
                                            const articleUrl = isHeadlineWithUrl ? getArticleUrl(row) : null

                                            return (
                                                <td
                                                    key={col}
                                                    className={`${styles.clickable} ${NUMERIC_COLS.has(col) ? styles.numeric : ''}`}
                                                    title={fullVal}
                                                    onClick={(e) => {
                                                        // If clicking on a headline link, let the anchor handle it
                                                        if (isHeadlineWithUrl && (e.target as HTMLElement).tagName === 'A') {
                                                            return
                                                        }
                                                        if (e.shiftKey && isTruncated) {
                                                            setExpandedCell(isExpanded ? null : { row: i, col })
                                                        } else {
                                                            // Click on cell = filter to show only this value
                                                            const clickedVal = rawVal === null || rawVal === undefined || rawVal === '' ? '(empty)' : String(rawVal)
                                                            setFilters(prev => ({ ...prev, [col]: new Set([clickedVal]) }))
                                                            setOffset(0)
                                                        }
                                                    }}
                                                >
                                                    {isExpanded ? (
                                                        <pre className={styles.expandedCell}>{fullVal}</pre>
                                                    ) : isHeadlineWithUrl ? (
                                                        <a
                                                            href={articleUrl!}
                                                            target="_blank"
                                                            rel="noopener noreferrer"
                                                            style={{
                                                                color: '#4dabf7',
                                                                textDecoration: 'underline',
                                                                display: 'inline-flex',
                                                                alignItems: 'center',
                                                                gap: '4px',
                                                            }}
                                                            title={`Open article: ${fullVal}`}
                                                            onClick={(e) => e.stopPropagation()}
                                                        >
                                                            {displayVal} <span style={{ fontSize: '10px' }}>↗</span>
                                                        </a>
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
