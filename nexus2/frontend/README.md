# Nexus 2 Frontend

Minimal Next.js dashboard for the Nexus 2 trading platform.

## Setup

```bash
cd nexus2/frontend
npm install
```

## Development

**1. Start the backend API first:**
```bash
# From project root
uvicorn nexus2.api.main:app --reload
```

**2. Start the frontend:**
```bash
cd nexus2/frontend
npm run dev
```

**3. Open browser:**
```
http://localhost:3000
```

## Features

- Health check display
- Open positions table
- Dark theme

## Proxy

API requests to `/api/*` are proxied to `http://localhost:8000/*` (the FastAPI backend).
