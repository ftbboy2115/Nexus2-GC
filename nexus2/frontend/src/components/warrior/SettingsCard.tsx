/**
 * SettingsCard - Config settings with numeric controls, toggles, and preset modes
 */
import { useState, useEffect, useCallback } from 'react'
import styles from '@/styles/Warrior.module.css'
import { CollapsibleCard } from './CollapsibleCard'

interface WarriorConfig {
    max_candidates?: number
    scanner_interval_minutes?: number
    risk_per_trade?: number
    max_positions?: number
    max_shares_per_trade?: number
    max_capital?: number
    orb_enabled?: boolean
    pmh_enabled?: boolean
    entry_bar_timeframe?: string  // "1min" or "10s"
    always_run_ai_comparison?: boolean
}

interface SettingsCardProps {
    config?: WarriorConfig
    updateConfig: (key: string, value: number | boolean | string) => void
}

// Preset types
interface Preset {
    risk_per_trade: number
    max_capital: number
    max_shares_per_trade: number
}

// Default preset values (fallbacks if nothing saved)
const DEFAULT_ROSS: Preset = { risk_per_trade: 2500, max_capital: 100000, max_shares_per_trade: 10000 }
const DEFAULT_CONSERVATIVE: Preset = { risk_per_trade: 50, max_capital: 1000, max_shares_per_trade: 10 }

// Load/save presets from localStorage
const STORAGE_KEY = 'warrior-settings-presets'

function loadPresets(): { ross: Preset; conservative: Preset } {
    if (typeof window !== 'undefined') {
        try {
            const saved = localStorage.getItem(STORAGE_KEY)
            if (saved) return JSON.parse(saved)
        } catch { /* ignore */ }
    }
    return { ross: DEFAULT_ROSS, conservative: DEFAULT_CONSERVATIVE }
}

function savePresets(presets: { ross: Preset; conservative: Preset }) {
    if (typeof window !== 'undefined') {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(presets))
    }
}

