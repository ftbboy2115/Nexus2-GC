/**
 * useWarriorActions - Custom hook for Warrior action handlers
 * Provides engine controls, simulation controls, and config updates
 */
import { useState, useCallback } from 'react'

const API_BASE = ''

export interface UseWarriorActionsProps {
    addToLog: (message: string) => void
    refetch: () => Promise<void>
    status: { auto_enable?: boolean } | null
}

export interface UseWarriorActionsReturn {
    // Loading state
    actionLoading: string | null
    setActionLoading: (loading: string | null) => void

    // Engine controls
    startEngine: () => Promise<void>
    stopEngine: () => Promise<void>
    pauseEngine: () => Promise<void>
    resumeEngine: () => Promise<void>

    // Simulation controls
    enableSim: () => Promise<void>
    resetSim: () => Promise<void>
    disableSim: () => Promise<void>

    // Broker controls
    enableBroker: () => Promise<void>

    // Config
    toggleAutoEnable: () => Promise<void>
    updateConfig: (field: string, value: number | boolean) => Promise<void>

    // Generic action handler for custom use
    handleAction: (actionId: string, endpoint: string, method?: 'GET' | 'POST' | 'PUT', body?: object) => Promise<any>
}

export function useWarriorActions({
    addToLog,
    refetch,
    status,
}: UseWarriorActionsProps): UseWarriorActionsReturn {
    const [actionLoading, setActionLoading] = useState<string | null>(null)

    const handleAction = useCallback(async (
        actionId: string,
        endpoint: string,
        method: 'GET' | 'POST' | 'PUT' = 'POST',
        body?: object
    ) => {
        setActionLoading(actionId)
        try {
            const res = await fetch(`${API_BASE}${endpoint}`, {
                method,
                headers: { 'Content-Type': 'application/json' },
                body: body ? JSON.stringify(body) : undefined,
            })
            if (res.ok) {
                const data = await res.json()
                addToLog(`✅ ${actionId}: ${data.status || 'Success'}`)
                await refetch()
                return data
            } else {
                const err = await res.json()
                addToLog(`❌ ${actionId}: ${err.detail || 'Failed'}`)
            }
        } catch (err) {
            console.error(`Error with ${actionId}:`, err)
            addToLog(`❌ ${actionId}: Network error`)
        } finally {
            setActionLoading(null)
        }
    }, [addToLog, refetch])

    // Engine Controls
    const startEngine = useCallback(() => handleAction('Start Engine', '/warrior/start'), [handleAction])
    const stopEngine = useCallback(() => handleAction('Stop Engine', '/warrior/stop'), [handleAction])
    const pauseEngine = useCallback(() => handleAction('Pause Engine', '/warrior/pause'), [handleAction])
    const resumeEngine = useCallback(() => handleAction('Resume Engine', '/warrior/resume'), [handleAction])

    // Simulation Controls
    const enableSim = useCallback(() => handleAction('Enable Sim', '/warrior/sim/enable'), [handleAction])
    const resetSim = useCallback(() => handleAction('Reset Sim', '/warrior/sim/reset'), [handleAction])
    const disableSim = useCallback(() => handleAction('Disable Sim', '/warrior/sim/disable'), [handleAction])

    // Broker Controls
    const enableBroker = useCallback(() => handleAction('Enable Broker', '/warrior/broker/enable'), [handleAction])

    // Auto-enable toggle
    const toggleAutoEnable = useCallback(async () => {
        setActionLoading('autoEnable')
        try {
            const newValue = !status?.auto_enable
            const res = await fetch(`${API_BASE}/warrior/auto-enable`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ enabled: newValue }),
            })
            if (res.ok) {
                addToLog(`⚙️ Auto-enable ${newValue ? 'enabled' : 'disabled'}: takes effect on next restart`)
                await refetch()
            } else {
                addToLog('❌ Failed to toggle auto-enable')
            }
        } catch (err) {
            addToLog('❌ Failed to toggle auto-enable')
        } finally {
            setActionLoading(null)
        }
    }, [status?.auto_enable, addToLog, refetch])

    // Config updates
    const updateConfig = useCallback(async (field: string, value: number | boolean) => {
        setActionLoading(`config-${field}`)
        try {
            const res = await fetch(`${API_BASE}/warrior/config`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ [field]: value }),
            })
            if (res.ok) {
                addToLog(`⚙️ Config updated: ${field} = ${value}`)
                await refetch()
            }
        } catch (err) {
            addToLog(`❌ Failed to update ${field}`)
        } finally {
            setActionLoading(null)
        }
    }, [addToLog, refetch])

    return {
        actionLoading,
        setActionLoading,
        startEngine,
        stopEngine,
        pauseEngine,
        resumeEngine,
        enableSim,
        resetSim,
        disableSim,
        enableBroker,
        toggleAutoEnable,
        updateConfig,
        handleAction,
    }
}
