/**
 * SortHeader - Clickable table header for sortable columns
 */
import styles from '@/styles/Warrior.module.css'
import type { SortConfig } from './formatters'

interface SortHeaderProps {
    label: string
    sortKey: string
    sortConfig: SortConfig
    onSort: () => void
}

export function SortHeader({ label, sortKey, sortConfig, onSort }: SortHeaderProps) {
    return (
        <th onClick={onSort} style={{ cursor: 'pointer', userSelect: 'none' }}>
            {label} {sortConfig.key === sortKey ? (sortConfig.dir === 'asc' ? '▲' : '▼') : ''}
        </th>
    )
}
