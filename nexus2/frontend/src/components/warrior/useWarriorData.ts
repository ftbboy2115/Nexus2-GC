/**
 * useWarriorData - Custom hook for Warrior page data fetching
 */
import { useState, useEffect, useCallback } from 'react'
import type {
    WarriorStatus,
    WarriorPosition,
    PositionHealth,
    SimStatus,
    BrokerStatus,
    ScanResult,
} from './types'

const API_BASE = ''

export interface UseWarriorDataReturn {
    // Core state
    status: WarriorStatus | null
    positions: WarriorPosition[]
    positionHealth: Record<string, PositionHealth>
    scanResult: ScanResult | null
    loading: boolean

    // Simulation/Broker
    simStatus: SimStatus | null
    brokerStatus: BrokerStatus | null

    // Trade events
    tradeEvents: any[]

    // Setters for external updates
    setScanResult: (result: ScanResult | null) => void

    // Refetch
    refetch: () => Promise<void>

    // Event log helper
    addToLog: (message: string) => void
    eventLog: string[]
    setEventLog: (log: string[]) => void
}

export function useWarriorData(): UseWarriorDataReturn {
    const [status, setStatus] = useState<WarriorStatus | null>(null)
    const [positions, setPositions] = useState<WarriorPosition[]>([])
    const [positionHealth, setPositionHealth] = useState<Record<string, PositionHealth>>({})
    const [scanResult, setScanResult] = useState<ScanResult | null>(null)
    const [loading, setLoading] = useState(true)

    const [simStatus, setSimStatus] = useState<SimStatus | null>(null)
    const [brokerStatus, setBrokerStatus] = useState<BrokerStatus | null>(null)

    const [tradeEvents, setTradeEvents] = useState<any[]>([])
    const [eventLog, setEventLog] = useState<string[]>([])

    const addToLog = useCallback((message: string) => {
        const timestamp = new Date().toLocaleTimeString()
        setEventLog(prev => [`[${timestamp}] ${message}`, ...prev.slice(0, 99)])
    }, [])

    const fetchStatus = useCallback(async () => {
        try {
            const [statusRes, positionsRes, simRes, brokerRes] = await Promise.all([
                fetch(`${API_BASE}/warrior/status`),
                fetch(`${API_BASE}/warrior/positions`),
                fetch(`${API_BASE}/warrior/sim/status`),
                fetch(`${API_BASE}/warrior/broker/status`),
            ])

            if (statusRes.ok) setStatus(await statusRes.json())
            if (positionsRes.ok) {
                const data = await positionsRes.json()
                setPositions(data.positions || [])
            }
            if (simRes.ok) setSimStatus(await simRes.json())

            // Fetch position health indicators
            try {
                const healthRes = await fetch(`${API_BASE}/warrior/positions/health`)
                if (healthRes.ok) {
                    const healthData = await healthRes.json()
                    const healthMap: Record<string, PositionHealth> = {}
                    for (const p of healthData.positions || []) {
                        if (p.health) {
                            healthMap[p.position_id] = p.health
                        }
                    }
                    setPositionHealth(healthMap)
                }
            } catch (err) {
                console.error('Error fetching position health:', err)
            }
            if (brokerRes.ok) setBrokerStatus(await brokerRes.json())

            // Fetch recent trade events
            try {
                const eventsRes = await fetch(`${API_BASE}/trade-events/recent?strategy=WARRIOR&limit=20`)
                if (eventsRes.ok) {
                    const eventsData = await eventsRes.json()
                    setTradeEvents(eventsData.events || [])
                }
            } catch (err) {
                console.error('Error fetching Warrior trade events:', err)
            }
        } catch (err) {
            console.error('Error fetching Warrior status:', err)
            addToLog('❌ Failed to connect to backend')
        } finally {
            setLoading(false)
        }
    }, [addToLog])

    // Auto-fetch on mount and interval
    useEffect(() => {
        fetchStatus()
        const interval = setInterval(fetchStatus, 1000)
        return () => clearInterval(interval)
    }, [fetchStatus])

    return {
        status,
        positions,
        positionHealth,
        scanResult,
        loading,
        simStatus,
        brokerStatus,
        tradeEvents,
        setScanResult,
        refetch: fetchStatus,
        addToLog,
        eventLog,
        setEventLog,
    }
}
