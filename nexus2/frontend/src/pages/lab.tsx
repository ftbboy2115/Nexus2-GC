import { useState, useEffect, useCallback } from 'react'
import Head from 'next/head'
import Link from 'next/link'
import styles from '@/styles/Lab.module.css'

// ============================================================================
// Types
// ============================================================================

interface Strategy {
    name: string
    versions: string[]
    latest: string
}

interface ExperimentResult {
    experiment_id: string
    base_strategy: string
    base_version: string
    total_iterations: number
    final_recommendation: string
    best_iteration: number | null
    best_score: number
    promoted_strategy: string | null
    iterations: IterationResult[]
}

interface IterationResult {
    iteration: number
    hypothesis: {
        hypothesis: string
        rationale: string
        confidence: number
    }
    code_valid: boolean
    validation_errors: string[]
    backtest_ran: boolean
    metrics: {
        win_rate?: number
        avg_r?: number
        total_trades?: number
    }
    evaluation: {
        improvement_score?: number
        absolute_score?: number
        recommendation?: string
        summary?: string
    }
    recommendation: string
    duration_seconds: number
}

// ============================================================================
// API Helper
// ============================================================================

const API_BASE = ''

async function fetchAPI(path: string, options?: RequestInit, timeoutMs: number = 30000) {
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), timeoutMs)

    try {
        const res = await fetch(`${API_BASE}${path}`, {
            ...options,
            signal: controller.signal,
        })
        clearTimeout(timeoutId)
        if (!res.ok) {
            throw new Error(`API error: ${res.status}`)
        }
        return res.json()
    } catch (err) {
        clearTimeout(timeoutId)
        if (err instanceof Error && err.name === 'AbortError') {
            throw new Error('Request timed out')
        }
        throw err
    }
}

// ============================================================================
// Main Component
// ============================================================================