export function SettingsCard({ config, updateConfig }: SettingsCardProps) {
    // Preset state (loaded from localStorage)
    const [presets, setPresets] = useState(loadPresets)

    // Notes state
    const [showNotes, setShowNotes] = useState(false)
    const [notesText, setNotesText] = useState('')
    const [notesLoading, setNotesLoading] = useState(false)

    // Detect if currently in Ross mode (all three values match saved Ross preset)
    const isRossMode =
        config?.risk_per_trade === presets.ross.risk_per_trade &&
        config?.max_capital === presets.ross.max_capital &&
        config?.max_shares_per_trade === presets.ross.max_shares_per_trade

    // Toggle between presets
    const togglePreset = () => {
        const preset = isRossMode ? presets.conservative : presets.ross
        updateConfig('risk_per_trade', preset.risk_per_trade)
        updateConfig('max_capital', preset.max_capital)
        updateConfig('max_shares_per_trade', preset.max_shares_per_trade)
    }

    // Save current values as the default for the active mode
    const saveAsDefault = () => {
        const modeName = isRossMode ? 'Ross Size' : 'Conservative'
        const current: Preset = {
            risk_per_trade: config?.risk_per_trade || 50,
            max_capital: config?.max_capital || 1000,
            max_shares_per_trade: config?.max_shares_per_trade || 10,
        }
        const msg = `Save current settings as ${modeName} default?\n\n` +
            `Risk/Trade: $${current.risk_per_trade.toLocaleString()}\n` +
            `Max Capital: $${current.max_capital.toLocaleString()}\n` +
            `Max Shares: ${current.max_shares_per_trade.toLocaleString()}`
        if (confirm(msg)) {
            const updated = { ...presets }
            if (isRossMode) {
                updated.ross = current
            } else {
                updated.conservative = current
            }
            setPresets(updated)
            savePresets(updated)
        }
    }

    // Load notes from API
    const loadNotes = useCallback(async () => {
        setNotesLoading(true)
        try {
            const res = await fetch('/warrior/mock-market/notes?case_id=_settings')
            if (res.ok) {
                const data = await res.json()
                setNotesText(data.notes || '')
            }
        } catch (err) {
            console.error('Failed to load settings notes:', err)
        } finally {
            setNotesLoading(false)
        }
    }, [])

    // Save notes to API
    const saveNotes = async () => {
        try {
            await fetch('/warrior/mock-market/notes', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ case_id: '_settings', notes: notesText }),
            })
        } catch (err) {
            console.error('Failed to save settings notes:', err)
        }
    }

    // Load notes when panel opens
    useEffect(() => {
        if (showNotes) {
            loadNotes()
        }
    }, [showNotes, loadNotes])

    return (
        <CollapsibleCard
            id="settings"
            title="⚙️ Settings"
            badge={
                <button
                    onClick={(e) => { e.stopPropagation(); setShowNotes(!showNotes) }}
                    style={{
                        background: 'none', border: 'none', cursor: 'pointer',
                        fontSize: '1rem', padding: '0 0.25rem',
                        color: showNotes ? '#4dabf7' : '#888',
                    }}
                    title="Settings Notepad"
                >
                    📋
                </button>
            }
        >
            <div className={styles.cardBody}>
                {/* Notes Section */}
                {showNotes && (
                    <div style={{
                        padding: '0.75rem', marginBottom: '0.75rem',
                        background: 'rgba(77, 171, 247, 0.08)', borderRadius: '6px',
                        border: '1px solid rgba(77, 171, 247, 0.2)',
                    }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                            <span style={{ fontSize: '0.85rem', fontWeight: 600, color: '#4dabf7' }}>📋 Settings Notes</span>
                            <button
                                onClick={saveNotes}
                                className={styles.btnSmall}
                                style={{ fontSize: '0.75rem' }}
                            >
                                💾 Save
                            </button>
                        </div>
                        {notesLoading ? (
                            <span style={{ color: '#888', fontSize: '0.8rem' }}>Loading...</span>
                        ) : (
                            <textarea
                                value={notesText}
                                onChange={(e) => setNotesText(e.target.value)}
                                placeholder="Settings notes, reminders, config rationale..."
                                style={{
                                    width: '100%', minHeight: '80px', padding: '0.5rem',
                                    background: 'rgba(0,0,0,0.3)', border: '1px solid #444',
                                    borderRadius: '4px', color: '#e0e0e0', fontSize: '0.8rem',
                                    resize: 'vertical', fontFamily: 'inherit',
                                }}
                            />
                        )}
                    </div>
                )}

                <div className={styles.settingsGrid}>
                    <div className={styles.settingItem}>
                        <label>Max Candidates</label>
                        <div className={styles.settingControl}>
                            <button
                                onClick={() => updateConfig('max_candidates', Math.max(1, (config?.max_candidates || 5) - 1))}
                                className={styles.btnSmall}
                            >-</button>
                            <span>{config?.max_candidates || 5}</span>
                            <button
                                onClick={() => updateConfig('max_candidates', Math.min(20, (config?.max_candidates || 5) + 1))}
                                className={styles.btnSmall}
                            >+</button>
                        </div>
                    </div>
                    <div className={styles.settingItem}>
                        <label>Scan Interval (min)</label>
                        <div className={styles.settingControl}>
                            <button
                                onClick={() => updateConfig('scanner_interval_minutes', Math.max(1, (config?.scanner_interval_minutes || 5) - 1))}
                                className={styles.btnSmall}
                            >-</button>
                            <span>{config?.scanner_interval_minutes || 5}</span>
                            <button
                                onClick={() => updateConfig('scanner_interval_minutes', Math.min(30, (config?.scanner_interval_minutes || 5) + 1))}
                                className={styles.btnSmall}
                            >+</button>
                        </div>
                    </div>
                    <div className={styles.settingItem}>
                        <label>Risk/Trade ($)</label>
                        <div className={styles.settingControl}>
                            <button
                                onClick={() => updateConfig('risk_per_trade', Math.max(10, (config?.risk_per_trade || 100) - 25))}
                                className={styles.btnSmall}
                            >-</button>
                            <input
                                type="number"
                                value={config?.risk_per_trade || 100}
                                onChange={(e) => {
                                    const val = parseInt(e.target.value, 10)
                                    if (!isNaN(val) && val >= 10 && val <= 10000) {
                                        updateConfig('risk_per_trade', val)
                                    }
                                }}
                                className={styles.settingInput}
                                min={10}
                                max={10000}
                            />
                            <button
                                onClick={() => updateConfig('risk_per_trade', Math.min(10000, (config?.risk_per_trade || 100) + 25))}
                                className={styles.btnSmall}
                            >+</button>
                        </div>
                    </div>
                    <div className={styles.settingItem}>
                        <label>Max Positions</label>
                        <div className={styles.settingControl}>
                            <button
                                onClick={() => updateConfig('max_positions', Math.max(1, (config?.max_positions || 3) - 1))}
                                className={styles.btnSmall}
                            >-</button>
                            <span>{config?.max_positions || 3}</span>
                            <button
                                onClick={() => updateConfig('max_positions', Math.min(20, (config?.max_positions || 3) + 1))}
                                className={styles.btnSmall}
                            >+</button>
                        </div>
                    </div>
                    <div className={styles.settingItem}>
                        <label>Max Shares/Trade</label>
                        <div className={styles.settingControl}>
                            <button
                                onClick={() => updateConfig('max_shares_per_trade', Math.max(10, (config?.max_shares_per_trade || 100) - 10))}
                                className={styles.btnSmall}
                            >-</button>
                            <input
                                type="number"
                                value={config?.max_shares_per_trade || 100}
                                onChange={(e) => {
                                    const val = parseInt(e.target.value, 10)
                                    if (!isNaN(val) && val >= 10 && val <= 10000) {
                                        updateConfig('max_shares_per_trade', val)
                                    }
                                }}
                                className={styles.settingInput}
                                min={10}
                                max={10000}
                            />
                            <button
                                onClick={() => updateConfig('max_shares_per_trade', Math.min(10000, (config?.max_shares_per_trade || 100) + 10))}
                                className={styles.btnSmall}
                            >+</button>
                        </div>
                    </div>
                    <div className={styles.settingItem}>
                        <label>Max Capital/Trade ($)</label>
                        <div className={styles.settingControl}>
                            <button
                                onClick={() => updateConfig('max_capital', Math.max(1000, (config?.max_capital || 5000) - 1000))}
                                className={styles.btnSmall}
                            >-</button>
                            <input
                                type="number"
                                value={config?.max_capital || 5000}
                                onChange={(e) => {
                                    const val = parseInt(e.target.value, 10)
                                    if (!isNaN(val) && val >= 1000 && val <= 500000) {
                                        updateConfig('max_capital', val)
                                    }
                                }}
                                className={styles.settingInput}
                                min={1000}
                                max={500000}
                            />
                            <button
                                onClick={() => updateConfig('max_capital', Math.min(500000, (config?.max_capital || 5000) + 1000))}
                                className={styles.btnSmall}
                            >+</button>
                        </div>
                    </div>
                </div>

                {/* Entry Mode Toggles */}
                <div className={styles.entryModeToggles}>
                    <button
                        onClick={() => updateConfig('orb_enabled', !config?.orb_enabled)}
                        className={config?.orb_enabled ? styles.btnToggleOn : styles.btnToggleOff}
                    >
                        {config?.orb_enabled ? '✅' : '❌'} ORB
                    </button>
                    <button
                        onClick={() => updateConfig('pmh_enabled', !config?.pmh_enabled)}
                        className={config?.pmh_enabled ? styles.btnToggleOn : styles.btnToggleOff}
                    >
                        {config?.pmh_enabled ? '✅' : '❌'} PMH
                    </button>
                    {/* Bar Timeframe Toggle */}
                    <button
                        onClick={() => updateConfig(
                            'entry_bar_timeframe',
                            config?.entry_bar_timeframe === '10s' ? '1min' : '10s'
                        )}
                        className={config?.entry_bar_timeframe === '10s' ? styles.btnToggleOn : styles.btnToggleOff}
                        title="Entry bar timeframe: 10s for faster entry, 1min for standard"
                    >
                        {config?.entry_bar_timeframe === '10s' ? '⚡' : '📊'} {config?.entry_bar_timeframe === '10s' ? '10s Bars' : '1min Bars'}
                    </button>
                    <button
                        onClick={() => updateConfig('always_run_ai_comparison', !(config?.always_run_ai_comparison ?? true))}
                        className={(config?.always_run_ai_comparison ?? true) ? styles.btnToggleOn : styles.btnToggleOff}
                        title="Run AI comparison on all headlines (even when regex/calendar already found catalyst). Disable to reduce API calls."
                    >
                        {(config?.always_run_ai_comparison ?? true) ? '🤖' : '💤'} AI Compare
                    </button>
                    {/* Ross Size Preset Toggle */}
                    <button
                        onClick={togglePreset}
                        className={isRossMode ? styles.btnToggleOn : styles.btnToggleOff}
                        title={isRossMode
                            ? `Ross Size: $${presets.ross.risk_per_trade.toLocaleString()} risk, $${presets.ross.max_capital.toLocaleString()} capital, ${presets.ross.max_shares_per_trade.toLocaleString()} shares — click to switch to Conservative`
                            : `Conservative: $${presets.conservative.risk_per_trade.toLocaleString()} risk, $${presets.conservative.max_capital.toLocaleString()} capital, ${presets.conservative.max_shares_per_trade.toLocaleString()} shares — click to switch to Ross Size`
                        }
                    >
                        {isRossMode ? '🚀 Ross Size' : '🐻 Conservative'}
                    </button>
                    <button
                        onClick={saveAsDefault}
                        className={styles.btnSmall}
                        title={`Save current values as ${isRossMode ? 'Ross Size' : 'Conservative'} default`}
                        style={{ fontSize: '0.75rem', padding: '0.2rem 0.4rem' }}
                    >
                        💾 Save Default
                    </button>
                </div>
            </div>
        </CollapsibleCard>
    )
}
