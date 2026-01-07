/**
 * useColumnConfig - Hook for managing table column configuration
 * 
 * Handles loading/saving preferences via API and provides column state.
 */

import { useState, useEffect, useCallback } from 'react'
import type { ColumnConfig } from '@/components/ColumnEditor'

const API_BASE = 'http://localhost:8000/api'

export function useColumnConfig(
    preferenceKey: string,
    defaultColumns: ColumnConfig[]
) {
    const [columns, setColumns] = useState<ColumnConfig[]>(defaultColumns)
    const [editColumns, setEditColumns] = useState<ColumnConfig[]>(defaultColumns)
    const [isEditing, setIsEditing] = useState(false)
    const [loaded, setLoaded] = useState(false)

    // Load preferences on mount
    useEffect(() => {
        async function loadPreferences() {
            try {
                const res = await fetch(`${API_BASE}/preferences/${preferenceKey}`)
                if (res.ok) {
                    const data = await res.json()
                    if (data.value && Array.isArray(data.value)) {
                        // Merge saved prefs with default columns (in case new columns were added)
                        const savedIds = new Set(data.value.map((c: ColumnConfig) => c.id))
                        const merged = [
                            ...data.value,
                            ...defaultColumns.filter(c => !savedIds.has(c.id))
                        ]
                        setColumns(merged)
                    }
                }
            } catch (err) {
                console.error('Failed to load column preferences:', err)
            } finally {
                setLoaded(true)
            }
        }
        loadPreferences()
    }, [preferenceKey, defaultColumns])

    // Open editor modal
    const openEditor = useCallback(() => {
        setEditColumns([...columns])
        setIsEditing(true)
    }, [columns])

    // Cancel editing
    const cancelEdit = useCallback(() => {
        setIsEditing(false)
    }, [])

    // Save changes
    const saveEdit = useCallback(async () => {
        try {
            const res = await fetch(`${API_BASE}/preferences/${preferenceKey}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ value: editColumns })
            })
            if (res.ok) {
                setColumns(editColumns)
                setIsEditing(false)
            }
        } catch (err) {
            console.error('Failed to save column preferences:', err)
        }
    }, [preferenceKey, editColumns])

    // Reset to defaults
    const resetEdit = useCallback(() => {
        setEditColumns([...defaultColumns])
    }, [defaultColumns])

    // Get visible columns in order
    const visibleColumns = columns.filter(c => c.visible)

    return {
        columns: visibleColumns,
        allColumns: columns,
        editColumns,
        setEditColumns,
        isEditing,
        openEditor,
        cancelEdit,
        saveEdit,
        resetEdit,
        loaded
    }
}

// Default column configurations
export const DASHBOARD_COLUMNS: ColumnConfig[] = [
    { id: 'checkbox', label: 'Select', visible: true },
    { id: 'symbol', label: 'Symbol', visible: true },
    { id: 'setup_type', label: 'Setup', visible: true },
    { id: 'entry_price', label: 'Entry', visible: true },
    { id: 'shares', label: 'Shares', visible: true },
    { id: 'current_stop', label: 'Stop', visible: true },
    { id: 'realized_pnl', label: 'P&L', visible: true },
    { id: 'days_held', label: 'Days', visible: true },
    { id: 'status', label: 'Status', visible: true },
    { id: 'actions', label: 'Actions', visible: true },
]

export const AUTOMATION_COLUMNS: ColumnConfig[] = [
    { id: 'symbol', label: 'Symbol', visible: true },
    { id: 'qty', label: 'Qty', visible: true },
    { id: 'avg_price', label: 'Avg Price', visible: true },
    { id: 'current_price', label: 'Current', visible: true },
    { id: 'market_value', label: 'Value', visible: true },
    { id: 'unrealized_pnl', label: 'P&L ($)', visible: true },
    { id: 'pnl_percent', label: 'P&L (%)', visible: true },
    { id: 'change_today', label: 'Today', visible: true },
    { id: 'side', label: 'Side', visible: true },
]

// Columns only shown in maximized/expanded view
export const AUTOMATION_EXPANDED_COLUMNS: ColumnConfig[] = [
    { id: 'symbol', label: 'Symbol', visible: true },
    { id: 'qty', label: 'Qty', visible: true },
    { id: 'side', label: 'Side', visible: true },
    { id: 'avg_price', label: 'Entry', visible: true },
    { id: 'current_price', label: 'Current', visible: true },
    { id: 'stop_price', label: 'Stop', visible: true },
    { id: 'market_value', label: 'Value', visible: true },
    { id: 'unrealized_pnl', label: 'P&L ($)', visible: true },
    { id: 'pnl_percent', label: 'P&L (%)', visible: true },
    { id: 'change_today', label: 'Today', visible: true },
    { id: 'days_held', label: 'Days', visible: true },
]