export default function Lab() {
    // State
    const [strategies, setStrategies] = useState<Strategy[]>([])
    const [loading, setLoading] = useState(true)
    const [selectedStrategy, setSelectedStrategy] = useState<string>('')
    const [experimentRunning, setExperimentRunning] = useState(false)
    const [experimentResult, setExperimentResult] = useState<ExperimentResult | null>(null)
    const [eventLog, setEventLog] = useState<string[]>([])

    // Experiment config
    const [startDate, setStartDate] = useState(() => {
        const d = new Date()
        d.setDate(d.getDate() - 30)
        return d.toISOString().split('T')[0]
    })
    const [endDate, setEndDate] = useState(() => new Date().toISOString().split('T')[0])
    const [maxIterations, setMaxIterations] = useState(3)
    const [initialCapital, setInitialCapital] = useState(25000)

    // GENERATE mode state
    const [experimentMode, setExperimentMode] = useState<'iterate' | 'explore' | 'generate'>('iterate')
    const [methodology, setMethodology] = useState('warrior')
    const [userIdea, setUserIdea] = useState('')
    const [guardrails, setGuardrails] = useState({
        maxRisk: 500,
        maxPositions: 5,
    })

    // Add to log
    const addToLog = useCallback((msg: string) => {
        const timestamp = new Date().toLocaleTimeString()
        setEventLog(prev => [`[${timestamp}] ${msg}`, ...prev.slice(0, 49)])
    }, [])

    // Fetch strategies - as useCallback so we can call it on demand
    const fetchStrategies = useCallback(async () => {
        try {
            const data = await fetchAPI('/lab/strategies')
            setStrategies(data.strategies || [])
            if (data.strategies?.length > 0 && !selectedStrategy) {
                setSelectedStrategy(data.strategies[0].name)
            }
            setLoading(false)
        } catch (err) {
            console.error('Failed to fetch strategies:', err)
            addToLog('❌ Failed to fetch strategies')
            setLoading(false)
        }
    }, [addToLog, selectedStrategy])

    // Fetch strategies on mount
    useEffect(() => {
        fetchStrategies()
    }, [fetchStrategies])

    // Run experiment
    const runExperiment = async () => {
        // For iterate/explore, need a base strategy
        if (experimentMode !== 'generate' && !selectedStrategy) return

        setExperimentRunning(true)
        setExperimentResult(null)

        const modeLabel = experimentMode.toUpperCase()
        const targetLabel = experimentMode === 'generate' ? methodology : selectedStrategy
        addToLog(`🚀 Starting ${modeLabel} experiment for ${targetLabel}...`)

        try {
            // Build request body based on mode
            const requestBody: Record<string, unknown> = {
                mode: experimentMode,
                start_date: startDate,
                end_date: endDate,
                initial_capital: initialCapital,
                max_iterations: maxIterations,
                promotion_threshold: 0.6,
            }

            // Add base strategy for iterate/explore modes
            if (experimentMode !== 'generate') {
                requestBody.base_strategy_name = selectedStrategy
            }

            // Add generate config for generate mode
            if (experimentMode === 'generate') {
                requestBody.generate_config = {
                    methodology: methodology,
                    user_idea: userIdea || null,
                    strategies_per_iteration: 3,
                    min_trades_per_strategy: 30,
                }
            }

            // Start the experiment (returns immediately with experiment_id)
            const startData = await fetchAPI('/lab/experiment', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(requestBody),
            }, 30000)  // 30 second timeout for the initial request

            const experimentId = startData.experiment_id
            addToLog(`📋 Experiment ID: ${experimentId} - polling for status...`)

            // Poll for status until complete
            let attempts = 0
            const maxAttempts = 120  // 6 minutes max (120 * 3 seconds)

            while (attempts < maxAttempts) {
                await new Promise(resolve => setTimeout(resolve, 3000))  // Wait 3 seconds

                try {
                    const status = await fetchAPI(`/lab/experiment/${experimentId}/status`, {}, 10000)

                    if (status.status === 'completed') {
                        setExperimentResult(status.result)
                        addToLog(`✅ Experiment complete: ${status.result.final_recommendation}`)
                        break
                    } else if (status.status === 'failed') {
                        addToLog(`❌ Experiment failed: ${status.error}`)
                        break
                    } else {
                        // Still running - update progress
                        if (attempts % 5 === 0) {
                            addToLog(`⏳ Still running... (iteration ${status.current_iteration}/${status.max_iterations})`)
                        }
                    }
                } catch (pollErr) {
                    console.warn('Poll error:', pollErr)
                    // Continue polling even if one poll fails
                }

                attempts++
            }

            if (attempts >= maxAttempts) {
                addToLog('⚠️ Experiment timed out - check lab.log for results')
            }
        } catch (err) {
            console.error('Experiment failed:', err)
            addToLog('❌ Failed to start experiment')
        } finally {
            setExperimentRunning(false)
        }
    }

    // Generate hypothesis only
    const generateHypothesis = async () => {
        if (!selectedStrategy) return

        addToLog(`🔬 Generating hypothesis for ${selectedStrategy}...`)
        try {
            const data = await fetchAPI('/lab/agents/research', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    strategy_name: selectedStrategy,
                }),
            })
            addToLog(`💡 Hypothesis: ${data.hypothesis}`)
        } catch (err) {
            addToLog('❌ Failed to generate hypothesis')
        }
    }

    // ========================================================================
    // Render
    // ========================================================================

    return (
        <>
            <Head>
                <title>R&D Lab | Nexus 2</title>
            </Head>

            <main className={styles.container}>
                {/* Header */}
                <header className={styles.header}>
                    <div className={styles.headerLeft}>
                        <Link href="/automation" className={styles.backLink}>← Automation</Link>
                        <h1>🧪 R&D Lab</h1>
                        <span className={styles.subtitle}>Strategy Discovery Engine</span>
                    </div>
                    <div className={styles.headerRight}>
                        <span className={styles.badge}>
                            {strategies.length} Strategies
                        </span>
                    </div>
                </header>

                {loading ? (
                    <div className={styles.loading}>Loading Lab...</div>
                ) : (
                    <>
                        <div className={styles.grid}>
                            {/* Strategy Selection Card */}
                            <div className={styles.card}>
                                <div className={styles.cardHeader}>
                                    <h2>📋 Strategies</h2>
                                    <button
                                        className={styles.refreshButton}
                                        onClick={() => { addToLog('🔄 Refreshing strategies...'); fetchStrategies(); }}
                                        title="Refresh strategies list"
                                    >
                                        🔄
                                    </button>
                                </div>
                                <div className={styles.cardContent}>
                                    <select
                                        value={selectedStrategy}
                                        onChange={e => setSelectedStrategy(e.target.value)}
                                        className={styles.select}
                                    >
                                        {strategies.map(s => (
                                            <option key={s.name} value={s.name}>
                                                {s.name} (v{s.latest})
                                            </option>
                                        ))}
                                    </select>
                                    <div className={styles.strategyList}>
                                        {strategies.map(s => (
                                            <div
                                                key={s.name}
                                                className={`${styles.strategyItem} ${selectedStrategy === s.name ? styles.selected : ''}`}
                                                onClick={() => setSelectedStrategy(s.name)}
                                            >
                                                <strong>{s.name}</strong>
                                                <span className={styles.versionBadge}>v{s.latest}</span>
                                                <span className={styles.versionCount}>{s.versions.length} versions</span>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            </div>

                            {/* Experiment Config Card */}
                            <div className={styles.card}>
                                <h2>⚙️ Experiment Config</h2>
                                <div className={styles.cardContent}>
                                    {/* Experiment Mode */}
                                    <div className={styles.formRow}>
                                        <label>Mode</label>
                                        <select
                                            value={experimentMode}
                                            onChange={e => setExperimentMode(e.target.value as 'iterate' | 'explore' | 'generate')}
                                            className={styles.select}
                                        >
                                            <option value="iterate">Iterate (Incremental)</option>
                                            <option value="explore">Explore (Bold)</option>
                                            <option value="generate">Generate (New Strategy)</option>
                                        </select>
                                    </div>

                                    {/* GENERATE mode specific inputs */}
                                    {experimentMode === 'generate' && (
                                        <>
                                            <div className={styles.formRow}>
                                                <label>Methodology</label>
                                                <select
                                                    value={methodology}
                                                    onChange={e => setMethodology(e.target.value)}
                                                    className={styles.select}
                                                >
                                                    <option value="warrior">Warrior (Ross Cameron)</option>
                                                    <option value="kk_ep">KK Episodic Pivot</option>
                                                    <option value="kk_breakout">KK Breakout</option>
                                                    <option value="kk_htf">KK High Tight Flag</option>
                                                    <option value="reversal">Reversal</option>
                                                    <option value="swing">Swing</option>
                                                    <option value="custom">Custom</option>
                                                </select>
                                            </div>
                                            <div className={styles.formRow}>
                                                <label>Strategy Idea (optional)</label>
                                                <textarea
                                                    value={userIdea}
                                                    onChange={e => setUserIdea(e.target.value)}
                                                    placeholder="Describe your strategy idea... e.g., 'A breakout strategy that enters when price breaks pre-market high with 2x volume, uses ATR stops, and targets 2R.'"
                                                    className={styles.textarea}
                                                    rows={3}
                                                />
                                            </div>
                                            <div className={styles.formRow}>
                                                <label>Max Risk ($)</label>
                                                <input
                                                    type="number"
                                                    value={guardrails.maxRisk}
                                                    onChange={e => setGuardrails(g => ({ ...g, maxRisk: parseInt(e.target.value) }))}
                                                    className={styles.input}
                                                    min={50}
                                                    max={5000}
                                                />
                                            </div>
                                            <div className={styles.formRow}>
                                                <label>Max Positions</label>
                                                <input
                                                    type="number"
                                                    value={guardrails.maxPositions}
                                                    onChange={e => setGuardrails(g => ({ ...g, maxPositions: parseInt(e.target.value) }))}
                                                    className={styles.input}
                                                    min={1}
                                                    max={20}
                                                />
                                            </div>
                                        </>
                                    )}
                                    <div className={styles.formRow}>
                                        <label>Start Date</label>
                                        <input
                                            type="date"
                                            value={startDate}
                                            onChange={e => setStartDate(e.target.value)}
                                            className={styles.input}
                                        />
                                    </div>
                                    <div className={styles.formRow}>
                                        <label>End Date</label>
                                        <input
                                            type="date"
                                            value={endDate}
                                            onChange={e => setEndDate(e.target.value)}
                                            className={styles.input}
                                        />
                                    </div>
                                    <div className={styles.formRow}>
                                        <label>Initial Capital</label>
                                        <input
                                            type="number"
                                            value={initialCapital}
                                            onChange={e => setInitialCapital(parseInt(e.target.value))}
                                            className={styles.input}
                                        />
                                    </div>
                                    <div className={styles.formRow}>
                                        <label>Max Iterations</label>
                                        <input
                                            type="number"
                                            value={maxIterations}
                                            min={1}
                                            max={20}
                                            onChange={e => setMaxIterations(parseInt(e.target.value))}
                                            className={styles.input}
                                        />
                                    </div>
                                </div>
                            </div>

                            {/* Actions Card */}
                            <div className={styles.card}>
                                <h2>🎯 Actions</h2>
                                <div className={styles.cardContent}>
                                    <button
                                        onClick={runExperiment}
                                        disabled={experimentRunning || (experimentMode !== 'generate' && !selectedStrategy)}
                                        className={styles.primaryBtn}
                                        title={experimentMode === 'generate'
                                            ? "Generate entirely new strategies using AI based on selected methodology"
                                            : "Run full iterative loop: Researcher → Coder → Backtest → Evaluator"}
                                    >
                                        {experimentRunning ? '⏳ Running...' :
                                            experimentMode === 'generate' ? '🧪 Generate Strategies' : '🚀 Run Experiment'}
                                    </button>
                                    {experimentMode !== 'generate' && (
                                        <button
                                            onClick={generateHypothesis}
                                            disabled={!selectedStrategy}
                                            className={styles.secondaryBtn}
                                            title="Generate a single hypothesis for strategy improvement using AI (without running backtest)."
                                        >
                                            💡 Generate Hypothesis
                                        </button>
                                    )}
                                </div>
                            </div>
                        </div>

                        {/* Experiment Results */}
                        {experimentResult && (
                            <div className={styles.resultsCard}>
                                <h2>📊 Experiment Results</h2>
                                <div className={styles.resultsHeader}>
                                    <span className={`${styles.resultBadge} ${styles[experimentResult.final_recommendation]}`}>
                                        {experimentResult.final_recommendation.toUpperCase()}
                                    </span>
                                    <span>Best Score: {(experimentResult.best_score * 100).toFixed(1)}%</span>
                                    <span>Iterations: {experimentResult.total_iterations}</span>
                                </div>

                                <div className={styles.iterationsTable}>
                                    <table>
                                        <thead>
                                            <tr>
                                                <th>#</th>
                                                <th>Hypothesis</th>
                                                <th>Valid</th>
                                                <th>Win Rate</th>
                                                <th>Avg R</th>
                                                <th title="Relative improvement over baseline">Δ Score</th>
                                                <th title="Absolute performance score">Abs</th>
                                                <th>Result</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {experimentResult.iterations.map(iter => (
                                                <tr key={iter.iteration}>
                                                    <td>{iter.iteration}</td>
                                                    <td className={styles.hypothesisCell}>
                                                        {iter.hypothesis.hypothesis.slice(0, 50)}...
                                                    </td>
                                                    <td>{iter.code_valid ? '✅' : '❌'}</td>
                                                    <td>{((iter.metrics.win_rate || 0) * 100).toFixed(1)}%</td>
                                                    <td>{iter.metrics.avg_r?.toFixed(2) || '-'}</td>
                                                    <td title="Relative improvement">{((iter.evaluation.improvement_score || 0) * 100).toFixed(1)}%</td>
                                                    <td title="Absolute performance">{((iter.evaluation.absolute_score || 0) * 100).toFixed(1)}%</td>
                                                    <td className={styles[iter.recommendation]}>
                                                        {iter.recommendation}
                                                    </td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        )}

                        {/* Event Log */}
                        <div className={styles.logCard}>
                            <div className={styles.logHeader}>
                                <h2>📜 Event Log</h2>
                                <button onClick={() => setEventLog([])} className={styles.clearBtn}>
                                    Clear
                                </button>
                            </div>
                            <div className={styles.logContent}>
                                {eventLog.length === 0 ? (
                                    <div className={styles.logEmpty}>No events yet</div>
                                ) : (
                                    eventLog.map((msg, i) => (
                                        <div key={i} className={styles.logEntry}>{msg}</div>
                                    ))
                                )}
                            </div>
                        </div>
                    </>
                )}
            </main>
        </>
    )
}
