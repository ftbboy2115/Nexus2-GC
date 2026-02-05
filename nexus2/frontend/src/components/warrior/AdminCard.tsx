/**
 * AdminCard - Server administration controls (restart, cache clear)
 */
import { useState, useEffect } from 'react'
import styles from '@/styles/Warrior.module.css'
import { CollapsibleCard } from './CollapsibleCard'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface AdminStatus {
    status: string
    timestamp: string
    version: string
    mode: string
    uptime_seconds: number
    memory_mb: number
    disk_used_gb?: number
    disk_total_gb?: number
    disk_percent?: number
}

export function AdminCard() {
    const [confirmText, setConfirmText] = useState('')
    const [clearCache, setClearCache] = useState(false)
    const [isRestarting, setIsRestarting] = useState(false)
    const [message, setMessage] = useState('')
    const [adminStatus, setAdminStatus] = useState<AdminStatus | null>(null)

    useEffect(() => {
        const fetchStatus = async () => {
            try {
                const res = await fetch(`${API_BASE}/health`)
                if (res.ok) {
                    const data = await res.json()
                    setAdminStatus(data)
                }
            } catch {
                setAdminStatus(null)
            }
        }
        fetchStatus()
        // Refresh every 30 seconds
        const interval = setInterval(fetchStatus, 30000)
        return () => clearInterval(interval)
    }, [])

    const handleRestart = async () => {
        if (confirmText !== 'REBOOT') {
            setMessage('❌ Type REBOOT to confirm')
            return
        }

        setIsRestarting(true)
        setMessage('🔄 Restarting server...')

        try {
            const res = await fetch(`${API_BASE}/admin/restart`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ confirmation: 'REBOOT', clear_cache: clearCache })
            })

            if (res.ok) {
                const data = await res.json()
                setMessage(`✅ ${data.message}`)

                // Auto-refresh after 8 seconds
                setTimeout(() => {
                    window.location.reload()
                }, 8000)
            } else {
                const err = await res.json()
                setMessage(`❌ ${err.detail}`)
                setIsRestarting(false)
            }
        } catch (e) {
            // Expected - server is restarting
            setMessage('🔄 Server is restarting... Page will refresh in 8 seconds.')
            setTimeout(() => {
                window.location.reload()
            }, 8000)
        }
    }

    return (
        <CollapsibleCard
            id="admin"
            title="🔧 Server Admin"
            defaultCollapsed={true}
        >
            <div className={styles.cardBody}>
                {/* Health Stats */}
                {adminStatus && (
                    <div style={{
                        display: 'grid',
                        gridTemplateColumns: 'repeat(4, 1fr)',
                        gap: '12px',
                        marginBottom: '16px',
                        padding: '12px',
                        background: 'rgba(50, 200, 100, 0.1)',
                        borderRadius: '8px',
                        border: '1px solid rgba(50, 200, 100, 0.3)'
                    }}>
                        <div style={{ textAlign: 'center' }}>
                            <div style={{ fontSize: '11px', color: '#888' }}>Uptime</div>
                            <div style={{ fontWeight: 'bold', color: '#4ade80' }}>
                                {Math.floor(adminStatus.uptime_seconds / 3600)}h {Math.floor((adminStatus.uptime_seconds % 3600) / 60)}m
                            </div>
                        </div>
                        <div style={{ textAlign: 'center' }}>
                            <div style={{ fontSize: '11px', color: '#888' }}>Memory</div>
                            <div style={{ fontWeight: 'bold', color: '#4ade80' }}>{adminStatus.memory_mb} MB</div>
                        </div>
                        <div style={{ textAlign: 'center' }}>
                            <div style={{ fontSize: '11px', color: '#888' }}>Storage</div>
                            <div style={{
                                fontWeight: 'bold',
                                color: (adminStatus.disk_percent ?? 0) > 80 ? '#f87171' : '#4ade80'
                            }}>
                                {adminStatus.disk_used_gb ?? '?'}/{adminStatus.disk_total_gb ?? '?'} GB
                            </div>
                        </div>
                        <div style={{ textAlign: 'center' }}>
                            <div style={{ fontSize: '11px', color: '#888' }}>Mode</div>
                            <div style={{ fontWeight: 'bold', color: adminStatus.mode?.includes('paper') ? '#fbbf24' : '#f87171' }}>
                                {adminStatus.mode?.replace('alpaca_', '').toUpperCase()}
                            </div>
                        </div>
                    </div>
                )}

                {/* Restart Section */}
                <div style={{
                    padding: '12px',
                    background: 'rgba(255, 100, 100, 0.1)',
                    borderRadius: '8px',
                    border: '1px solid rgba(255, 100, 100, 0.3)'
                }}>
                    <div style={{ marginBottom: '8px', fontWeight: 'bold', color: '#ff6b6b' }}>
                        ⚠️ Server Restart
                    </div>

                    <div style={{ display: 'flex', gap: '8px', alignItems: 'center', marginBottom: '8px' }}>
                        <input
                            type="text"
                            placeholder="Type REBOOT to confirm"
                            value={confirmText}
                            onChange={(e) => setConfirmText(e.target.value.toUpperCase())}
                            style={{
                                flex: 1,
                                padding: '8px',
                                borderRadius: '4px',
                                border: '1px solid #444',
                                background: '#1a1a1a',
                                color: '#fff',
                                fontFamily: 'monospace'
                            }}
                            disabled={isRestarting}
                        />
                        <button
                            onClick={handleRestart}
                            disabled={isRestarting || confirmText !== 'REBOOT'}
                            className={styles.btnDanger}
                            style={{
                                padding: '8px 16px',
                                opacity: confirmText === 'REBOOT' && !isRestarting ? 1 : 0.5,
                                cursor: confirmText === 'REBOOT' && !isRestarting ? 'pointer' : 'not-allowed'
                            }}
                        >
                            {isRestarting ? '🔄' : '🔄 Restart'}
                        </button>
                    </div>

                    <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
                        <input
                            type="checkbox"
                            checked={clearCache}
                            onChange={(e) => setClearCache(e.target.checked)}
                            disabled={isRestarting}
                        />
                        <span style={{ fontSize: '13px', color: '#aaa' }}>
                            Clear __pycache__ (for code updates)
                        </span>
                    </label>

                    {message && (
                        <div style={{ marginTop: '8px', fontSize: '13px' }}>
                            {message}
                        </div>
                    )}
                </div>
            </div>
        </CollapsibleCard>
    )
}
