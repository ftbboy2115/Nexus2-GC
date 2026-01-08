/** @type {import('next').NextConfig} */
const nextConfig = {
    reactStrictMode: true,
    async rewrites() {
        return [
            // Proxy all backend API calls through Next.js to avoid CORS/localhost issues
            {
                source: '/automation/:path*',
                destination: 'http://localhost:8000/automation/:path*',
            },
            {
                source: '/positions/:path*',
                destination: 'http://localhost:8000/positions/:path*',
            },
            {
                source: '/positions',
                destination: 'http://localhost:8000/positions',
            },
            {
                source: '/settings',
                destination: 'http://localhost:8000/settings',
            },
            {
                source: '/health',
                destination: 'http://localhost:8000/health',
            },
            {
                source: '/api/:path*',
                destination: 'http://localhost:8000/:path*',
            },
            {
                source: '/ws/:path*',
                destination: 'http://localhost:8000/ws/:path*',
            },
        ]
    },
}

module.exports = nextConfig
