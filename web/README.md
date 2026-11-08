# AICOR Frontend

React + TypeScript dashboard for comparing Microsoft (MSFT) and Alphabet (GOOGL). The UI reads the checked-in JSON datasets under `public/data/`; it can also use the backend API when available.

## Requirements

- Node.js and npm
- Python backend is optional for static-data development; when running, Vite proxies `/api/*` to `http://127.0.0.1:8000`.

## Run locally

From the repository root, start the backend in one terminal if needed:

```powershell
python -m backend
```

In another terminal:

```powershell
cd web
npm ci
npm run dev
```

Vite serves the frontend at `http://localhost:5173`. If the backend is offline, datasets fall back to `web/public/data/*.json`; the top bar indicates the degraded/stale state.

## Validate

```powershell
cd web
npm run typecheck
npm test
npm run test:e2e
npm run build
```

Playwright tests cover Desktop Chrome and Mobile Chrome; the viewport test checks 360, 768, and 1440 pixels. E2E tests include static API fallback and a simulated SSE `snapshot changed=true` event.

## Production build

```powershell
cd web
npm run build
```

The static output is `web/dist/`. For a static host such as Vercel, set `web/` as the project root and `dist` as the output directory. Static hosting serves the bundled JSON fallback but does not provide `/api/*` or live SSE unless a backend/proxy is configured separately. Do not expose or add refresh secrets to the frontend.

## Handoff status

See [`PROGRESS.md`](./PROGRESS.md), [`GAPS.md`](./GAPS.md), and [`FINAL_REPORT.md`](./FINAL_REPORT.md). Screenshots from the final UI pass are in [`evidence/`](./evidence/).
