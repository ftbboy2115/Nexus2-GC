import type { AppProps } from 'next/app'
import Head from 'next/head'
import '@/styles/globals.css'
import Navbar from '@/components/Navbar'

export default function App({ Component, pageProps }: AppProps) {
    return (
        <div style={{ width: '100%', minHeight: '100vh', boxSizing: 'border-box' }}>
            <Head>
                <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1" />
            </Head>
            <Navbar />
            <Component {...pageProps} />
        </div>
    )
}
