import type { AppProps } from 'next/app'
import Head from 'next/head'
import '@/styles/globals.css'
import '@/styles/global-loading.css'
import Navbar from '@/components/Navbar'
import { LoadingProvider } from '@/components/GlobalLoadingBar'

export default function App({ Component, pageProps }: AppProps) {
    return (
        <LoadingProvider>
            <Head>
                <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1" />
            </Head>
            <Navbar />
            <Component {...pageProps} />
        </LoadingProvider>
    )
}
