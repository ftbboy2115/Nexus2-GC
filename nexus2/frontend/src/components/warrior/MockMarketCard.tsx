/**
 * MockMarketCard - Test case selector and price simulation controls
 */
import styles from '@/styles/Warrior.module.css'
import { CollapsibleCard } from './CollapsibleCard'

interface TestCase {
    id: string
    symbol: string
    description: string
}

interface MockMarketCardProps {
    testCases: TestCase[]
    selectedTestCase: string
    setSelectedTestCase: (id: string) => void
    loadedTestCase: { symbol: string; price: number } | null
    loadTestCase: () => void
    setMockPrice: (symbol: string, price: number) => void
    actionLoading: string | null
}

export function MockMarketCard({
    testCases,
    selectedTestCase,
    setSelectedTestCase,
    loadedTestCase,
    loadTestCase,
    setMockPrice,
    actionLoading,
}: MockMarketCardProps) {
    return (
        <CollapsibleCard
            id="mockmarket"
            title="🎮 Mock Market"
            badge={loadedTestCase ? <span className={styles.badge}>{loadedTestCase.symbol}</span> : undefined}
        >
            <div className={styles.cardBody}>
                {/* Test Case Selector */}
                <div className={styles.testCaseSelector}>
                    <select
                        value={selectedTestCase}
                        onChange={(e) => setSelectedTestCase(e.target.value)}
                        className={styles.selectInput}
                        title={testCases.find(tc => tc.id === selectedTestCase)?.description || ''}
                    >
                        <option value="">Select a test case...</option>
                        {testCases.map((tc) => (
                            <option key={tc.id} value={tc.id}>
                                {tc.symbol} - {tc.description.length > 40 ? tc.description.slice(0, 40) + '...' : tc.description}
                            </option>
                        ))}
                    </select>
                    <button
                        onClick={loadTestCase}
                        className={styles.btnPrimary}
                        disabled={!selectedTestCase || actionLoading === 'loadTest'}
                        style={{ flexShrink: 0 }}
                    >
                        {actionLoading === 'loadTest' ? '...' : '📦 Load'}
                    </button>
                </div>

                {/* Price Controls */}
                {loadedTestCase && loadedTestCase.price != null && (
                    <div className={styles.priceControls}>
                        <div className={styles.priceDisplay}>
                            <span className={styles.priceLabel}>Price:</span>
                            <span className={styles.priceValue}>${loadedTestCase.price.toFixed(2)}</span>
                        </div>
                        <div className={styles.priceButtons}>
                            <button onClick={() => setMockPrice(loadedTestCase.symbol, loadedTestCase.price - 0.10)} className={styles.btnSmall}>-10¢</button>
                            <button onClick={() => setMockPrice(loadedTestCase.symbol, loadedTestCase.price - 0.05)} className={styles.btnSmall}>-5¢</button>
                            <button onClick={() => setMockPrice(loadedTestCase.symbol, loadedTestCase.price + 0.05)} className={styles.btnSmall}>+5¢</button>
                            <button onClick={() => setMockPrice(loadedTestCase.symbol, loadedTestCase.price + 0.10)} className={styles.btnSmall}>+10¢</button>
                            <button onClick={() => setMockPrice(loadedTestCase.symbol, loadedTestCase.price + 0.25)} className={styles.btnPrimary}>+25¢ 🚀</button>
                        </div>
                    </div>
                )}

                {!loadedTestCase && !selectedTestCase && (
                    <p className={styles.emptyMessage}>
                        Select a test case to simulate price movements
                    </p>
                )}
            </div>
        </CollapsibleCard>
    )
}
