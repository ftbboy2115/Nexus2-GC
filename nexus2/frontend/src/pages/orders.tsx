import { useState, useEffect, useCallback } from 'react'
import Head from 'next/head'
import Link from 'next/link'
import styles from '@/styles/Orders.module.css'

interface Order {
    id: string
    symbol: string
    side: string
    quantity: number
    filled_quantity: number
    order_type: string
    status: string
    limit_price: string | null
    stop_price: string | null
    avg_fill_price: string | null
    created_at: string
    submitted_at: string | null
    filled_at: string | null
}

interface OrdersResponse {
    orders: Order[]
    total: number
}

export default function Orders() {
    const [orders, setOrders] = useState<Order[]>([])
    const [loading, setLoading] = useState(true)
    const [filter, setFilter] = useState('all')
    const [demo, setDemo] = useState(false)  // Default to real data

    // Cancel confirmation modal
    const [cancelModal, setCancelModal] = useState<{ isOpen: boolean; orderId: string | null; symbol: string }>(
        { isOpen: false, orderId: null, symbol: '' }
    )
    const [cancelling, setCancelling] = useState(false)

    const generateDemoOrders = (): Order[] => {
        const symbols = ['NVDA', 'AAPL', 'META', 'TSLA', 'AMD', 'MSFT', 'GOOGL', 'AMZN']
        const statuses = ['filled', 'filled', 'filled', 'cancelled', 'filled']
        const now = new Date()

        return symbols.map((symbol, i) => {
            const status = statuses[i % statuses.length]
            const qty = Math.floor(Math.random() * 100) + 10
            const price = Math.round((50 + Math.random() * 400) * 100) / 100
            const fillPrice = status === 'filled' ? price + (Math.random() - 0.5) * 2 : null
            const createdAt = new Date(now.getTime() - (i + 1) * 24 * 60 * 60 * 1000)

            return {
                id: `demo-${i + 1}`,
                symbol,
                side: i % 3 === 0 ? 'sell' : 'buy',
                quantity: qty,
                filled_quantity: status === 'filled' ? qty : 0,
                order_type: i % 2 === 0 ? 'limit' : 'market',
                status,
                limit_price: i % 2 === 0 ? price.toFixed(2) : null,
                stop_price: (price * 0.95).toFixed(2),
                avg_fill_price: fillPrice ? fillPrice.toFixed(2) : null,
                created_at: createdAt.toISOString(),
                submitted_at: createdAt.toISOString(),
                filled_at: status === 'filled' ? createdAt.toISOString() : null,
            }
        })
    }

    const fetchOrders = useCallback(async () => {
        setLoading(true)

        if (demo) {
            // Use demo data
            setOrders(generateDemoOrders())
            setLoading(false)
            return
        }

        try {
            const response = await fetch('/api/orders')
            if (response.ok) {
                const data: OrdersResponse = await response.json()
                setOrders(data.orders)
            }
        } catch (err) {
            console.error('Failed to fetch orders:', err)
        } finally {
            setLoading(false)
        }
    }, [demo])

    useEffect(() => {
        fetchOrders()
    }, [fetchOrders])

    const filteredOrders = orders.filter(order => {
        if (filter === 'all') return true
        return order.status === filter
    })

    const getStatusColor = (status: string) => {
        switch (status) {
            case 'filled': return styles.statusFilled
            case 'cancelled': return styles.statusCancelled
            case 'rejected': return styles.statusRejected
            case 'pending': return styles.statusPending
            case 'submitted': return styles.statusSubmitted
            default: return styles.statusDraft
        }
    }

    const getSideColor = (side: string) => {
        return side === 'buy' ? styles.sideBuy : styles.sideSell
    }

    const formatDate = (dateStr: string | null) => {
        if (!dateStr) return '-'
        return new Date(dateStr).toLocaleString()
    }

    const handleCancelOrder = async (orderId: string) => {
        console.log('[Cancel] Attempting to cancel order:', orderId, 'demo:', demo)

        // Demo mode uses fake orders
        if (demo) {
            console.log('[Cancel] Demo mode is ON - showing alert')
            alert('Cannot cancel orders in demo mode. Turn off demo toggle to cancel real orders.')
            return
        }

        // Find the order to get symbol
        const order = orders.find(o => o.id === orderId)
        setCancelModal({ isOpen: true, orderId, symbol: order?.symbol || 'order' })
    }

    const confirmCancelOrder = async () => {
        if (!cancelModal.orderId) return

        setCancelling(true)
        console.log('[Cancel] Proceeding with cancel...')

        try {
            const response = await fetch(`/api/orders/${cancelModal.orderId}`, {
                method: 'DELETE',
            })
            console.log('[Cancel] Response status:', response.status)

            if (response.ok) {
                // Refresh orders list
                fetchOrders()
            } else {
                const err = await response.json()
                console.error('[Cancel] Error:', err)
                alert(`Failed to cancel: ${err.detail || 'Unknown error'}`)
            }
        } catch (err) {
            console.error('[Cancel] Exception:', err)
            alert('Failed to cancel order')
        } finally {
            setCancelling(false)
            setCancelModal({ isOpen: false, orderId: null, symbol: '' })
        }
    }

    const isCancellable = (status: string) => {
        return ['pending', 'submitted', 'draft'].includes(status.toLowerCase())
    }

    return (
        <>
            <Head>
                <title>Order History - Nexus 2</title>
                <meta name="description" content="View all orders" />
                <meta name="viewport" content="width=device-width, initial-scale=1" />
            </Head>

            <main className={styles.main}>
                <header className={styles.header}>
                    <div className={styles.headerLeft}>
                        <h1 className={styles.title}>📋 Order History</h1>
                        <Link href="/" className={styles.navLink}>
                            🏠 Dashboard
                        </Link>
                        <Link href="/scanner" className={styles.navLink}>
                            🔍 Scanner
                        </Link>
                        <Link href="/closed" className={styles.navLink}>
                            📊 Closed
                        </Link>
                    </div>
                    <div className={styles.headerRight}>
                        <select
                            className={styles.filterSelect}
                            value={filter}
                            onChange={(e) => setFilter(e.target.value)}
                        >
                            <option value="all">All Orders</option>
                            <option value="filled">Filled</option>
                            <option value="pending">Pending</option>
                            <option value="submitted">Submitted</option>
                            <option value="cancelled">Cancelled</option>
                            <option value="rejected">Rejected</option>
                            <option value="draft">Draft</option>
                        </select>
                        <label className={styles.demoToggle}>
                            <input
                                type="checkbox"
                                checked={demo}
                                onChange={(e) => setDemo(e.target.checked)}
                                disabled={loading}
                            />
                            Demo
                        </label>
                        <button
                            className={styles.refreshBtn}
                            onClick={fetchOrders}
                            disabled={loading}
                        >
                            {loading ? 'Loading...' : '🔄 Refresh'}
                        </button>
                    </div>
                </header>

                {loading && orders.length === 0 && (
                    <div className={styles.loading}>Loading orders...</div>
                )}

                {!loading && orders.length === 0 && (
                    <div className={styles.empty}>
                        <p>No orders yet</p>
                        <p className={styles.hint}>Execute a trade from the Scanner to create orders</p>
                    </div>
                )}

                {filteredOrders.length > 0 && (
                    <div className={styles.results}>
                        <div className={styles.summary}>
                            <span>Showing {filteredOrders.length} orders</span>
                            <span className={styles.total}>({orders.length} total)</span>
                        </div>

                        <div className={styles.tableContainer}>
                            <table className={styles.table}>
                                <thead>
                                    <tr>
                                        <th>Symbol</th>
                                        <th>Side</th>
                                        <th>Qty</th>
                                        <th>Filled</th>
                                        <th>Type</th>
                                        <th>Price</th>
                                        <th>Avg Fill</th>
                                        <th>Status</th>
                                        <th>Created</th>
                                        <th>Actions</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {filteredOrders.map((order) => (
                                        <tr key={order.id}>
                                            <td className={styles.symbol}>{order.symbol}</td>
                                            <td>
                                                <span className={`${styles.side} ${getSideColor(order.side)}`}>
                                                    {order.side.toUpperCase()}
                                                </span>
                                            </td>
                                            <td>{order.quantity}</td>
                                            <td>{order.filled_quantity}</td>
                                            <td>{order.order_type}</td>
                                            <td>
                                                {order.limit_price
                                                    ? `$${parseFloat(order.limit_price).toFixed(2)}`
                                                    : 'MKT'}
                                            </td>
                                            <td>
                                                {order.avg_fill_price
                                                    ? `$${parseFloat(order.avg_fill_price).toFixed(2)}`
                                                    : '-'}
                                            </td>
                                            <td>
                                                <span className={`${styles.status} ${getStatusColor(order.status)}`}>
                                                    {order.status}
                                                </span>
                                            </td>
                                            <td className={styles.date}>
                                                {formatDate(order.created_at)}
                                            </td>
                                            <td>
                                                {isCancellable(order.status) && (
                                                    <button
                                                        className={styles.cancelBtn}
                                                        onClick={() => handleCancelOrder(order.id)}
                                                    >
                                                        ✕ Cancel
                                                    </button>
                                                )}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>
                )}

                {/* Cancel Confirmation Modal */}
                {cancelModal.isOpen && (
                    <div className={styles.modalOverlay} onClick={() => setCancelModal({ isOpen: false, orderId: null, symbol: '' })}>
                        <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
                            <h3 className={styles.modalTitle}>Cancel Order</h3>
                            <p className={styles.modalText}>
                                Are you sure you want to cancel the order for <strong>{cancelModal.symbol}</strong>?
                            </p>
                            <div className={styles.modalActions}>
                                <button
                                    className={styles.modalCancelBtn}
                                    onClick={() => setCancelModal({ isOpen: false, orderId: null, symbol: '' })}
                                    disabled={cancelling}
                                >
                                    No, Keep Order
                                </button>
                                <button
                                    className={styles.modalConfirmBtn}
                                    onClick={confirmCancelOrder}
                                    disabled={cancelling}
                                >
                                    {cancelling ? 'Cancelling...' : 'Yes, Cancel Order'}
                                </button>
                            </div>
                        </div>
                    </div>
                )}
            </main>
        </>
    )
}
