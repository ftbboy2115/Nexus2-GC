/**
 * Formatting utilities for Warrior Trading UI
 */

// Currency formatter
const currencyFormatter = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' })

export const formatCurrency = (value: number): string =>
    currencyFormatter.format(value)

export const formatPnL = (value: number): string => {
    const formatted = formatCurrency(Math.abs(value))
    if (value > 0) return `+${formatted}`
    if (value < 0) return `-${formatted}`
    return formatted
}

export const formatFloat = (shares: number | null): string => {
    if (!shares) return '-'
    if (shares >= 1_000_000) return `${(shares / 1_000_000).toFixed(1)}M`
    if (shares >= 1_000) return `${(shares / 1_000).toFixed(0)}K`
    return shares.toString()
}

export const formatTime = (iso: string | null): string => {
    if (!iso) return '-'
    // Ensure ISO string is treated as UTC (append Z if missing)
    const utcIso = iso.endsWith('Z') ? iso : iso + 'Z'
    return new Date(utcIso).toLocaleTimeString('en-US', {
        timeZone: 'America/New_York',
        hour: '2-digit',
        minute: '2-digit'
    }) + ' ET'
}

// Sort configuration type
export type SortConfig = { key: string; dir: 'asc' | 'desc' }

// Generic sort function
export function sortData<T>(data: T[], sortConfig: SortConfig): T[] {
    return [...data].sort((a, b) => {
        const aVal = (a as Record<string, unknown>)[sortConfig.key]
        const bVal = (b as Record<string, unknown>)[sortConfig.key]
        if (aVal == null) return 1
        if (bVal == null) return -1
        if (aVal < bVal) return sortConfig.dir === 'asc' ? -1 : 1
        if (aVal > bVal) return sortConfig.dir === 'asc' ? 1 : -1
        return 0
    })
}

// Toggle sort state
export function toggleSort(
    key: string,
    current: SortConfig,
    setter: React.Dispatch<React.SetStateAction<SortConfig>>
): void {
    if (current.key === key) {
        setter({ key, dir: current.dir === 'asc' ? 'desc' : 'asc' })
    } else {
        setter({ key, dir: 'desc' })
    }
}
