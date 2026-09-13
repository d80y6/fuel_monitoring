# FuelOps SCADA (web)

React + Vite + TypeScript frontend for the fuel monitoring platform.

## Development

```bash
npm install
npm run dev      # Vite dev server on :5173, proxies /api + /ws to :8000
npm test         # Vitest (jsdom), single run
npm run build    # tsc --noEmit && vite build
```

Requires the backend stack (`docker compose up -d db redis api ingest`) with
`npm run dev` proxying API + WebSocket traffic to `localhost:8000`.

## Deployment

`docker compose up -d web` builds `web/` into an nginx image on :8080; the
reverse proxy in `infra/nginx/conf.d/app.conf` forwards `location /` there
for HTTP+WS, while static assets are served directly by the nginx container.

## Architecture notes

- Zustand persist (localStorage key `fuel.auth`) for the JWT bearer token.
- `src/api/ws.ts` — token-auth WebSocket client for `/ws/telemetry` and
  `/ws/alarms` with exponential reconnect (1s→30s).
- `src/lib/tankGeometry.ts` — TS port of the backend tank-geometry engine for
  live SVG visualization (matches backend fixtures via tests).
- TanStack Query for REST; dual-axis ECharts (GOV/NSV vs temperature/density).

## Theming

- **Toggle**: Light / System / Dark switch in the app header, persisted under
  localStorage key `fmp-theme`.
- **Tokens**: semantic Tailwind classes with no per-element `.dark:` overrides —
  surface/inset containers (`bg-surface`, `bg-inset`), text ranks (`text-primary`,
  `text-secondary`, `text-muted`), hairlines (`border-line`, `border-line-strong`),
  and status tokens (`text-danger-fg`, `text-ok-fg`, `text-warn-fg`, `text-info-fg`).
- **Switching**: System follows `prefers-color-scheme`; the resolved scheme flips a
  `.dark` class on `<html>` (Tailwind `darkMode: 'class'`), which drives the tokens.
- **Charts**: ECharts themes `fmp-light` / `fmp-dark` are applied via the resolved
  scheme so series, axes, and tooltips match the current mode.
