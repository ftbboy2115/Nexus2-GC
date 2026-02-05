/**
 * TradingNotesCalendarCard - Performance calendar for Ross vs Bot comparison
 * 
 * Displays a mini calendar with dots indicating days with notes.
 * Click a date to open a modal for viewing/editing notes.
 */
import { useState, useEffect, useCallback } from 'react'
import { CollapsibleCard } from './CollapsibleCard'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface TradingNote {
    date: string
    ross_trades?: number | null
    ross_pnl?: string | null
    ross_notes?: string | null
    warrior_trades?: number | null
    warrior_pnl?: string | null
    warrior_notes?: string | null
    market_context?: string | null
    lessons?: string | null
}

export function TradingNotesCalendarCard() {
    const [currentDate, setCurrentDate] = useState(new Date())
    const [datesWithEntries, setDatesWithEntries] = useState<string[]>([])
    const [selectedDate, setSelectedDate] = useState<string | null>(null)
    const [note, setNote] = useState<TradingNote | null>(null)
    const [saving, setSaving] = useState(false)
    const [loading, setLoading] = useState(false)

    // Form state
    const [formData, setFormData] = useState<TradingNote>({
        date: '',
        ross_trades: null,
        ross_pnl: '',
        ross_notes: '',
        warrior_trades: null,
        warrior_pnl: '',
        warrior_notes: '',
        market_context: '',
        lessons: '',
    })

    // Fetch dates with entries for current month
    const fetchDatesWithEntries = useCallback(async () => {
        const year = currentDate.getFullYear()
        const month = currentDate.getMonth()
        const startDate = `${year}-${String(month + 1).padStart(2, '0')}-01`
        const endDate = `${year}-${String(month + 1).padStart(2, '0')}-31`

        try {
            const res = await fetch(`${API_BASE}/trading-notes/dates-with-entries?start_date=${startDate}&end_date=${endDate}`)
            if (res.ok) {
                const data = await res.json()
                setDatesWithEntries(data.dates || [])
            }
        } catch (err) {
            console.error('Failed to fetch dates:', err)
        }
    }, [currentDate])

    useEffect(() => {
        fetchDatesWithEntries()
    }, [fetchDatesWithEntries])

    // Fetch note for selected date
    const fetchNote = async (date: string) => {
        setLoading(true)
        try {
            const res = await fetch(`${API_BASE}/trading-notes/${date}`)
            if (res.ok) {
                const data = await res.json()
                if (data.note) {
                    setNote(data.note)
                    setFormData(data.note)
                } else {
                    setNote(null)
                    setFormData({
                        date,
                        ross_trades: null,
                        ross_pnl: '',
                        ross_notes: '',
                        warrior_trades: null,
                        warrior_pnl: '',
                        warrior_notes: '',
                        market_context: '',
                        lessons: '',
                    })
                }
            }
        } catch (err) {
            console.error('Failed to fetch note:', err)
        } finally {
            setLoading(false)
        }
    }

    // Save note
    const saveNote = async () => {
        if (!selectedDate) return
        setSaving(true)
        try {
            const res = await fetch(`${API_BASE}/trading-notes/${selectedDate}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    ross_trades: formData.ross_trades,
                    ross_pnl: formData.ross_pnl || null,
                    ross_notes: formData.ross_notes || null,
                    warrior_trades: formData.warrior_trades,
                    warrior_pnl: formData.warrior_pnl || null,
                    warrior_notes: formData.warrior_notes || null,
                    market_context: formData.market_context || null,
                    lessons: formData.lessons || null,
                }),
            })
            if (res.ok) {
                await fetchDatesWithEntries()
                setSelectedDate(null)
            }
        } catch (err) {
            console.error('Failed to save note:', err)
        } finally {
            setSaving(false)
        }
    }

    // Calendar helpers
    const getDaysInMonth = (year: number, month: number) => new Date(year, month + 1, 0).getDate()
    const getFirstDayOfMonth = (year: number, month: number) => new Date(year, month, 1).getDay()

    const year = currentDate.getFullYear()
    const month = currentDate.getMonth()
    const daysInMonth = getDaysInMonth(year, month)
    const firstDay = getFirstDayOfMonth(year, month)
    const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

    const handleDateClick = (day: number) => {
        const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`
        setSelectedDate(dateStr)
        fetchNote(dateStr)
    }

    const prevMonth = () => setCurrentDate(new Date(year, month - 1, 1))
    const nextMonth = () => setCurrentDate(new Date(year, month + 1, 1))

    // Build calendar grid
    const calendarDays = []
    for (let i = 0; i < firstDay; i++) {
        calendarDays.push(<div key={`empty-${i}`} style={{ padding: '6px', minHeight: '28px' }} />)
    }
    for (let day = 1; day <= daysInMonth; day++) {
        const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`
        const hasEntry = datesWithEntries.includes(dateStr)
        const isToday = new Date().toISOString().slice(0, 10) === dateStr

        calendarDays.push(
            <div
                key={day}
                onClick={() => handleDateClick(day)}
                style={{
                    cursor: 'pointer',
                    padding: '6px',
                    background: isToday ? 'rgba(59, 130, 246, 0.2)' : undefined,
                    borderRadius: '4px',
                    position: 'relative',
                    textAlign: 'center',
                    minHeight: '28px',
                }}
            >
                {day}
                {hasEntry && (
                    <span style={{
                        position: 'absolute',
                        bottom: '2px',
                        left: '50%',
                        transform: 'translateX(-50%)',
                        width: '4px',
                        height: '4px',
                        background: '#22c55e',
                        borderRadius: '50%',
                    }} />
                )}
            </div>
        )
    }

    return (
        <CollapsibleCard id="trading-notes" title="📅 Trading Notes" defaultCollapsed={true}>
            <div style={{ padding: '12px' }}>
                {/* Calendar Header */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                    <button onClick={prevMonth} style={{ background: 'none', border: 'none', color: '#888', cursor: 'pointer', fontSize: '16px' }}>◀</button>
                    <span style={{ fontWeight: 600 }}>{monthNames[month]} {year}</span>
                    <button onClick={nextMonth} style={{ background: 'none', border: 'none', color: '#888', cursor: 'pointer', fontSize: '16px' }}>▶</button>
                </div>

                {/* Calendar Grid */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: '2px', textAlign: 'center', fontSize: '12px' }}>
                    {['S', 'M', 'T', 'W', 'T', 'F', 'S'].map((d, i) => (
                        <div key={i} style={{ color: '#666', padding: '4px', fontWeight: 600 }}>{d}</div>
                    ))}
                    {calendarDays}
                </div>

                <div style={{ marginTop: '8px', fontSize: '11px', color: '#666', textAlign: 'center' }}>
                    Click a date to add/view notes
                </div>
            </div>

            {/* Modal Overlay */}
            {selectedDate && (
                <div
                    style={{
                        position: 'fixed',
                        top: 0,
                        left: 0,
                        right: 0,
                        bottom: 0,
                        background: 'rgba(0,0,0,0.7)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        zIndex: 1000,
                    }}
                    onClick={() => setSelectedDate(null)}
                >
                    <div
                        style={{
                            background: '#1e1e1e',
                            borderRadius: '8px',
                            padding: '20px',
                            width: '500px',
                            maxHeight: '80vh',
                            overflowY: 'auto',
                        }}
                        onClick={(e) => e.stopPropagation()}
                    >
                        <h3 style={{ margin: '0 0 16px 0' }}>📝 Notes for {selectedDate}</h3>

                        {loading ? (
                            <p style={{ color: '#888' }}>Loading...</p>
                        ) : (
                            <>
                                {/* Ross Section */}
                                <div style={{ marginBottom: '16px', padding: '12px', background: '#2a2a2a', borderRadius: '6px' }}>
                                    <h4 style={{ margin: '0 0 8px 0', color: '#60a5fa' }}>👨‍🏫 Ross (Teacher)</h4>
                                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', marginBottom: '8px' }}>
                                        <label style={{ fontSize: '12px' }}>
                                            Trades
                                            <input
                                                type="number"
                                                value={formData.ross_trades ?? ''}
                                                onChange={(e) => setFormData({ ...formData, ross_trades: e.target.value ? parseInt(e.target.value) : null })}
                                                style={{ width: '100%', padding: '6px', borderRadius: '4px', border: '1px solid #444', background: '#1e1e1e', color: '#eee' }}
                                            />
                                        </label>
                                        <label style={{ fontSize: '12px' }}>
                                            P&L
                                            <input
                                                type="text"
                                                value={formData.ross_pnl ?? ''}
                                                onChange={(e) => setFormData({ ...formData, ross_pnl: e.target.value })}
                                                placeholder="e.g. +$1,500"
                                                style={{ width: '100%', padding: '6px', borderRadius: '4px', border: '1px solid #444', background: '#1e1e1e', color: '#eee' }}
                                            />
                                        </label>
                                    </div>
                                    <textarea
                                        value={formData.ross_notes ?? ''}
                                        onChange={(e) => setFormData({ ...formData, ross_notes: e.target.value })}
                                        placeholder="Notes on Ross's trades..."
                                        rows={2}
                                        style={{ width: '100%', padding: '6px', borderRadius: '4px', border: '1px solid #444', background: '#1e1e1e', color: '#eee', resize: 'vertical' }}
                                    />
                                </div>

                                {/* Warrior Section */}
                                <div style={{ marginBottom: '16px', padding: '12px', background: '#2a2a2a', borderRadius: '6px' }}>
                                    <h4 style={{ margin: '0 0 8px 0', color: '#f59e0b' }}>🤖 Warrior (Bot)</h4>
                                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', marginBottom: '8px' }}>
                                        <label style={{ fontSize: '12px' }}>
                                            Trades
                                            <input
                                                type="number"
                                                value={formData.warrior_trades ?? ''}
                                                onChange={(e) => setFormData({ ...formData, warrior_trades: e.target.value ? parseInt(e.target.value) : null })}
                                                style={{ width: '100%', padding: '6px', borderRadius: '4px', border: '1px solid #444', background: '#1e1e1e', color: '#eee' }}
                                            />
                                        </label>
                                        <label style={{ fontSize: '12px' }}>
                                            P&L
                                            <input
                                                type="text"
                                                value={formData.warrior_pnl ?? ''}
                                                onChange={(e) => setFormData({ ...formData, warrior_pnl: e.target.value })}
                                                placeholder="e.g. +$250"
                                                style={{ width: '100%', padding: '6px', borderRadius: '4px', border: '1px solid #444', background: '#1e1e1e', color: '#eee' }}
                                            />
                                        </label>
                                    </div>
                                    <textarea
                                        value={formData.warrior_notes ?? ''}
                                        onChange={(e) => setFormData({ ...formData, warrior_notes: e.target.value })}
                                        placeholder="Notes on bot's trades..."
                                        rows={2}
                                        style={{ width: '100%', padding: '6px', borderRadius: '4px', border: '1px solid #444', background: '#1e1e1e', color: '#eee', resize: 'vertical' }}
                                    />
                                </div>

                                {/* Context Section */}
                                <div style={{ marginBottom: '16px' }}>
                                    <label style={{ fontSize: '12px' }}>
                                        Market Context
                                        <textarea
                                            value={formData.market_context ?? ''}
                                            onChange={(e) => setFormData({ ...formData, market_context: e.target.value })}
                                            placeholder="Market conditions, sector moves, news..."
                                            rows={2}
                                            style={{ width: '100%', padding: '6px', borderRadius: '4px', border: '1px solid #444', background: '#1e1e1e', color: '#eee', resize: 'vertical' }}
                                        />
                                    </label>
                                </div>

                                <div style={{ marginBottom: '16px' }}>
                                    <label style={{ fontSize: '12px' }}>
                                        Lessons Learned
                                        <textarea
                                            value={formData.lessons ?? ''}
                                            onChange={(e) => setFormData({ ...formData, lessons: e.target.value })}
                                            placeholder="Key takeaways, adjustments for bot..."
                                            rows={2}
                                            style={{ width: '100%', padding: '6px', borderRadius: '4px', border: '1px solid #444', background: '#1e1e1e', color: '#eee', resize: 'vertical' }}
                                        />
                                    </label>
                                </div>

                                {/* Actions */}
                                <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
                                    <button
                                        onClick={() => setSelectedDate(null)}
                                        style={{ padding: '8px 16px', borderRadius: '4px', background: '#444', color: '#fff', border: 'none', cursor: 'pointer' }}
                                    >
                                        Cancel
                                    </button>
                                    <button
                                        onClick={saveNote}
                                        disabled={saving}
                                        style={{ padding: '8px 16px', borderRadius: '4px', background: '#3498db', color: '#fff', border: 'none', cursor: saving ? 'not-allowed' : 'pointer' }}
                                    >
                                        {saving ? 'Saving...' : 'Save'}
                                    </button>
                                </div>
                            </>
                        )}
                    </div>
                </div>
            )}
        </CollapsibleCard>
    )
}
