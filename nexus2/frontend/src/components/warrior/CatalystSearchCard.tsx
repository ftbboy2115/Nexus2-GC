/**
 * CatalystSearchCard Component
 * 
 * Search catalyst headlines from the headline_cache.json file.
 * Provides a search box and results table for finding symbols by catalyst keywords.
 * 
 * API Endpoints:
 * - GET /catalyst/search?q={query}&limit={limit} - Search headlines
 * - GET /catalyst/stats - Get cache statistics
 * - GET /catalyst/recent - Get recent catalysts
 */
import React, { useState, useCallback } from 'react';
import styles from '../../styles/Warrior.module.css';
import { CollapsibleCard } from './CollapsibleCard';

interface CatalystResult {
    symbol: string;
    headline: string;
    source?: string;
    timestamp?: string;
    catalyst_type?: string;
    match_score: number;
}

interface SearchResponse {
    query: string;
    count: number;
    results: CatalystResult[];
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export const CatalystSearchCard: React.FC = () => {
    const [query, setQuery] = useState('');
    const [results, setResults] = useState<CatalystResult[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [searched, setSearched] = useState(false);

    const handleSearch = useCallback(async () => {
        if (!query.trim() || query.length < 2) {
            setError('Enter at least 2 characters');
            return;
        }

        setLoading(true);
        setError(null);
        setSearched(true);

        try {
            const res = await fetch(`${API_BASE}/catalyst/search?q=${encodeURIComponent(query)}&limit=50`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);

            const data: SearchResponse = await res.json();
            setResults(data.results);
        } catch (err: any) {
            setError(err.message || 'Search failed');
            setResults([]);
        } finally {
            setLoading(false);
        }
    }, [query]);

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter') handleSearch();
    };

    const handleClear = () => {
        setQuery('');
        setResults([]);
        setSearched(false);
        setError(null);
    };

    return (
        <CollapsibleCard id="catalyst-search" title="🔍 Catalyst Search">
            <div style={{ padding: '12px' }}>
                <div style={{ display: 'flex', gap: '8px', marginBottom: '12px' }}>
                    <input
                        type="text"
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                        onKeyDown={handleKeyDown}
                        placeholder="Search headlines... (FDA, earnings, partnership)"
                        style={{
                            flex: 1,
                            padding: '8px 12px',
                            borderRadius: '4px',
                            border: '1px solid #444',
                            background: '#2a2a2a',
                            color: '#eee',
                        }}
                    />
                    <button
                        onClick={handleSearch}
                        disabled={loading || query.length < 2}
                        style={{
                            padding: '8px 16px',
                            borderRadius: '4px',
                            background: loading ? '#444' : '#3498db',
                            color: '#fff',
                            border: 'none',
                            cursor: loading ? 'not-allowed' : 'pointer',
                        }}
                    >
                        {loading ? '...' : 'Search'}
                    </button>
                    {results.length > 0 && (
                        <button
                            onClick={handleClear}
                            style={{
                                padding: '8px 12px',
                                borderRadius: '4px',
                                background: '#666',
                                color: '#fff',
                                border: 'none',
                                cursor: 'pointer',
                            }}
                        >
                            Clear
                        </button>
                    )}
                </div>

                {error && <div style={{ color: '#e74c3c', marginBottom: '8px' }}>{error}</div>}

                {searched && !loading && (
                    <div style={{ marginBottom: '8px', color: '#888' }}>
                        {results.length} result{results.length !== 1 ? 's' : ''} for "{query}"
                    </div>
                )}

                {results.length > 0 && (
                    <div style={{ maxHeight: '300px', overflowY: 'auto' }}>
                        <table className={styles.table} style={{ fontSize: '12px' }}>
                            <thead>
                                <tr>
                                    <th style={{ width: '60px' }}>Symbol</th>
                                    <th>Headline</th>
                                    <th style={{ width: '80px' }}>Type</th>
                                </tr>
                            </thead>
                            <tbody>
                                {results.map((r, i) => (
                                    <tr key={i}>
                                        <td style={{ fontWeight: 600, color: '#3498db' }}>{r.symbol}</td>
                                        <td style={{
                                            whiteSpace: 'nowrap',
                                            overflow: 'hidden',
                                            textOverflow: 'ellipsis',
                                            maxWidth: '400px',
                                            color: r.match_score === 1 ? '#2ecc71' : '#bbb',
                                        }} title={r.headline}>
                                            {r.headline}
                                        </td>
                                        <td style={{ color: '#888' }}>{r.catalyst_type || '-'}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>
        </CollapsibleCard>
    );
};

export default CatalystSearchCard;

