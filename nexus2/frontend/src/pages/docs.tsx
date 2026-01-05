import { useState, useEffect } from 'react'
import Head from 'next/head'
import Link from 'next/link'
import styles from '@/styles/Docs.module.css'

export default function DocsPage() {
    const [markdown, setMarkdown] = useState<string>('')
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)

    useEffect(() => {
        async function fetchReadme() {
            try {
                const response = await fetch('http://localhost:8000/documentation/readme')
                if (response.ok) {
                    const text = await response.text()
                    setMarkdown(text)
                } else {
                    setError('Failed to load documentation')
                }
            } catch (err) {
                setError('Could not connect to backend')
            } finally {
                setLoading(false)
            }
        }
        fetchReadme()
    }, [])

    // Simple markdown to HTML conversion for display
    const renderMarkdown = (md: string) => {
        let html = md
            // Headers
            .replace(/^### (.+)$/gm, '<h3>$1</h3>')
            .replace(/^## (.+)$/gm, '<h2>$1</h2>')
            .replace(/^# (.+)$/gm, '<h1>$1</h1>')
            // Bold and italic
            .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.+?)\*/g, '<em>$1</em>')
            // Code blocks
            .replace(/```(\w+)?\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>')
            // Inline code
            .replace(/`([^`]+)`/g, '<code>$1</code>')
            // Links
            .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>')
            // Horizontal rules
            .replace(/^---$/gm, '<hr />')
            // Lists
            .replace(/^- (.+)$/gm, '<li>$1</li>')
            // Tables (simplified)
            .replace(/^\|(.+)\|$/gm, (match, content) => {
                if (content.includes('---')) return '' // Skip header separator
                const cells = content.split('|').map((c: string) => c.trim())
                return '<tr>' + cells.map((c: string) => `<td>${c}</td>`).join('') + '</tr>'
            })
            // Line breaks
            .replace(/\n\n/g, '</p><p>')
            .replace(/\n/g, '<br />')

        // Wrap in paragraph if needed
        if (!html.startsWith('<')) {
            html = '<p>' + html + '</p>'
        }

        return html
    }

    return (
        <>
            <Head>
                <title>Documentation - Nexus 2</title>
                <meta name="description" content="Nexus 2 documentation" />
                <meta name="viewport" content="width=device-width, initial-scale=1" />
            </Head>

            <main className={styles.main}>
                <header className={styles.header}>
                    <div className={styles.headerLeft}>
                        <h1 className={styles.title}>📚 Documentation</h1>
                        <Link href="/" className={styles.navLink}>
                            🏠 Dashboard
                        </Link>
                        <Link href="/automation" className={styles.navLink}>
                            🤖 Automation
                        </Link>
                        <Link href="/scanner" className={styles.navLink}>
                            🔍 Scanner
                        </Link>
                    </div>
                    <div className={styles.headerRight}>
                        <button
                            className={styles.refreshBtn}
                            onClick={() => window.location.reload()}
                        >
                            🔄 Refresh
                        </button>
                    </div>
                </header>

                <div className={styles.content}>
                    {loading && (
                        <div className={styles.loading}>Loading documentation...</div>
                    )}

                    {error && (
                        <div className={styles.error}>{error}</div>
                    )}

                    {!loading && !error && (
                        <article
                            className={styles.markdown}
                            dangerouslySetInnerHTML={{ __html: renderMarkdown(markdown) }}
                        />
                    )}
                </div>
            </main>
        </>
    )
}
