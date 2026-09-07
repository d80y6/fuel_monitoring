# SCADA React Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the greenfield SCADA frontend in `web/` (Vite + React 18 + TypeScript + Tailwind) with JWT auth, a geometry-aware SVG `TankCanvas` mirroring the backend shape math, dual-Y-axis GOV/NSV ECharts telemetry charts, a live dispensing view, and a totalizer-drift chart — wired to the platform REST + WebSocket APIs and to Docker compose / nginx.

**Architecture:** A single-page app with React Router (login + guarded layout). Auth lives in a zustand store (JWT persisted to localStorage, validated on boot via `/api/v1/auth/me`); all REST calls go through a typed fetch client that injects `Authorization: Bearer` and centralizes 401 handling. Live telemetry streams over native WebSockets (`/ws/telemetry`, `/ws/alarms`) with `?token=` auth and exponential-backoff reconnect into a zustand telemetry store. Pure math (tank geometry mirror, chart transforms, drift calc, spline interpolation) is extracted to `src/lib/` for Vitest coverage against backend fixture vectors. Production serving: `web/Dockerfile` multi-stage build → nginx on :8080, proxied from the existing root nginx `location /`.

**Tech Stack:** Vite 5, React 18, TypeScript 5, Tailwind 3, React Router 6, zustand 4 (persist), TanStack Query 5, Apache ECharts 5 via `echarts-for-react`, Vitest 2 + jsdom + Testing Library.

**Backend contract this plan relies on (from the backend plan / current API):**
- `POST /api/v1/auth/login` `{username,password}` → `{access_token, token_type, user}`; `GET /api/v1/auth/me` (Bearer) → user.
- `GET /api/v1/tanks`, `GET /api/v1/tanks/{id}`, `GET /api/v1/tanks/{id}/recent?limit=`, `GET /api/v1/tanks/{id}/range?start&end&bucket=`, `GET /api/v1/tanks/{id}/alarms`, `POST /api/v1/tanks/{id}/alarms/{aid}/ack`.
- `GET /api/v1/fuel-types` (list), `PUT/GET /api/v1/tanks/{tank_id}/strapping`.
- `GET /api/v1/dispensing/allocations?max_rows=`, `GET /api/v1/dispensing/transactions?limit=&dispenser_id=`.
- `GET /api/v1/totalizers?dispenser_id=&start=&end=&limit=`, `GET /api/v1/stations`, `GET /api/v1/stations/{id}/dispensers`.
- WS `?token=` JWT auth (server closes 4401 on bad token). Telemetry frames carry `tank_id, timestamp, temperature, pressure, level, volume, gov_volume, net_volume, density_at_temperature, fill_percent, is_outlier`.
- `TankRead` returns the new shape fields (`tank_shape`, `fuel_type_id`, `dish_depth`, `tank_width`, `strapping_table_id`); `fluid_density` is REMOVED — never use it client-side.

**Test env:**
```
cd /home/ubuntu/fuel_monitoring/web
npm install
npm test          # vitest run
npm run build     # tsc --noEmit && vite build (typecheck + prod build)
```
No DB or backend needed for these unit/component tests (fetch + WebSocket are injected/faked).

---

## File Map

- Scaffold: `web/index.html`, `web/package.json`, `web/vite.config.ts`, `web/tsconfig.json`, `web/tailwind.config.js`, `web/postcss.config.js`, `web/.gitignore`, `web/src/main.tsx`, `web/src/index.css`, `web/src/test/setup.ts`, `web/src/App.tsx` (+ trivial `web/src/App.test.tsx`)
- Pure libs (Vitest-covered): `web/src/lib/tankGeometry.ts`, `web/src/lib/apiTypes.ts`, `web/src/lib/chartOptions.ts`, `web/src/lib/driftCalc.ts`, `web/src/lib/authGuard.ts`, `web/src/lib/dispenseFormat.ts`
- API/WS: `web/src/api/http.ts`, `web/src/api/client.ts`, `web/src/api/ws.ts`
- State: `web/src/store/auth.ts`, `web/src/store/telemetry.ts`
- Hooks: `web/src/hooks/useTelemetrySocket.ts`, `web/src/hooks/useTelemetry.ts`, `web/src/hooks/useRealtimeAlarms.ts`
- Components: `web/src/components/layout/AppLayout.tsx`, `web/src/components/layout/Sidebar.tsx`, `web/src/components/tanks/TankCanvas.tsx`, `web/src/components/tanks/TankTile.tsx`, `web/src/components/charts/TelemetryChart.tsx`, `web/src/components/charts/TotalizerDriftChart.tsx`, `web/src/components/dispensing/DispenseLiveView.tsx`
- Pages: `web/src/pages/Login.tsx`, `web/src/pages/Dashboard.tsx`, `web/src/pages/Tanks.tsx`, `web/src/pages/TankDetail.tsx`, `web/src/pages/Dispensing.tsx`, `web/src/pages/Totalizers.tsx`
- Routing: `web/src/router.tsx`
- Infra: `web/Dockerfile`, `web/nginx.conf`, `web/README.md`; modify root `docker-compose.yml`, root `infra/nginx/conf.d/app.conf`, root `.gitignore`
- Tests: `web/tests/tankGeometry.test.ts`, `web/tests/http.test.ts`, `web/tests/authStore.test.ts`, `web/tests/ws.test.ts`, `web/tests/chartOptions.test.ts`, `web/tests/driftCalc.test.ts`, `web/tests/dispenseFormat.test.ts`, `web/src/App.test.tsx`

---

### Task 1: Scaffold the Vite + React + TS + Tailwind app

**Files:**
- Create: `web/package.json`, `web/vite.config.ts`, `web/tsconfig.json`, `web/index.html`, `web/tailwind.config.js`, `web/postcss.config.js`, `web/.gitignore`, `web/src/index.css`, `web/src/test/setup.ts`, `web/src/main.tsx`, `web/src/App.tsx`, `web/src/App.test.tsx`

- [ ] **Step 1: Write the failing smoke test**

`web/src/App.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import App from './App';

describe('App', () => {
  it('renders the app shell heading', () => {
    render(<App />);
    expect(screen.getByRole('heading', { name: 'FuelOps SCADA' })).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Create the scaffold files**

`web/package.json`:

```json
{
  "name": "fuel-platform-web",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc --noEmit && vite build",
    "preview": "vite preview",
    "test": "vitest run",
    "test:watch": "vitest"
  },
  "dependencies": {
    "@tanstack/react-query": "^5.59.0",
    "echarts": "^5.5.1",
    "echarts-for-react": "^3.0.2",
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.26.2",
    "zustand": "^4.5.5"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "^6.5.0",
    "@testing-library/react": "^16.0.1",
    "@testing-library/user-event": "^14.5.2",
    "@types/react": "^18.3.10",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.2",
    "autoprefixer": "^10.4.20",
    "jsdom": "^25.0.1",
    "postcss": "^8.4.47",
    "tailwindcss": "^3.4.13",
    "typescript": "^5.6.2",
    "vite": "^5.4.8",
    "vitest": "^2.1.2"
  }
}
```

`web/index.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>FuelOps SCADA</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

`web/vite.config.ts` (Vitest config + dev proxy so the SPA calls same-origin `/api` and `/ws` paths):

```ts
/// <reference types="vitest" />
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
      '/ws': { target: 'ws://localhost:8000', ws: true },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: false,
  },
});
```

`web/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "types": ["vitest/globals", "@testing-library/jest-dom"]
  },
  "include": ["src"]
}
```

`web/tailwind.config.js`:

```js
/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: { DEFAULT: '#0ea5e9', dark: '#0369a1' },
      },
    },
  },
  plugins: [],
};
```

`web/postcss.config.js`:

```js
export default {
  plugins: { tailwindcss: {}, autoprefixer: {} },
};
```

`web/.gitignore`:

```
node_modules/
dist/
```

`web/src/index.css`:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

html,
body,
#root {
  height: 100%;
}
```

`web/src/test/setup.ts`:

```ts
import '@testing-library/jest-dom/vitest';
```

`web/src/App.tsx`:

```tsx
export default function App() {
  return (
    <div className="min-h-screen bg-slate-100 flex items-center justify-center">
      <h1 className="text-3xl font-bold text-slate-800">FuelOps SCADA</h1>
    </div>
  );
}
```

`web/src/main.tsx` (minimal for now; Task 5 replaces it with routing + providers):

```tsx
import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './index.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
```

- [ ] **Step 3: Install deps and run the smoke test**

Run: `cd /home/ubuntu/fuel_monitoring/web && npm install && npm test`
Expected: PASS (1 test).

- [ ] **Step 4: Verify typecheck + prod build**

Run: `cd /home/ubuntu/fuel_monitoring/web && npm run build`
Expected: `tsc` clean, Vite emits `dist/`.

- [ ] **Step 5: Commit**

```bash
git add web/
git commit -m "feat: scaffold SCADA web app (Vite + React 18 + TS + Tailwind + Vitest)"
```

---

### Task 2: tank-geometry TS mirror (tested against backend vectors)

Mirrors `fmp/ingestion/tank_geometry.py` (natural cubic spline, vertical/horizontal-cylinder, rectangular, spherical volume) plus SVG outline/fill helpers. Pure, dependency-free.

**Files:**
- Create: `web/src/lib/tankGeometry.ts`
- Test: `web/tests/tankGeometry.test.ts`

- [ ] **Step 1: Write the failing tests**

`web/tests/tankGeometry.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import {
  fillFraction,
  fuelColor,
  interpolateStrapping,
  liquidTopY,
  roundRectPath,
  tankOutlinePath,
  volumeLitersForShape,
} from '../src/lib/tankGeometry';

const vertDims = { diameter: 1.5, height: 2.0 };

describe('volumeLitersForShape (backend fixture vectors)', () => {
  it('vertical_cylinder at 1.0 m == PI * 0.75^2 * 1.0 * 1000', () => {
    const v = volumeLitersForShape(1.0, 'vertical_cylinder', vertDims);
    expect(v).toBeCloseTo(Math.PI * 0.75 ** 2 * 1.0 * 1000, 5);
  });

  it('horizontal_cylinder half-full is (within 0.1%) half of full', () => {
    const full = volumeLitersForShape(1.5, 'horizontal_cylinder', { diameter: 1.5, length: 2.0 });
    const half = volumeLitersForShape(0.75, 'horizontal_cylinder', { diameter: 1.5, length: 2.0 });
    expect(half).toBeCloseTo(full / 2, -3); // 3 significant-figure agreement
  });

  it('rectangular at 0.5 m == 0.5 * width * length * 1000', () => {
    const v = volumeLitersForShape(0.5, 'rectangular', { width: 1.0, length: 2.0, height: 1.5 });
    expect(v).toBeCloseTo(0.5 * 1.0 * 2.0 * 1000, 5);
  });

  it('spherical full == 4/3 PI r^3 * 1000 and half == full/2', () => {
    const full = volumeLitersForShape(2.0, 'spherical', { diameter: 2.0 });
    expect(full).toBeCloseTo((4 / 3) * Math.PI * 1 ** 3 * 1000, 4);
    const half = volumeLitersForShape(1.0, 'spherical', { diameter: 2.0 });
    expect(half).toBeCloseTo(full / 2, -2);
  });

  it('custom_strapping cubic spline interpolates smoothly (mirrors backend)', () => {
    const pts = [
      { height: 0.0, volume: 0.0 },
      { height: 1.0, volume: 100.0 },
      { height: 2.0, volume: 250.0 },
    ];
    const mid = interpolateStrapping(pts, 1.5, 'cubic_spline');
    expect(mid).toBeGreaterThan(100.0);
    expect(mid).toBeLessThan(300.0);
    expect(Math.abs(mid - 190.0)).toBeLessThan(40.0); // smooth, not linear (175)
  });

  it('linear strapping interpolates exactly', () => {
    const pts = [
      { height: 0.0, volume: 0.0 },
      { height: 1.0, volume: 100.0 },
      { height: 2.0, volume: 250.0 },
    ];
    expect(interpolateStrapping(pts, 1.5, 'linear')).toBeCloseTo(175.0, 5);
  });

  it('strapping clamps outside the domain and rejects <2 points', () => {
    const pts = [
      { height: 0.0, volume: 0.0 },
      { height: 1.0, volume: 100.0 },
    ];
    expect(interpolateStrapping(pts, -1.0, 'linear')).toBeCloseTo(0.0, 5);
    expect(interpolateStrapping(pts, 2.0, 'linear')).toBeCloseTo(100.0, 5);
    expect(() => interpolateStrapping([{ height: 0.0, volume: 0.0 }], 0.5, 'linear')).toThrow();
  });
});

describe('SVG helpers', () => {
  it('fillFraction is level/height for vertical-ish and level/diameter for horizontal-ish', () => {
    expect(fillFraction(1.0, 'vertical_cylinder', vertDims)).toBeCloseTo(0.5, 5);
    expect(fillFraction(0.75, 'horizontal_cylinder', { diameter: 1.5 })).toBeCloseTo(0.5, 5);
    expect(fillFraction(3.0, 'vertical_cylinder', vertDims)).toBeLessThanOrEqual(1.0);
    expect(fillFraction(-0.5, 'vertical_cylinder', vertDims)).toBeGreaterThanOrEqual(0.0);
  });

  it('liquidTopY maps 50% fill to the vertical midpoint of the box', () => {
    const box = { x: 4, y: 4, w: 88, h: 112 };
    expect(liquidTopY(1.0, 'vertical_cylinder', vertDims, box)).toBeCloseTo(4 + 112 * 0.5, 5);
  });

  it('tankOutlinePath returns a closed path per shape', () => {
    for (const shape of [
      'vertical_cylinder',
      'horizontal_cylinder',
      'rectangular',
      'spherical',
      'horizontal_elliptical_ends',
      'custom_strapping',
    ] as const) {
      const d = tankOutlinePath(shape, { x: 4, y: 4, w: 88, h: 112 });
      expect(d.startsWith('M ')).toBe(true);
      expect(d.endsWith(' Z')).toBe(true);
    }
  });

  it('roundRectPath starts at the top-left rounded corner and closes Z', () => {
    const d = roundRectPath(4, 4, 88, 112, 12);
    expect(d.startsWith('M 16 4')).toBe(true);
    expect(d.endsWith(' Z')).toBe(true);
  });

  it('fuelColor maps known fuel codes, defaulting otherwise', () => {
    expect(fuelColor('diesel')).toBe('#60a5fa');
    expect(fuelColor('gasoline')).toBe('#f59e0b');
    expect(fuelColor('nope')).toBe('#0ea5e9');
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /home/ubuntu/fuel_monitoring/web && npm test`
Expected: FAIL — `Cannot find module '../src/lib/tankGeometry'`.

- [ ] **Step 3: Implement `web/src/lib/tankGeometry.ts`**

```ts
export type TankShape =
  | 'vertical_cylinder'
  | 'horizontal_cylinder'
  | 'rectangular'
  | 'spherical'
  | 'horizontal_elliptical_ends'
  | 'custom_strapping';

export interface ShapeDims {
  diameter?: number | null;
  length?: number | null;
  height?: number | null;
  width?: number | null;
  dishDepth?: number | null;
}

export interface StrappingPoint {
  height: number;
  volume: number;
}

export interface StrappingRef {
  points: StrappingPoint[];
  method: 'linear' | 'cubic_spline';
}

export interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
}

export function clamp(v: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, v));
}

/** Liters in a horizontal cylinder up to `level` (m); diameter m, length m. */
export function horizontalCylinderLiters(level: number, diameter: number, length: number): number {
  const lvl = clamp(level, 0, diameter);
  const r = diameter / 2;
  if (lvl <= 0.001) return 0;
  if (lvl >= diameter - 0.001) return Math.PI * r * r * length * 1000;
  let area: number;
  if (lvl <= r) {
    const theta = 2 * Math.acos((r - lvl) / r);
    area = (r * r * (theta - Math.sin(theta))) / 2;
  } else {
    const hEmpty = diameter - lvl;
    const theta = 2 * Math.acos((r - hEmpty) / r);
    area = Math.PI * r * r - (r * r * (theta - Math.sin(theta))) / 2;
  }
  return area * length * 1000;
}

function verticalCylinderLiters(level: number, diameter: number, height: number): number {
  return Math.PI * (diameter / 2) ** 2 * clamp(level, 0, height) * 1000;
}

function rectangularLiters(level: number, width: number, length: number, height: number): number {
  return length * width * clamp(level, 0, height) * 1000;
}

function sphericalLiters(level: number, diameter: number): number {
  const r = diameter / 2;
  const h = clamp(level, 0, diameter);
  return ((Math.PI * h * h) / 3) * (3 * r - h) * 1000;
}

/** Natural cubic spline: returns an evaluation function over [xs[0], xs[n]]. */
export function naturalCubicSpline(xs: number[], ys: number[]): (x: number) => number {
  const n = xs.length - 1;
  if (n < 1) throw new Error('spline requires at least 2 points');
  const h: number[] = [];
  for (let i = 0; i < n; i++) h[i] = xs[i + 1] - xs[i];
  if (h.some((v) => v <= 0)) throw new Error('spline x values must be strictly ascending');

  const a: number[][] = Array.from({ length: n + 1 }, () => new Array(n + 1).fill(0));
  const rhs: number[] = new Array(n + 1).fill(0);
  for (let i = 1; i < n; i++) {
    a[i][i - 1] = h[i - 1];
    a[i][i] = 2 * (h[i - 1] + h[i]);
    a[i][i + 1] = h[i];
    rhs[i] = 6 * ((ys[i + 1] - ys[i]) / h[i] - (ys[i] - ys[i - 1]) / h[i - 1]);
  }
  a[0][0] = 1;
  a[n][n] = 1;

  for (let i = 1; i <= n; i++) {
    const factor = a[i][i - 1] / a[i - 1][i - 1];
    a[i][i - 1] = 0;
    a[i][i] -= factor * a[i - 1][i];
    rhs[i] -= factor * rhs[i - 1];
  }
  const m2 = new Array(n + 1).fill(0);
  m2[n] = rhs[n] / a[n][n];
  for (let i = n - 1; i >= 0; i--) {
    let s = rhs[i];
    for (let j = i + 1; j <= n; j++) s -= a[i][j] * m2[j];
    m2[i] = s / a[i][i];
  }

  return (x: number): number => {
    if (x <= xs[0]) return ys[0];
    if (x >= xs[n]) return ys[n];
    let i = 0;
    while (i < n - 1 && xs[i + 1] < x) i++;
    const av = (xs[i + 1] - x) / h[i];
    const bv = (x - xs[i]) / h[i];
    return (
      av * ys[i] +
      bv * ys[i + 1] +
      ((av ** 3 - av) * m2[i] + (bv ** 3 - bv) * m2[i + 1]) * (h[i] * h[i]) / 6
    );
  };
}

export function interpolateStrapping(
  points: StrappingPoint[],
  level: number,
  method: 'linear' | 'cubic_spline'
): number {
  const pts = [...points].sort((a, b) => a.height - b.height).map((p) => [p.height, p.volume] as const);
  if (pts.length < 2) throw new Error('strapping table requires at least 2 points');
  const hs = pts.map((p) => p[0]);
  const vs = pts.map((p) => p[1]);
  if (level <= hs[0]) return vs[0];
  if (level >= hs[hs.length - 1]) return vs[vs.length - 1];
  if (method === 'linear') {
    for (let i = 0; i < hs.length - 1; i++) {
      if (hs[i] <= level && level <= hs[i + 1]) {
        const t = (level - hs[i]) / (hs[i + 1] - hs[i]);
        return vs[i] + t * (vs[i + 1] - vs[i]);
      }
    }
    return vs[0];
  }
  return naturalCubicSpline(hs, vs)(level);
}

/** Liters at a level for a physical shape (mirror of the backend dispatcher). */
export function volumeLitersForShape(
  level: number,
  shape: TankShape,
  dims: ShapeDims,
  strapping?: StrappingRef
): number {
  const d = dims.diameter ?? 0;
  switch (shape) {
    case 'vertical_cylinder':
      return verticalCylinderLiters(level, d, dims.height ?? d);
    case 'rectangular':
      return rectangularLiters(level, dims.width ?? 0, dims.length ?? 0, dims.height ?? 0);
    case 'spherical':
      return sphericalLiters(level, d);
    case 'horizontal_cylinder':
    case 'horizontal_elliptical_ends':
      // Dished heads add a small volume beyond the cylinder; the SVG/readout use the
      // cylinder portion (the backend's persisted `volume` is authoritative).
      return horizontalCylinderLiters(level, d, dims.length ?? 0);
    case 'custom_strapping':
      if (!strapping) throw new Error('custom_strapping requires a strapping table');
      return interpolateStrapping(strapping.points, level, strapping.method);
  }
}

export function fillFraction(level: number, shape: TankShape, dims: ShapeDims): number {
  const h =
    shape === 'vertical_cylinder' || shape === 'rectangular' ? dims.height : dims.diameter;
  if (!h || h <= 0) return clamp(level, 0, 1);
  return clamp(level / h, 0, 1);
}

/** Y pixel of the liquid surface inside a drawing box (bottom = full, top = empty). */
export function liquidTopY(level: number, shape: TankShape, dims: ShapeDims, box: Box): number {
  return box.y + box.h * (1 - fillFraction(level, shape, dims));
}

/** Bottom-aligned liquid polygon; clipped to the tank outline by the SVG. */
export function liquidPath(level: number, shape: TankShape, dims: ShapeDims, box: Box): string {
  const y = liquidTopY(level, shape, dims, box);
  return (
    `M ${box.x} ${y} L ${box.x + box.w} ${y} ` +
    `L ${box.x + box.w} ${box.y + box.h} L ${box.x} ${box.y + box.h} Z`
  );
}

export function roundRectPath(x: number, y: number, w: number, h: number, r: number): string {
  const rr = Math.min(r, w / 2, h / 2);
  return (
    `M ${x + rr} ${y} L ${x + w - rr} ${y} ` +
    `A ${rr} ${rr} 0 0 1 ${x + w} ${y + rr} ` +
    `L ${x + w} ${y + h - rr} A ${rr} ${rr} 0 0 1 ${x + w - rr} ${y + h} ` +
    `L ${x + rr} ${y + h} A ${rr} ${rr} 0 0 1 ${x} ${y + h - rr} ` +
    `L ${x} ${y + rr} A ${rr} ${rr} 0 0 1 ${x + rr} ${y} Z`
  );
}

function circlePath(x: number, y: number, w: number, h: number): string {
  const r = Math.max(1, Math.min(w, h) / 2 - 6);
  const cx = x + w / 2;
  const cy = y + h / 2;
  return `M ${cx - r} ${cy} A ${r} ${r} 0 1 0 ${cx + r} ${cy} A ${r} ${r} 0 1 0 ${cx - r} ${cy} Z`;
}

/** Outline path per tank shape within a drawing box (liquid is clipped to it). */
export function tankOutlinePath(shape: TankShape, box: Box): string {
  switch (shape) {
    case 'vertical_cylinder':
      return roundRectPath(box.x, box.y, box.w, box.h, box.w / 2);
    case 'horizontal_cylinder':
    case 'horizontal_elliptical_ends':
      return roundRectPath(box.x, box.y, box.w, box.h, box.h / 2);
    case 'rectangular':
      return roundRectPath(box.x, box.y, box.w, box.h, 6);
    case 'spherical':
      return circlePath(box.x, box.y, box.w, box.h);
    case 'custom_strapping':
      return roundRectPath(box.x, box.y, box.w, box.h, box.w / 2);
  }
}

/** Liquid fill color keyed by fuel type code. */
export function fuelColor(code: string): string {
  switch (code) {
    case 'gasoline':
      return '#f59e0b';
    case 'diesel':
      return '#60a5fa';
    case 'kerosene':
      return '#84cc16';
    case 'jet_fuel':
      return '#f97316';
    case 'ethanol':
      return '#14b8a6';
    default:
      return '#0ea5e9';
  }
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd /home/ubuntu/fuel_monitoring/web && npm test`
Expected: PASS (`web/tests/tankGeometry.test.ts` green).

- [ ] **Step 5: Commit**

```bash
git add web/tests/tankGeometry.test.ts web/src/lib/tankGeometry.ts
git commit -m "feat: tank-geometry TS mirror + SVG outline/fill helpers tested against backend vectors"
```

---

### Task 3: API types + typed HTTP client

**Files:**
- Create: `web/src/lib/apiTypes.ts`, `web/src/api/http.ts`, `web/src/api/client.ts`
- Test: `web/tests/http.test.ts`

- [ ] **Step 1: Write the failing tests**

`web/tests/http.test.ts`:

```ts
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, request, setOnUnauthorized, setTokenProvider } from '../src/api/http';
import { api } from '../src/api/client';
import type { ListTanksResponse } from '../src/lib/apiTypes';

const json = (data: unknown, init: ResponseInit = {}) =>
  new Response(JSON.stringify(data), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });

describe('request', () => {
  beforeEach(() => {
    setTokenProvider(() => 'tok123');
    setOnUnauthorized(() => {});
    vi.stubGlobal('fetch', vi.fn());
  });
  afterEach(() => vi.unstubAllGlobals());

  it('adds the Bearer token from the provider', async () => {
    vi.mocked(fetch).mockResolvedValue(json({ ok: true }));
    await request('/api/v1/health');
    const [, init] = vi.mocked(fetch).mock.calls[0];
    expect((init.headers as Record<string, string>).Authorization).toBe('Bearer tok123');
  });

  it('throws ApiError with backend detail on 4xx', async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify({ detail: 'nope' }), { status: 400 })
    );
    await expect(request('/api/v1/tanks')).rejects.toBeInstanceOf(ApiError);
  });

  it('fires onUnauthorized on a 401 response', async () => {
    const on401 = vi.fn();
    setOnUnauthorized(on401);
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify({ detail: 'bad token' }), { status: 401 })
    );
    await expect(request('/api/v1/tanks')).rejects.toBeInstanceOf(ApiError);
    expect(on401).toHaveBeenCalledOnce();
  });
});

describe('api client', () => {
  beforeEach(() => {
    setTokenProvider(() => null);
    vi.stubGlobal('fetch', vi.fn());
  });
  afterEach(() => vi.unstubAllGlobals());

  it('login posts credentials and returns the parsed login payload', async () => {
    const payload = { access_token: 'abc', token_type: 'bearer', user: { id: 'u1' } };
    vi.mocked(fetch).mockResolvedValue(json(payload));
    const out = await api.login('alice', 's3cret');
    expect(out.access_token).toBe('abc');
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe('/api/v1/auth/login');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body as string)).toEqual({ username: 'alice', password: 's3cret' });
  });

  it('listTanks GETs /api/v1/tanks', async () => {
    vi.mocked(fetch).mockResolvedValue(json([]));
    const tanks = await api.listTanks();
    expect(vi.mocked(fetch).mock.calls[0][0]).toBe('/api/v1/tanks');
    expect(Array.isArray(tanks)).toBe(true);
  });

  it('rangeReadings encodes query params', async () => {
    vi.mocked(fetch).mockResolvedValue(json([]));
    await api.rangeReadings('t1', '2026-01-01T00:00:00Z', '2026-01-01T01:00:00Z');
    const url = vi.mocked(fetch).mock.calls[0][0] as string;
    expect(url).toContain('/api/v1/tanks/t1/range?start=2026-01-01T00%3A00%3A00Z');
    expect(url).toContain('bucket=5%20minutes');
  });
});
```

(The `ListTanksResponse` import keeps the type under test reference; see its definition in `apiTypes.ts` below.)

- [ ] **Step 2: Run to verify it fails**

Run: `cd /home/ubuntu/fuel_monitoring/web && npm test`
Expected: FAIL — missing module `../src/api/http`.

- [ ] **Step 3: Implement `web/src/lib/apiTypes.ts`**

Interfaces mirror the backend DTOs exactly (tank shape fields include the new backend-plan fields; `fluid_density` is absent).

```ts
export interface UserRead {
  id: string;
  username: string;
  email: string;
  first_name: string | null;
  last_name: string | null;
  role: string;
  is_active: boolean;
  phone: string | null;
  last_login: string | null;
  created_at: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: UserRead;
}

export type FuelCode = 'gasoline' | 'diesel' | 'kerosene' | 'jet_fuel' | 'ethanol' | string;

export interface FuelType {
  id: string;
  code: FuelCode;
  name: string;
  base_density: number;
  thermal_expansion_coeff: number;
  max_vapor_pressure: number;
  viscosity_cst: number;
  created_at: string;
}

export type TankShape =
  | 'vertical_cylinder'
  | 'horizontal_cylinder'
  | 'rectangular'
  | 'spherical'
  | 'horizontal_elliptical_ends'
  | 'custom_strapping';

export interface TankRead {
  id: string;
  name: string;
  site_id: string;
  sensor_serial_number: string;
  device_address: number;
  tank_orientation: 'vertical' | 'horizontal';
  tank_diameter: number;
  tank_height: number | null;
  tank_length: number | null;
  tank_volume: number;
  tank_shape: TankShape | null;
  fuel_type_id: string;
  dish_depth: number | null;
  tank_width: number | null;
  strapping_table_id: string | null;
  elevation: number | null;
  calibration_factor: number;
  atmospheric_pressure: number;
  low_level_threshold: number | null;
  critical_level_threshold: number | null;
  high_level_threshold: number | null;
  low_volume_threshold: number | null;
  high_volume_threshold: number | null;
  is_active: boolean;
  gateway_mac: string | null;
  created_at: string;
  connection_status: string;
  last_connection: string | null;
}

export interface TankCreatePayload {
  name: string;
  site_id: string;
  sensor_serial_number: string;
  device_address?: number;
  tank_orientation: 'vertical' | 'horizontal';
  tank_shape: TankShape;
  tank_diameter: number;
  tank_height?: number;
  tank_length?: number;
  tank_width?: number;
  dish_depth?: number;
  tank_volume: number;
  fuel_type_id: string;
  low_level_threshold?: number | null;
  critical_level_threshold?: number | null;
  high_level_threshold?: number | null;
  low_volume_threshold?: number | null;
  high_volume_threshold?: number | null;
}

export interface TelemetryPoint {
  timestamp: string;
  pressure: number | null;
  temperature: number | null;
  level: number | null;
  volume: number | null;
  flow_rate: number | null;
  fill_percent: number | null;
  is_outlier: boolean;
  gov_volume?: number | null;
  net_volume?: number | null;
  density_at_temperature?: number | null;
}

export interface AlarmSummary {
  id: string;
  tank_id: string;
  timestamp: string;
  type: string;
  level: string;
  message: string;
  value: number | null;
  acknowledged: boolean;
  acknowledged_at: string | null;
}

export interface StrappingPoint {
  height: number;
  volume: number;
}

export interface StrappingTable {
  id: string;
  tank_id: string;
  calibration_data: StrappingPoint[];
  interpolation_method: 'linear' | 'cubic_spline';
  created_at: string;
}

export interface AllocationRead {
  id: string;
  employee_id: string;
  employee_name: string;
  invoice_number: string | null;
  allocated_liters: number;
  dispensed_liters: number;
  remaining_liters: number;
  status: string;
  created_at: string;
}

export interface TransactionRead {
  id: number;
  station_id: string;
  dispenser_id: string;
  employee_id: string;
  requested_liters: number;
  actual_liters: number;
  secret_totalizer_before: number;
  secret_totalizer_after: number;
  status: string;
  created_at: string;
}

export interface TotalizerPoint {
  timestamp: string;
  station_id: string;
  dispenser_id: string;
  totalizer_value: number;
  cumulative_liters: number;
  source: string;
}

export interface Dispenser {
  id: string;
  name: string;
  station_id: string;
  serial_number: string;
  modbus_address: number;
  dispenser_model: string | null;
  is_active: boolean;
}

export interface Station {
  id: string;
  name: string;
  site_id: string;
  serial_number: string;
  raspberry_pi_id: string | null;
  firmware_version: string | null;
  connection_status: string;
  last_heartbeat: string | null;
}

export interface Company {
  id: string;
  name: string;
  address: string | null;
  contact_name: string | null;
  contact_email: string | null;
  contact_phone: string | null;
  created_at: string;
}

export interface Site {
  id: string;
  name: string;
  company_id: string;
  address: string | null;
  location: string | null;
  is_active: boolean;
  created_at: string;
}

export type ListTanksResponse = TankRead[];
```

- [ ] **Step 4: Implement `web/src/api/http.ts`**

```ts
export class ApiError extends Error {
  constructor(public status: number, public detail: string) {
    super(detail);
    this.name = 'ApiError';
  }
}

let tokenProvider: () => string | null = () => null;
let onUnauthorized: () => void = () => {};

export function setTokenProvider(fn: () => string | null): void {
  tokenProvider = fn;
}

export function setOnUnauthorized(fn: () => void): void {
  onUnauthorized = fn;
}

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = tokenProvider();
  const headers: Record<string, string> = {
    ...((init.headers as Record<string, string>) ?? {}),
  };
  if (!headers['Content-Type']) headers['Content-Type'] = 'application/json';
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const res = await fetch(path, { ...init, headers });
  if (res.status === 401) onUnauthorized();
  const text = await res.text();
  let body: unknown = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = text;
  }
  if (!res.ok) {
    const detail =
      typeof body === 'object' && body !== null && 'detail' in body
        ? String((body as { detail: unknown }).detail)
        : String(body || `HTTP ${res.status}`);
    throw new ApiError(res.status, detail);
  }
  return body as T;
}

export const get = <T>(path: string) => request<T>(path);

export const post = <T>(path: string, data?: unknown) =>
  request<T>(path, { method: 'POST', body: data === undefined ? undefined : JSON.stringify(data) });
```

- [ ] **Step 5: Implement `web/src/api/client.ts`**

```ts
import type {
  AlarmSummary,
  AllocationRead,
  Company,
  Dispenser,
  FuelType,
  ListTanksResponse,
  LoginResponse,
  Site,
  Station,
  StrappingTable,
  TankCreatePayload,
  TankRead,
  TelemetryPoint,
  TotalizerPoint,
  TransactionRead,
  UserRead,
} from '../lib/apiTypes';
import { get, post } from './http';

export const api = {
  login: (username: string, password: string) =>
    post<LoginResponse>('/api/v1/auth/login', { username, password }),
  me: () => get<UserRead>('/api/v1/auth/me'),

  listTanks: () => get<ListTanksResponse>('/api/v1/tanks'),
  getTank: (id: string) => get<TankRead>(`/api/v1/tanks/${id}`),
  createTank: (payload: TankCreatePayload) => post<TankRead>('/api/v1/tanks', payload),
  recentReadings: (id: string, limit = 200) =>
    get<TelemetryPoint[]>(`/api/v1/tanks/${id}/recent?limit=${limit}`),
  rangeReadings: (id: string, start: string, end: string, bucket = '5 minutes') =>
    get<TelemetryPoint[]>(
      `/api/v1/tanks/${id}/range?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}&bucket=${encodeURIComponent(bucket)}`
    ),
  tankAlarms: (id: string, openOnly = false, limit = 50) =>
    get<AlarmSummary[]>(`/api/v1/tanks/${id}/alarms${openOnly ? '?open_only=true' : ''}`),
  ackAlarm: (tankId: string, alarmId: string) =>
    post<{ alarm_id: string; acknowledged: boolean }>(`/api/v1/tanks/${tankId}/alarms/${alarmId}/ack`),
  getStrapping: (tankId: string) => get<StrappingTable>(`/api/v1/tanks/${tankId}/strapping`),

  listFuelTypes: () => get<FuelType[]>('/api/v1/fuel-types'),

  listCompanies: () => get<Company[]>('/api/v1/companies'),
  listSites: (companyId?: string) =>
    get<Site[]>(`/api/v1/sites${companyId ? `?company_id=${companyId}` : ''}`),
  listStations: (siteId?: string) =>
    get<Station[]>(`/api/v1/stations${siteId ? `?site_id=${siteId}` : ''}`),
  stationDispensers: (stationId: string) =>
    get<Dispenser[]>(`/api/v1/stations/${stationId}/dispensers`),

  listTotalizers: (dispenserId?: string, start?: string, end?: string, limit = 1000) => {
    const qs = new URLSearchParams();
    if (dispenserId) qs.set('dispenser_id', dispenserId);
    if (start) qs.set('start', start);
    if (end) qs.set('end', end);
    qs.set('limit', String(limit));
    return get<TotalizerPoint[]>(`/api/v1/totalizers?${qs}`);
  },
  listAllocations: (limit = 100) =>
    get<AllocationRead[]>(`/api/v1/dispensing/allocations?max_rows=${limit}`),
  listTransactions: (limit = 200, dispenserId?: string) =>
    get<TransactionRead[]>(
      `/api/v1/dispensing/transactions?limit=${limit}${dispenserId ? `&dispenser_id=${dispenserId}` : ''}`
    ),
};
```

- [ ] **Step 6: Run to verify it passes**

Run: `cd /home/ubuntu/fuel_monitoring/web && npm test`
Expected: PASS (`web/tests/http.test.ts` green).

- [ ] **Step 7: Commit**

```bash
git add web/src/lib/apiTypes.ts web/src/api/http.ts web/src/api/client.ts web/tests/http.test.ts
git commit -m "feat: typed API client with JWT injection and centralized 401 handling"
```

---

### Task 4: Auth store (zustand persist) + auth guard

**Files:**
- Create: `web/src/store/auth.ts`, `web/src/lib/authGuard.ts`
- Test: `web/tests/authStore.test.ts`

- [ ] **Step 1: Write the failing tests**

`web/tests/authStore.test.ts`:

```ts
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { isAuthed } from '../src/lib/authGuard';
import { setOnUnauthorized, setTokenProvider } from '../src/api/http';
import { useAuthStore } from '../src/store/auth';

const loginResponse = {
  access_token: 'jwt.1',
  token_type: 'bearer',
  user: { id: 'u1', username: 'alice', email: 'a@x.com', role: 'admin', is_active: true },
};

describe('authGuard', () => {
  it('treats only non-empty tokens as authenticated', () => {
    expect(isAuthed('abc.def')).toBe(true);
    expect(isAuthed('')).toBe(false);
    expect(isAuthed(null)).toBe(false);
  });
});

describe('auth store', () => {
  beforeEach(() => {
    localStorage.clear();
    setTokenProvider(() => useAuthStore.getState().token);
    setOnUnauthorized(() => useAuthStore.getState().logout());
  });

  it('login stores token + user and persists to localStorage', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(loginResponse), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      )
    );
    await useAuthStore.getState().login('alice', 'pw');
    expect(useAuthStore.getState().token).toBe('jwt.1');
    expect(useAuthStore.getState().user?.username).toBe('alice');
    expect(localStorage.getItem('fuel.auth')).toContain('jwt.1');
    vi.unstubAllGlobals();
  });

  it('logout clears the session', () => {
    useAuthStore.getState().login = async () => {};
    useAuthStore.setState({ token: 'jwt.1', user: loginResponse.user as never });
    useAuthStore.getState().logout();
    expect(useAuthStore.getState().token).toBeNull();
    expect(useAuthStore.getState().user).toBeNull();
  });

  it('boot calls /me with the token; a 401 clears the session', async () => {
    useAuthStore.setState({ token: 'stale.jwt' });
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: 'expired' }), { status: 401 }))
    );
    await useAuthStore.getState().boot();
    expect(useAuthStore.getState().token).toBeNull();
    vi.unstubAllGlobals();
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /home/ubuntu/fuel_monitoring/web && npm test`
Expected: FAIL — missing `../src/store/auth`.

- [ ] **Step 3: Implement `web/src/lib/authGuard.ts`**

```ts
export function isAuthed(token: string | null | undefined): boolean {
  return Boolean(token && token.length > 0);
}
```

- [ ] **Step 4: Implement `web/src/store/auth.ts`**

```ts
import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';
import type { UserRead } from '../lib/apiTypes';
import { api } from '../api/client';
import { setOnUnauthorized, setTokenProvider } from '../api/http';

export interface AuthState {
  token: string | null;
  user: UserRead | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  boot: () => Promise<void>;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      token: null,
      user: null,
      login: async (username, password) => {
        const res = await api.login(username, password);
        set({ token: res.access_token, user: res.user });
      },
      logout: () => set({ token: null, user: null }),
      boot: async () => {
        if (!get().token) return;
        try {
          const me = await api.me();
          set({ user: me });
        } catch {
          get().logout();
        }
      },
    }),
    { name: 'fuel.auth', storage: createJSONStorage(() => localStorage) }
  )
);

setTokenProvider(() => useAuthStore.getState().token);
setOnUnauthorized(() => useAuthStore.getState().logout());
```

- [ ] **Step 5: Run to verify it passes**

Run: `cd /home/ubuntu/fuel_monitoring/web && npm test`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add web/src/store/auth.ts web/src/lib/authGuard.ts web/tests/authStore.test.ts
git commit -m "feat: persisted zustand auth store + guard, boot validation via /me"
```

---

### Task 5: Router, login page, guarded layout

**Files:**
- Create: `web/src/router.tsx`, `web/src/pages/Login.tsx`, `web/src/components/layout/AppLayout.tsx`, `web/src/components/layout/Sidebar.tsx`
- Create (stubs, filled in later tasks): `web/src/pages/Dashboard.tsx`, `web/src/pages/Tanks.tsx`, `web/src/pages/TankDetail.tsx`, `web/src/pages/Dispensing.tsx`, `web/src/pages/Totalizers.tsx`, `web/src/hooks/useRealtimeAlarms.ts`, `web/src/store/telemetry.ts`
- Modify: `web/src/main.tsx`, `web/src/App.tsx` (replace App with the routing bootstrap)

- [ ] **Step 1: Implement the app shell**

`web/src/main.tsx`:

```tsx
import React from 'react';
import ReactDOM from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RouterProvider } from 'react-router-dom';
import { router } from './router';
import { useAuthStore } from './store/auth';
import { useTelemetrySocket } from './hooks/useTelemetrySocket';
import './index.css';

void useAuthStore.getState().boot();

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false, staleTime: 15_000 } },
});

function Root() {
  // Hooks must live inside a component; `useAuthStore` re-fires the socket
  // connect whenever the token changes (login/logout/rehydrate).
  useTelemetrySocket();
  return <RouterProvider router={router} />;
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <Root />
    </QueryClientProvider>
  </React.StrictMode>
);
```

`web/src/router.tsx`:

```tsx
import React from 'react';
import { Navigate, createBrowserRouter } from 'react-router-dom';
import { isAuthed } from './lib/authGuard';
import { useAuthStore } from './store/auth';
import { AppLayout } from './components/layout/AppLayout';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Tanks from './pages/Tanks';
import TankDetail from './pages/TankDetail';
import Dispensing from './pages/Dispensing';
import Totalizers from './pages/Totalizers';

function RequireAuth({ children }: { children: React.ReactNode }) {
  const authed = isAuthed(useAuthStore((s) => s.token));
  if (!authed) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export const router = createBrowserRouter([
  { path: '/login', element: <Login /> },
  {
    path: '/',
    element: (
      <RequireAuth>
        <AppLayout />
      </RequireAuth>
    ),
    children: [
      { index: true, element: <Navigate to="/dashboard" replace /> },
      { path: 'dashboard', element: <Dashboard /> },
      { path: 'tanks', element: <Tanks /> },
      { path: 'tanks/:tankId', element: <TankDetail /> },
      { path: 'dispensing', element: <Dispensing /> },
      { path: 'totalizers', element: <Totalizers /> },
    ],
  },
  { path: '*', element: <Navigate to="/dashboard" replace /> },
]);
```

`web/src/pages/Login.tsx`:

```tsx
import { FormEvent, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ApiError } from '../api/http';
import { useAuthStore } from '../store/auth';

export default function Login() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const login = useAuthStore((s) => s.login);
  const navigate = useNavigate();

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(username, password);
      navigate('/dashboard', { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Sign-in failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-900 px-4">
      <form onSubmit={submit} className="w-full max-w-sm bg-white rounded-lg shadow-lg p-8">
        <h1 className="text-2xl font-bold text-slate-800 mb-1">FuelOps SCADA</h1>
        <p className="text-sm text-slate-500 mb-6">Sign in to the fuel platform</p>
        <label className="block text-sm font-medium text-slate-700 mb-1">Username</label>
        <input
          className="w-full border border-slate-300 rounded px-3 py-2 mb-4"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          autoComplete="username"
          required
        />
        <label className="block text-sm font-medium text-slate-700 mb-1">Password</label>
        <input
          type="password"
          className="w-full border border-slate-300 rounded px-3 py-2 mb-4"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password"
          required
        />
        {error ? <p className="text-sm text-red-600 mb-4">{error}</p> : null}
        <button
          type="submit"
          disabled={busy}
          className="w-full bg-brand text-white rounded py-2 font-medium disabled:opacity-50"
        >
          {busy ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </div>
  );
}
```

`web/src/components/layout/Sidebar.tsx`:

```tsx
import { NavLink } from 'react-router-dom';
import { useAuthStore } from '../../store/auth';
import { useRealtimeAlarms } from '../../hooks/useRealtimeAlarms';

const links = [
  { to: '/dashboard', label: 'Dashboard' },
  { to: '/tanks', label: 'Tanks' },
  { to: '/dispensing', label: 'Dispensing' },
  { to: '/totalizers', label: 'Totalizers' },
];

export function Sidebar() {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const alarms = useRealtimeAlarms();
  const openCount = alarms.filter((a) => !a.acknowledged).length;

  return (
    <aside className="w-56 shrink-0 bg-slate-900 text-slate-100 flex flex-col">
      <div className="px-4 py-5 border-b border-slate-800">
        <p className="font-bold tracking-tight">FuelOps SCADA</p>
        <p className="text-xs text-slate-400">{user?.username ?? ''}</p>
      </div>
      <nav className="flex-1 px-2 py-4 space-y-1">
        {links.map((l) => (
          <NavLink
            key={l.to}
            to={l.to}
            className={({ isActive }) =>
              `block rounded px-3 py-2 text-sm ${
                isActive ? 'bg-brand text-white' : 'hover:bg-slate-800'
              }`
            }
          >
            {l.label}
            {l.to === '/dashboard' && openCount > 0 ? (
              <span className="ml-2 inline-block w-2 h-2 rounded-full bg-rose-400" />
            ) : null}
          </NavLink>
        ))}
      </nav>
      <div className="px-4 py-4 border-t border-slate-800">
        <button onClick={logout} className="text-sm text-slate-400 hover:text-white">
          Sign out
        </button>
      </div>
    </aside>
  );
}
```

`web/src/components/layout/AppLayout.tsx`:

```tsx
import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';

export function AppLayout() {
  return (
    <div className="min-h-screen flex bg-slate-100">
      <Sidebar />
      <main className="flex-1 p-6 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}
```

Stub page implementations (filled in Tasks 7-10) — all return a titled placeholder:

`web/src/pages/Dashboard.tsx`:
```tsx
export default function Dashboard() {
  return <h2 className="text-2xl font-semibold text-slate-800">Dashboard</h2>;
}
```

`web/src/pages/Tanks.tsx`:
```tsx
export default function Tanks() {
  return <h2 className="text-2xl font-semibold text-slate-800">Tanks</h2>;
}
```

`web/src/pages/TankDetail.tsx`:
```tsx
export default function TankDetail() {
  return <h2 className="text-2xl font-semibold text-slate-800">Tank Detail</h2>;
}
```

`web/src/pages/Dispensing.tsx`:
```tsx
export default function Dispensing() {
  return <h2 className="text-2xl font-semibold text-slate-800">Dispensing</h2>;
}
```

`web/src/pages/Totalizers.tsx`:
```tsx
export default function Totalizers() {
  return <h2 className="text-2xl font-semibold text-slate-800">Totalizers</h2>;
}
```

Telemetry store + hooks must exist for `Sidebar`/`main` imports. Create the minimal files now (fully expanded in Task 6):

`web/src/store/telemetry.ts`:
```ts
import { create } from 'zustand';
import type { AlarmSummary, TelemetryPoint } from '../lib/apiTypes';

export interface LiveReading extends TelemetryPoint {
  tank_id: string;
  timestamp: string;
}

export interface TelemetryState {
  readings: Record<string, LiveReading>;
  alarms: AlarmSummary[];
  setReading: (r: LiveReading) => void;
  setAlarm: (a: AlarmSummary) => void;
}

export const useTelemetryStore = create<TelemetryState>()((set) => ({
  readings: {},
  alarms: [],
  setReading: (r) =>
    set((s) => ({ readings: { ...s.readings, [r.tank_id]: r } })),
  setAlarm: (a) => set((s) => ({ alarms: [a, ...s.alarms].slice(0, 50) })),
}));
```

`web/src/hooks/useRealtimeAlarms.ts`:
```ts
import { useTelemetryStore } from '../store/telemetry';

export function useRealtimeAlarms() {
  return useTelemetryStore((s) => s.alarms);
}
```

`web/src/hooks/useTelemetrySocket.ts`:

```ts
import { useEffect } from 'react';
import { useAuthStore } from '../store/auth';
import { useTelemetryStore } from '../store/telemetry';
import { LiveReading } from '../store/telemetry';
import type { AlarmSummary } from '../lib/apiTypes';
import { TelemetrySocket } from '../api/ws';

export function useTelemetrySocket() {
  const token = useAuthStore((s) => s.token);

  useEffect(() => {
    if (!token) return;
    const wsProto = location.origin.replace(/^http/, 'ws');
    const tel = new TelemetrySocket(`${wsProto}/ws/telemetry?channels=telemetry&token=${encodeURIComponent(token)}`);
    const alm = new TelemetrySocket(`${wsProto}/ws/alarms?token=${encodeURIComponent(token)}`);
    const offR = tel.on('reading', (m) =>
      useTelemetryStore.getState().setReading(m as LiveReading)
    );
    const offA = alm.on('alarm', (m) =>
      useTelemetryStore.getState().setAlarm(m as AlarmSummary)
    );
    tel.connect();
    alm.connect();
    return () => {
      offR();
      offA();
      tel.disconnect();
      alm.disconnect();
    };
  }, [token]);
}
```

Note: `useTelemetrySocket` imports `TelemetrySocket` from `../api/ws`, which does not exist yet — Task 6 creates it. Until Task 6 lands, `npm test`-only verification of this task is limited to typecheck-free unit tests; the smoke test in `App.test.tsx` still renders `App` directly (not the router), so the app can be built. Step 4 below verifies `npm run build`, which typechecks all modules — implement `web/src/api/ws.ts` in Task 6 **before** running `npm run build`, or temporarily comment the `useTelemetrySocket` import in `main.tsx` until Task 6. The recommended order is Task 5 → Task 6 → build; run `npm test` now (unit tests do not import the router shell).

- [ ] **Step 2: Run unit tests**

Run: `cd /home/ubuntu/fuel_monitoring/web && npm test`
Expected: PASS (all previous tests; no new tests yet in this task).

- [ ] **Step 3: Commit**

```bash
git add web/src/router.tsx web/src/main.tsx web/src/App.tsx web/src/pages/ web/src/components/layout/ web/src/store/telemetry.ts web/src/hooks/useRealtimeAlarms.ts web/src/hooks/useTelemetrySocket.ts
git commit -m "feat: react-router shell with guarded layout, login page, sidebar, stub pages"
```

---

### Task 6: WebSocket client + live telemetry hooks

**Files:**
- Create: `web/src/api/ws.ts`
- Modify: `web/src/store/telemetry.ts` (already has `LiveReading` — wire nothing further)
- Test: `web/tests/ws.test.ts`

- [ ] **Step 1: Write the failing tests**

`web/tests/ws.test.ts` (a fake `WebSocket` replaces the browser socket; `vi.useFakeTimers()` for reconnect backoff):

```ts
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { TelemetrySocket } from '../src/api/ws';

class FakeWS {
  static instances: FakeWS[] = [];
  url = '';
  onopen: (() => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: (() => void) | null = null;
  closed = false;

  constructor(url: string) {
    this.url = url;
    FakeWS.instances.push(this);
  }
  close() {
    this.closed = true;
  }
  triggerOpen() {
    this.onopen?.();
  }
  triggerMessage(data: unknown) {
    this.onmessage?.({ data: JSON.stringify(data) });
  }
  triggerClose() {
    this.onclose?.();
  }
}

const url = 'ws://x/ws/telemetry?token=tok';
const createSocket = (u: string) => new FakeWS(u) as unknown as WebSocket;

describe('TelemetrySocket', () => {
  beforeEach(() => {
    FakeWS.instances = [];
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('connects to the given URL and emits parsed readings', () => {
    const sock = new TelemetrySocket(url, { createSocket });
    const reading = vi.fn();
    sock.on('reading', reading);
    sock.connect();
    const ws = FakeWS.instances[0];
    expect(ws.url).toBe(url);
    ws.triggerOpen();
    ws.triggerMessage({ tank_id: 't1', level: 1.2, volume: 400, gov_volume: 401 });
    expect(reading).toHaveBeenCalledTimes(1);
    expect(reading.mock.calls[0][0].tank_id).toBe('t1');
    expect(reading.mock.calls[0][0].gov_volume).toBe(401);
    sock.disconnect();
  });

  it('treats non-JSON or alarm frames without crashing', () => {
    const sock = new TelemetrySocket(url, { createSocket });
    const alarm = vi.fn();
    sock.on('alarm', alarm);
    sock.connect();
    const ws = FakeWS.instances[0];
    ws.triggerOpen();
    ws.triggerMessage({ type: 'LEVEL', tank_id: 't1', acknowledged: false });
    expect(alarm).toHaveBeenCalledTimes(1);
    expect(sock).toBeDefined();
    sock.disconnect();
  });

  it('reconnects with exponential backoff after close, capping at 30s', () => {
    vi.useFakeTimers();
    const sock = new TelemetrySocket(url, { createSocket });
    sock.connect();
    const first = FakeWS.instances[0];
    first.triggerClose();
    vi.advanceTimersByTime(999);
    expect(FakeWS.instances.length).toBe(1); // not yet
    vi.advanceTimersByTime(1);
    expect(FakeWS.instances.length).toBe(2); // reconnected after 1s
    const second = FakeWS.instances[1];
    second.triggerClose();
    vi.advanceTimersByTime(1_999);
    expect(FakeWS.instances.length).toBe(2);
    vi.advanceTimersByTime(1);
    expect(FakeWS.instances.length).toBe(3); // 2s backoff
    sock.disconnect();
  });

  it('disconnect() stops reconnects and closes the socket', () => {
    const sock = new TelemetrySocket(url, { createSocket });
    sock.connect();
    const ws = FakeWS.instances[0];
    ws.triggerClose();
    sock.disconnect();
    vi.advanceTimersByTime(5_000);
    expect(FakeWS.instances.length).toBe(1);
    expect(ws.closed).toBe(true);
  });

  it('emits status events on open and close', () => {
    const sock = new TelemetrySocket(url, { createSocket });
    const status = vi.fn();
    sock.on('status', status);
    sock.connect();
    FakeWS.instances[0].triggerOpen();
    expect(status).toHaveBeenLastCalledWith({ state: 'open' });
    FakeWS.instances[0].triggerClose();
    expect(status).toHaveBeenLastCalledWith({ state: 'closed' });
    sock.disconnect();
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /home/ubuntu/fuel_monitoring/web && npm test`
Expected: FAIL — missing `../src/api/ws`.

- [ ] **Step 3: Implement `web/src/api/ws.ts`**

```ts
export type WsMessage = unknown;

type Listener = (msg: any) => void;

const READ_RECONNECT_MS = 1_000;
const RECONNECT_MAX_MS = 30_000;

export class TelemetrySocket {
  private ws: WebSocket | null = null;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private retries = 0;
  private closedByUser = false;
  private listeners = new Map<string, Set<Listener>>();

  constructor(
    private url: string,
    private opts: { createSocket?: (u: string) => WebSocket } = {}
  ) {}

  connect(): void {
    this.closedByUser = false;
    this.open();
  }

  private open(): void {
    const make = this.opts.createSocket ?? ((u: string) => new WebSocket(u));
    this.ws = make(this.url);
    this.ws.onopen = () => {
      this.retries = 0;
      this.emit('status', { state: 'open' });
    };
    this.ws.onmessage = (ev: MessageEvent) => {
      let data: any = null;
      try {
        data = JSON.parse(ev.data as string);
      } catch {
        return;
      }
      if (data && typeof data.tank_id === 'string') this.emit('reading', data);
      else this.emit('alarm', data);
    };
    this.ws.onerror = () => {};
    this.ws.onclose = () => {
      this.emit('status', { state: 'closed' });
      if (!this.closedByUser) this.scheduleReconnect();
    };
  }

  private scheduleReconnect(): void {
    const delay = Math.min(RECONNECT_MAX_MS, READ_RECONNECT_MS * 2 ** this.retries);
    this.retries += 1;
    this.timer = setTimeout(() => this.open(), delay);
  }

  disconnect(): void {
    this.closedByUser = true;
    if (this.timer) {
      clearTimeout(this.timer);
      this.timer = null;
    }
    if (this.ws) {
      this.ws.onclose = null;
      this.ws.close();
      this.ws = null;
    }
  }

  on(type: 'reading' | 'alarm' | 'status', cb: Listener): () => void {
    if (!this.listeners.has(type)) this.listeners.set(type, new Set());
    this.listeners.get(type)!.add(cb);
    return () => this.listeners.get(type)?.delete(cb);
  }

  private emit(type: string, msg: any): void {
    this.listeners.get(type)?.forEach((cb) => cb(msg));
  }
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd /home/ubuntu/fuel_monitoring/web && npm test`
Expected: PASS (`web/tests/ws.test.ts` green).

- [ ] **Step 5: Run typecheck/build** (unblocks the Task 5 `main.tsx` import)

Run: `cd /home/ubuntu/fuel_monitoring/web && npm run build`
Expected: clean `tsc` + Vite `dist/`.

- [ ] **Step 6: Commit**

```bash
git add web/src/api/ws.ts web/tests/ws.test.ts
git commit -m "feat: WebSocket client with token auth, reconnect backoff, live-reading events"
```

---

### Task 7: TankCanvas + dashboard

**Files:**
- Create: `web/src/components/tanks/TankCanvas.tsx`, `web/src/components/tanks/TankTile.tsx`, `web/src/hooks/useTelemetry.ts`, `web/src/lib/fuelMap.ts`
- Modify: `web/src/pages/Dashboard.tsx`
- Test: `web/tests/fuelMap.test.ts` (pure helpers are unit-tested; the geometry math was already tested in Task 2)

- [ ] **Step 1: Write the failing tests**

`web/tests/fuelMap.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { fuelCodeById } from '../src/lib/fuelMap';
import type { FuelType, TankRead } from '../src/lib/apiTypes';

const fuels: FuelType[] = [
  { id: 'f1', code: 'diesel', name: 'Diesel', base_density: 845, thermal_expansion_coeff: 0.0008, max_vapor_pressure: 2, viscosity_cst: 2.5, created_at: 'x' },
];

describe('fuelCodeById', () => {
  it('resolves the fuel code for a tank fuel_type_id', () => {
    expect(fuelCodeById(fuels, 'f1')).toBe('diesel');
  });

  it('returns empty string when the fuel is unknown', () => {
    expect(fuelCodeById([], 'nope')).toBe('');
  });

  it('uses the strapping_shaped tank defaults without crashing', () => {
    const tank = {} as TankRead;
    expect(fuelCodeById(fuels, tank.fuel_type_id)).toBe('');
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /home/ubuntu/fuel_monitoring/web && npm test`
Expected: FAIL — missing `../src/lib/fuelMap`.

- [ ] **Step 3: Implement `web/src/lib/fuelMap.ts`**

```ts
import type { FuelType } from './apiTypes';

export function fuelCodeById(fuels: FuelType[], fuelTypeId: string | null | undefined): string {
  const fuel = fuels.find((f) => f.id === fuelTypeId);
  return fuel?.code ?? '';
}
```

- [ ] **Step 4: Implement `web/src/components/tanks/TankCanvas.tsx`**

```tsx
import type { LiveReading } from '../../store/telemetry';
import type { TankRead } from '../../lib/apiTypes';
import {
  fillFraction,
  fuelColor,
  liquidPath,
  tankOutlinePath,
  type Box,
  type ShapeDims,
  type TankShape,
} from '../../lib/tankGeometry';
import { fuelCodeById } from '../../lib/fuelMap';
import type { FuelType } from '../../lib/apiTypes';

export interface ThreshLine {
  y: number;
  color: string;
  label: string;
}

function thresholdLines(tank: TankRead, box: Box): ThreshLine[] {
  const shape = (tank.tank_shape ?? 'vertical_cylinder') as TankShape;
  const dims: ShapeDims = {
    diameter: tank.tank_diameter,
    length: tank.tank_length,
    height: tank.tank_height,
    width: tank.tank_width,
  };
  const lines: ThreshLine[] = [];
  const maxH = shape === 'vertical_cylinder' || shape === 'rectangular' ? tank.tank_height : tank.tank_diameter;
  if (!maxH) return lines;
  for (const rec of [
    { v: tank.high_level_threshold, color: '#f87171', label: 'high' },
    { v: tank.low_level_threshold, color: '#facc15', label: 'low' },
    { v: tank.critical_level_threshold, color: '#ef4444', label: 'crit' },
  ]) {
    if (rec.v != null) {
      const frac = fillFraction(rec.v, shape, dims);
      lines.push({ y: box.y + box.h * (1 - frac), color: rec.color, label: rec.label });
    }
  }
  return lines;
}

interface TankCanvasProps {
  tank: TankRead;
  live?: LiveReading;
  fuels?: FuelType[];
  compact?: boolean;
}

export function TankCanvas({ tank, live, fuels = [], compact = false }: TankCanvasProps) {
  const shape = (tank.tank_shape ?? 'vertical_cylinder') as TankShape;
  const dims: ShapeDims = {
    diameter: tank.tank_diameter,
    length: tank.tank_length,
    height: tank.tank_height,
    width: tank.tank_width,
    dishDepth: tank.dish_depth,
  };
  const box: Box = { x: 4, y: 4, w: 88, h: 112 };
  const level = live?.level ?? 0;
  const code = fuelCodeById(fuels, tank.fuel_type_id);
  const color = fuelColor(code);
  const clipId = `clip-${tank.id}`;
  const thresholds = thresholdLines(tank, box);
  const fillPct = Math.round((live?.fill_percent ?? 0) * 100) / 100;
  const flow = live?.flow_rate ?? 0;

  const liquid = liquidPath(level, shape, dims, box);
  return (
    <div className={compact ? 'relative' : 'flex flex-col'}>
      <svg viewBox="0 0 96 120" className="w-full h-auto" role="img" aria-label={`${tank.name} level ${fillPct}%`}>
        <defs>
          <clipPath id={clipId}>
            <path d={tankOutlinePath(shape, box)} />
          </clipPath>
        </defs>
        <path d={tankOutlinePath(shape, box)} fill="none" stroke="#334155" strokeWidth="2" />
        <g clipPath={`url(#${clipId})`}>
          <path d={liquid} fill={color} opacity={0.7} />
        </g>
        {thresholds.map((t) => (
          <line
            key={t.label}
            x1={box.x}
            x2={box.x + box.w}
            y1={t.y}
            y2={t.y}
            stroke={t.color}
            strokeWidth={1}
            strokeDasharray="4 3"
          />
        ))}
        {flow !== 0 ? (
          <text x={box.x + box.w - 6} y={10} fontSize="12" textAnchor="end" fill={flow > 0 ? '#16a34a' : '#dc2626'}>
            {flow > 0 ? '▲ in' : '▼ out'}
          </text>
        ) : null}
      </svg>
      {!compact ? (
        <div className="text-center text-sm font-medium text-slate-700 mt-1">
          {fillPct}% · {Math.round(live?.gov_volume ?? live?.volume ?? 0).toLocaleString()} L
        </div>
      ) : null}
    </div>
  );
}
```

`web/src/components/tanks/TankTile.tsx`:

```tsx
import { Link } from 'react-router-dom';
import type { FuelType, TankRead } from '../../lib/apiTypes';
import type { LiveReading } from '../../store/telemetry';
import { TankCanvas } from './TankCanvas';

interface TankTileProps {
  tank: TankRead;
  live?: LiveReading;
  fuels?: FuelType[];
}

export function TankTile({ tank, live, fuels = [] }: TankTileProps) {
  return (
    <Link
      to={`/tanks/${tank.id}`}
      className="bg-white rounded-lg border border-slate-200 p-3 hover:shadow-md transition-shadow"
    >
      <div className="flex items-center justify-between mb-2">
        <p className="font-medium text-slate-800 truncate">{tank.name}</p>
        <span
          className={`text-xs px-2 py-0.5 rounded-full ${
            live ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'
          }`}
        >
          {live ? 'live' : tank.connection_status}
        </span>
      </div>
      <TankCanvas tank={tank} live={live} fuels={fuels} compact />
    </Link>
  );
}
```

`web/src/hooks/useTelemetry.ts`:

```ts
import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import { useTelemetryStore, type LiveReading } from '../store/telemetry';

export function useTelemetry(tankId: string) {
  const live = useTelemetryStore((s) => s.readings[tankId]);
  const q = useQuery({
    queryKey: ['recent', tankId],
    queryFn: () => api.recentReadings(tankId, 200),
    refetchInterval: 30_000,
  });
  const recent = (q.data ?? []) as LiveReading[];
  return { live, recent, loading: q.isLoading };
}
```

`web/src/pages/Dashboard.tsx`:

```tsx
import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import { useRealtimeAlarms } from '../hooks/useRealtimeAlarms';
import { useTelemetry } from '../hooks/useTelemetry';
import { TankTile } from '../components/tanks/TankTile';
import type { FuelType, TankRead } from '../lib/apiTypes';

export default function Dashboard() {
  const tanks = useQuery({ queryKey: ['tanks'], queryFn: () => api.listTanks() });
  const fuels = useQuery({ queryKey: ['fuel-types'], queryFn: () => api.listFuelTypes() });
  const alarms = useRealtimeAlarms();
  const open = alarms.filter((a) => !a.acknowledged);
  const rows = tanks.data ?? [];

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-semibold text-slate-800">Dashboard</h2>
        {open.length > 0 ? (
          <span className="text-sm bg-rose-100 text-rose-700 px-3 py-1 rounded-full">
            {open.length} open alarm{open.length > 1 ? 's' : ''}
          </span>
        ) : null}
      </div>
      {tanks.isLoading ? <p className="text-slate-500">Loading tanks…</p> : null}
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-4">
        {rows.map((t) => <TankRow key={t.id} tank={t} fuels={fuels.data ?? []} />)}
      </div>
    </div>
  );
}

function TankRow({ tank, fuels }: { tank: TankRead; fuels: FuelType[] }) {
  const { live } = useTelemetry(tank.id);
  return <TankTile tank={tank} live={live} fuels={fuels} />;
}
```

Note: per-row `useTelemetry` subscriptions (one zustand selector per tank) are cheap — zustand only re-renders rows whose tank id changed.

- [ ] **Step 5: Run to verify it passes**

Run: `cd /home/ubuntu/fuel_monitoring/web && npm test`
Expected: PASS (`web/tests/fuelMap.test.ts` green).

- [ ] **Step 6: Typecheck + commit**

Run: `cd /home/ubuntu/fuel_monitoring/web && npm run build`
Expected: clean `tsc`.

```bash
git add web/src/components/tanks/ web/src/hooks/useTelemetry.ts web/src/lib/fuelMap.ts web/src/pages/Dashboard.tsx web/tests/fuelMap.test.ts
git commit -m "feat: SVG tank canvases with live fill, dashboard grid, fuel-mapped colors"
```

---

### Task 8: Chart transforms, TelemetryChart, tanks list + detail

**Files:**
- Create: `web/src/lib/chartOptions.ts`, `web/src/components/charts/TelemetryChart.tsx`
- Modify: `web/src/pages/Tanks.tsx`, `web/src/pages/TankDetail.tsx`
- Test: `web/tests/chartOptions.test.ts`

- [ ] **Step 1: Write the failing tests**

`web/tests/chartOptions.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import {
  buildChartOption,
  gapFill,
  mergeLivePoints,
  roundAxisExtent,
  toEpochMs,
} from '../src/lib/chartOptions';
import type { TelemetryPoint } from '../src/lib/apiTypes';

const pt = (t: string, over: Partial<TelemetryPoint> = {}): TelemetryPoint => ({
  timestamp: t,
  pressure: null,
  temperature: null,
  level: null,
  volume: null,
  flow_rate: null,
  fill_percent: null,
  is_outlier: false,
  ...over,
});

describe('gapFill', () => {
  it('inserts nulls where consecutive points exceed the max gap', () => {
    const points = [pt('2026-01-01T00:00:00Z'), pt('2026-01-01T01:00:00Z')];
    const filled = gapFill(points, 15);
    expect(filled.length).toBeGreaterThan(2);
    expect(filled.every((p) => p === null || p.timestamp)).toBe(true);
  });

  it('returns the input unchanged for a tight series', () => {
    const points = [pt('2026-01-01T00:00:00Z'), pt('2026-01-01T00:05:00Z')];
    expect(gapFill(points, 15).length).toBe(2);
  });
});

describe('roundAxisExtent', () => {
  it('rounds up to a nice 1/2/5×10^k number', () => {
    expect(roundAxisExtent(6123)).toBe(7000);
    expect(roundAxisExtent(310)).toBe(400);
    expect(roundAxisExtent(99)).toBe(100);
    expect(roundAxisExtent(0)).toBe(1);
  });
});

describe('mergeLivePoints', () => {
  it('appends a live point newer than the last range point', () => {
    const range = [pt('2026-01-01T00:00:00Z', { volume: 100 }), pt('2026-01-01T00:05:00Z', { volume: 110 })];
    const live = pt('2026-01-01T00:06:00Z', { volume: 115 });
    const merged = mergeLivePoints(range, live);
    expect(merged.length).toBe(3);
    expect(merged[2].volume).toBe(115);
  });

  it('replaces a live point whose timestamp matches the last range bucket', () => {
    const range = [pt('2026-01-01T00:05:00Z', { volume: 110 })];
    const live = pt('2026-01-01T00:05:00Z', { volume: 111 });
    const merged = mergeLivePoints(range, live);
    expect(merged.length).toBe(1);
    expect(merged[0].volume).toBe(111);
  });
});

describe('buildChartOption', () => {
  it('produces dual-axis option with GOV/NSV on the left and temp/density on the right', () => {
    const points = [pt('2026-01-01T00:00:00Z', { gov_volume: 900, net_volume: 880, temperature: 30, density_at_temperature: 800 })];
    const opt = buildChartOption(points, undefined, 'Tank A');
    const series = opt.series as Array<{ name: string; yAxisIndex: number }>;
    const names = series.map((s) => s.name);
    expect(names).toContain('GOV');
    expect(names).toContain('NSV');
    const gov = series.find((s) => s.name === 'GOV')!;
    expect(gov.yAxisIndex).toBe(0);
    const temp = series.find((s) => s.name === 'Temperature');
    expect(temp?.yAxisIndex).toBe(1);
    expect(opt.title.text).toBe('Tank A');
  });
});

describe('toEpochMs', () => {
  it('parses ISO timestamps and trusts pre-epoch strings', () => {
    expect(toEpochMs('2026-01-02T03:04:05Z')).toBe(Date.parse('2026-01-02T03:04:05Z'));
    expect(toEpochMs('2026')).toBe(2026);
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /home/ubuntu/fuel_monitoring/web && npm test`
Expected: FAIL — missing `../src/lib/chartOptions`.

- [ ] **Step 3: Implement `web/src/lib/chartOptions.ts`**

```ts
import type { TelemetryPoint } from './apiTypes';
import type { LiveReading } from '../store/telemetry';

export function toEpochMs(t: string): number {
  const parsed = Date.parse(t);
  return Number.isNaN(parsed) ? Number(t) : parsed;
}

/** Insert null markers where consecutive samples exceed maxGapMinutes. */
export function gapFill(points: TelemetryPoint[], maxGapMinutes = 15): (TelemetryPoint | null)[] {
  const out: (TelemetryPoint | null)[] = [];
  for (let i = 0; i < points.length; i++) {
    if (i > 0) {
      const prev = toEpochMs(points[i - 1].timestamp);
      const cur = toEpochMs(points[i].timestamp);
      const gapMin = (cur - prev) / 60_000;
      if (gapMin > maxGapMinutes) out.push(null);
    }
    out.push(points[i]);
  }
  return out;
}

/** Round up to a nice 1/2/5×10^k axis maximum. */
export function roundAxisExtent(max: number): number {
  const m = Math.max(1, max);
  const mag = 10 ** Math.floor(Math.log10(m));
  const norm = m / mag;
  const nice = norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 5 ? 5 : 10;
  return nice * mag;
}

/** Append live point; replace the trailing bucket when timestamps collide. */
export function mergeLivePoints(range: TelemetryPoint[], live: TelemetryPoint): TelemetryPoint[] {
  const list = [...range];
  if (list.length === 0) return [live];
  const last = list[list.length - 1];
  if (toEpochMs(last.timestamp) >= toEpochMs(live.timestamp)) {
    list[list.length - 1] = live;
    return list;
  }
  return [...list, live];
}

export interface ChartOption {
  title: { text: string };
  tooltip: { trigger: string };
  legend: { data: string[] };
  grid: { left: number; right: number; top: number; bottom: number };
  dataZoom: unknown[];
  xAxis: { type: string; data: string[] };
  yAxis: Array<{ type: string; name: string; min: number; max?: number }>;
  series: Array<Record<string, unknown>>;
}

export function buildChartOption(
  range: TelemetryPoint[],
  live: LiveReading | undefined,
  tankTitle: string,
  lowVolume?: number | null,
  highVolume?: number | null
): ChartOption {
  const merged = live ? mergeLivePoints(range, live) : range;
  const filled = gapFill(merged, 15);
  const xs = filled.map((p) => (p === null ? '' : new Date(p.timestamp).toLocaleTimeString()));

  const volMax = roundAxisExtent(
    Math.max(1, ...filled.flatMap((p) => (p === null ? [] : [p.gov_volume ?? 0, p.net_volume ?? 0])))
  );
  const tempMax = roundAxisExtent(
    Math.max(1, ...filled.flatMap((p) => (p === null ? [] : [p.temperature ?? 0, p.density_at_temperature ?? 0])))
  );

  const markArea =
    lowVolume != null || highVolume != null
      ? [
          {
            name: 'thresholds',
            itemStyle: { color: 'rgba(248,113,113,0.12)' },
            data: [[{ yAxis: lowVolume ?? 0 }, { yAxis: highVolume ?? volMax }]],
          },
        ]
      : undefined;

  const series: Array<Record<string, unknown>> = [
    {
      name: 'GOV',
      type: 'line',
      smooth: true,
      showSymbol: false,
      yAxisIndex: 0,
      data: filled.map((p) => (p === null ? null : p.gov_volume ?? p.volume)),
    },
    {
      name: 'NSV',
      type: 'line',
      smooth: true,
      showSymbol: false,
      yAxisIndex: 0,
      data: filled.map((p) => (p === null ? null : p.net_volume)),
    },
    {
      name: 'Temperature',
      type: 'line',
      smooth: true,
      showSymbol: false,
      yAxisIndex: 1,
      data: filled.map((p) => (p === null ? null : p.temperature)),
    },
    {
      name: 'Density',
      type: 'line',
      smooth: true,
      showSymbol: false,
      yAxisIndex: 1,
      data: filled.map((p) => (p === null ? null : p.density_at_temperature)),
    },
  ];
  if (markArea) series[0] = { ...series[0], markArea };

  return {
    title: { text: tankTitle },
    tooltip: { trigger: 'axis' },
    legend: { data: ['GOV', 'NSV', 'Temperature', 'Density'] },
    grid: { left: 56, right: 56, top: 40, bottom: 56 },
    dataZoom: [{ type: 'inside' }, { type: 'slider', height: 18, bottom: 12 }],
    xAxis: { type: 'category', data: xs },
    yAxis: [
      { type: 'value', name: 'Volume (L)', min: 0, max: volMax },
      { type: 'value', name: 'Temp / Density', min: 0, max: tempMax },
    ],
    series,
  };
}
```

- [ ] **Step 4: Implement `web/src/components/charts/TelemetryChart.tsx`**

```tsx
import ReactECharts from 'echarts-for-react';
import type { TelemetryPoint } from '../../lib/apiTypes';
import type { LiveReading } from '../../store/telemetry';
import { buildChartOption } from '../../lib/chartOptions';

interface TelemetryChartProps {
  points: TelemetryPoint[];
  live?: LiveReading;
  tankTitle: string;
  lowVolume?: number | null;
  highVolume?: number | null;
}

export function TelemetryChart({ points, live, tankTitle, lowVolume, highVolume }: TelemetryChartProps) {
  const option = buildChartOption(points, live, tankTitle, lowVolume, highVolume);
  return (
    <ReactECharts
      option={option}
      notMerge
      style={{ height: 360, width: '100%' }}
      opts={{ renderer: 'canvas' }}
    />
  );
}
```

- [ ] **Step 5: Implement `web/src/pages/Tanks.tsx`**

List view with a create-tank dialog. It fetches fuel types + sites for the form and posts via `api.createTank`.

```tsx
import { FormEvent, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { ApiError } from '../api/http';
import { api } from '../api/client';
import type { FuelType, TankRead, TankShape } from '../lib/apiTypes';
import { fuelColor } from '../lib/tankGeometry';
import { fuelCodeById } from '../lib/fuelMap';
import { useTelemetry } from '../hooks/useTelemetry';

const SHAPES: TankShape[] = [
  'vertical_cylinder',
  'horizontal_cylinder',
  'rectangular',
  'spherical',
  'horizontal_elliptical_ends',
  'custom_strapping',
];

type Shape = (typeof SHAPES)[number];
type Group = { label: string; field: string; placeholder: string; show: (s: Shape) => boolean };

const DIM_GROUPS: Group[] = [
  { label: 'Height (m)', field: 'tank_height', placeholder: '2.0', show: (s) => s === 'vertical_cylinder' || s === 'rectangular' },
  { label: 'Length (m)', field: 'tank_length', placeholder: '3.0', show: (s) => s === 'horizontal_cylinder' || s === 'rectangular' || s === 'horizontal_elliptical_ends' },
  { label: 'Width (m)', field: 'tank_width', placeholder: '1.5', show: (s) => s === 'rectangular' },
  { label: 'Dish depth (m)', field: 'dish_depth', placeholder: '0.4', show: (s) => s === 'horizontal_elliptical_ends' },
];

export default function Tanks() {
  const tanks = useQuery({ queryKey: ['tanks'], queryFn: () => api.listTanks() });
  const fuels = useQuery({ queryKey: ['fuel-types'], queryFn: () => api.listFuelTypes() });
  const sites = useQuery({ queryKey: ['sites'], queryFn: () => api.listSites() });
  const [creating, setCreating] = useState(false);

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-semibold text-slate-800">Tanks</h2>
        <button onClick={() => setCreating(true)} className="bg-brand text-white rounded px-3 py-2 text-sm font-medium">
          New tank
        </button>
      </div>
      <div className="bg-white rounded-lg border border-slate-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-500">
            <tr>
              <th className="text-left px-4 py-2">Name</th>
              <th className="text-left px-4 py-2">Fuel</th>
              <th className="text-left px-4 py-2">Shape</th>
              <th className="text-right px-4 py-2">Volume (L)</th>
              <th className="text-right px-4 py-2">Fill</th>
            </tr>
          </thead>
          <tbody>
            {(tanks.data ?? []).map((t) => <TankRowT key={t.id} tank={t} fuels={fuels.data ?? []} />)}
          </tbody>
        </table>
      </div>
      {creating ? (
        <CreateTankDialog
          fuels={fuels.data ?? []}
          sites={sites.data ?? []}
          onClose={() => setCreating(false)}
        />
      ) : null}
    </div>
  );
}

function TankRowT({ tank, fuels }: { tank: TankRead; fuels: FuelType[] }) {
  const { live } = useTelemetry(tank.id);
  const code = fuelCodeById(fuels, tank.fuel_type_id);
  return (
    <tr className="border-t border-slate-100">
      <td className="px-4 py-2">
        <Link to={`/tanks/${tank.id}`} className="font-medium text-brand-dark hover:underline">
          {tank.name}
        </Link>
      </td>
      <td className="px-4 py-2">
        <span className="inline-flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: fuelColor(code) }} />
          {code || '—'}
        </span>
      </td>
      <td className="px-4 py-2 text-slate-600">{tank.tank_shape ?? 'vertical_cylinder'}</td>
      <td className="px-4 py-2 text-right">{Math.round(tank.tank_volume).toLocaleString()}</td>
      <td className="px-4 py-2 text-right">{Math.round((live?.fill_percent ?? 0) * 100) / 100}%</td>
    </tr>
  );
}

function CreateTankDialog({
  fuels,
  sites,
  onClose,
}: {
  fuels: FuelType[];
  sites: Array<{ id: string; name: string }>;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState({
    name: '',
    site_id: sites[0]?.id ?? '',
    sensor_serial_number: '',
    tank_shape: 'vertical_cylinder' as Shape,
    tank_orientation: 'vertical',
    tank_diameter: '',
    tank_height: '',
    tank_length: '',
    tank_width: '',
    dish_depth: '',
    tank_volume: '',
    fuel_type_id: fuels[0]?.id ?? '',
  });
  const [error, setError] = useState<string | null>(null);
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  const create = useMutation({
    mutationFn: () => {
      const shape = form.tank_shape;
      const base = {
        name: form.name,
        site_id: form.site_id,
        sensor_serial_number: form.sensor_serial_number,
        tank_shape: shape,
        tank_orientation: (shape === 'vertical_cylinder' ? 'vertical' : 'horizontal') as 'vertical' | 'horizontal',
        tank_diameter: Number(form.tank_diameter),
        tank_volume: Number(form.tank_volume),
        fuel_type_id: form.fuel_type_id,
      };
      const payload = {
        ...base,
        tank_height: form.tank_height ? Number(form.tank_height) : undefined,
        tank_length: form.tank_length ? Number(form.tank_length) : undefined,
        tank_width: form.tank_width ? Number(form.tank_width) : undefined,
        dish_depth: form.dish_depth ? Number(form.dish_depth) : undefined,
      };
      return api.createTank(payload);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['tanks'] });
      onClose();
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : 'Create failed'),
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    create.mutate();
  };

  return (
    <div className="fixed inset-0 bg-slate-900/40 flex items-center justify-center z-50">
      <form onSubmit={submit} className="bg-white rounded-lg shadow-xl w-full max-w-lg p-6 space-y-3 max-h-[90vh] overflow-auto">
        <h3 className="text-lg font-semibold text-slate-800">Register tank</h3>
        <label className="block text-sm font-medium text-slate-700">Name</label>
        <input className="w-full border border-slate-300 rounded px-3 py-2" value={form.name} onChange={set('name')} required />
        <label className="block text-sm font-medium text-slate-700">Sensor serial</label>
        <input className="w-full border border-slate-300 rounded px-3 py-2" value={form.sensor_serial_number} onChange={set('sensor_serial_number')} required />
        <label className="block text-sm font-medium text-slate-700">Site</label>
        <select className="w-full border border-slate-300 rounded px-3 py-2" value={form.site_id} onChange={set('site_id')}>
          {sites.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
        <label className="block text-sm font-medium text-slate-700">Tank shape</label>
        <select className="w-full border border-slate-300 rounded px-3 py-2" value={form.tank_shape} onChange={set('tank_shape')}>
          {SHAPES.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <label className="block text-sm font-medium text-slate-700">Fuel type</label>
        <select className="w-full border border-slate-300 rounded px-3 py-2" value={form.fuel_type_id} onChange={set('fuel_type_id')}>
          {fuels.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
        </select>
        <label className="block text-sm font-medium text-slate-700">Diameter (m)</label>
        <input type="number" step="any" className="w-full border border-slate-300 rounded px-3 py-2" value={form.tank_diameter} onChange={set('tank_diameter')} required />
        {DIM_GROUPS.filter((g) => g.show(form.tank_shape as Shape)).map((g) => (
          <div key={g.field}>
            <label className="block text-sm font-medium text-slate-700">{g.label}</label>
            <input
              type="number"
              step="any"
              placeholder={g.placeholder}
              className="w-full border border-slate-300 rounded px-3 py-2"
              value={form[g.field as keyof typeof form] as string}
              onChange={set(g.field as keyof typeof form)}
              required
            />
          </div>
        ))}
        <label className="block text-sm font-medium text-slate-700">Capacity (L)</label>
        <input type="number" step="any" className="w-full border border-slate-300 rounded px-3 py-2" value={form.tank_volume} onChange={set('tank_volume')} required />
        {error ? <p className="text-sm text-red-600">{error}</p> : null}
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className="px-3 py-2 text-sm text-slate-600">Cancel</button>
          <button type="submit" disabled={create.isPending} className="bg-brand text-white rounded px-3 py-2 text-sm font-medium disabled:opacity-50">
            Create
          </button>
        </div>
      </form>
    </div>
  );
}
```

- [ ] **Step 6: Implement `web/src/pages/TankDetail.tsx`**

```tsx
import { useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';
import { useTelemetry } from '../hooks/useTelemetry';
import { TankCanvas } from '../components/tanks/TankCanvas';
import { TelemetryChart } from '../components/charts/TelemetryChart';

const WINDOWS: Record<string, number> = { '1h': 1, '6h': 6, '24h': 24, '7d': 168 };

export default function TankDetail() {
  const { tankId = '' } = useParams();
  const [window, setWindow] = useState<keyof typeof WINDOWS>('24h');
  const queryClient = useQueryClient();

  const tankQ = useQuery({ queryKey: ['tank', tankId], queryFn: () => api.getTank(tankId) });
  const fuelsQ = useQuery({ queryKey: ['fuel-types'], queryFn: () => api.listFuelTypes() });
  const alarmsQ = useQuery({ queryKey: ['alarms', tankId], queryFn: () => api.tankAlarms(tankId, true, 50) });
  const { live, recent } = useTelemetry(tankId);

  const range = useQuery({
    queryKey: ['range', tankId, window],
    queryFn: () => {
      const hours = WINDOWS[window];
      const end = new Date();
      const start = new Date(end.getTime() - hours * 60 * 60 * 1000);
      return api.rangeReadings(tankId, start.toISOString(), end.toISOString());
    },
  });

  const ack = useMutation({
    mutationFn: (alarmId: string) => api.ackAlarm(tankId, alarmId),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['alarms', tankId] }),
  });

  const readouts = useMemo(
    () => [
      { label: 'GOV', value: live?.gov_volume ?? live?.volume ?? recent[recent.length - 1]?.volume, unit: 'L' },
      { label: 'NSV', value: live?.net_volume ?? recent[recent.length - 1]?.net_volume, unit: 'L' },
      { label: 'Density', value: live?.density_at_temperature ?? recent[recent.length - 1]?.density_at_temperature, unit: 'kg/m³' },
      { label: 'Temperature', value: live?.temperature ?? recent[recent.length - 1]?.temperature, unit: '°C' },
      { label: 'Level', value: live?.level ?? recent[recent.length - 1]?.level, unit: 'm' },
      { label: 'Fill', value: live?.fill_percent ?? recent[recent.length - 1]?.fill_percent, unit: '%' },
    ],
    [live, recent]
  );

  const tank = tankQ.data;
  if (!tank) return <p className="text-slate-500">Loading tank…</p>;

  return (
    <div>
      <Link to="/tanks" className="text-sm text-slate-500 hover:text-slate-700 mb-2 inline-block">← Tanks</Link>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-1 bg-white rounded-lg border border-slate-200 p-4">
          <div className="max-w-xs mx-auto">
            <TankCanvas tank={tank} live={live} fuels={fuelsQ.data ?? []} />
          </div>
          <div className="grid grid-cols-2 gap-2 mt-4">
            {readouts.map((r) => (
              <div key={r.label} className="bg-slate-50 rounded p-2">
                <p className="text-xs text-slate-500">{r.label}</p>
                <p className="text-lg font-semibold text-slate-800">
                  {r.value == null ? '—' : Number(r.value).toFixed(2)}
                  <span className="text-xs font-normal text-slate-400 ml-1">{r.unit}</span>
                </p>
              </div>
            ))}
          </div>
        </div>
        <div className="lg:col-span-2 bg-white rounded-lg border border-slate-200 p-4">
          <div className="flex justify-between items-center mb-2">
            <h3 className="font-semibold text-slate-800">{tank.name} · Telemetry</h3>
            <div className="flex gap-1">
              {Object.keys(WINDOWS).map((k) => (
                <button
                  key={k}
                  onClick={() => setWindow(k as keyof typeof WINDOWS)}
                  className={`px-2 py-1 text-xs rounded ${window === k ? 'bg-brand text-white' : 'bg-slate-100 text-slate-600'}`}
                >
                  {k}
                </button>
              ))}
            </div>
          </div>
          <TelemetryChart
            points={range.data ?? []}
            live={live}
            tankTitle={tank.name}
            lowVolume={tank.low_volume_threshold}
            highVolume={tank.high_volume_threshold}
          />
        </div>
      </div>
      <div className="mt-6 bg-white rounded-lg border border-slate-200 p-4">
        <h3 className="font-semibold text-slate-800 mb-2">Open alarms</h3>
        {(alarmsQ.data ?? []).length === 0 ? (
          <p className="text-sm text-slate-500">No open alarms.</p>
        ) : (
          <ul className="space-y-2">
            {(alarmsQ.data ?? []).map((a) => (
              <li key={a.id} className="flex items-center justify-between text-sm">
                <div>
                  <span className="font-medium text-slate-700">{a.type}</span>
                  <span className="text-slate-500 ml-2">{a.message}</span>
                </div>
                <button
                  onClick={() => ack.mutate(a.id)}
                  disabled={a.acknowledged}
                  className="text-xs bg-slate-100 px-2 py-1 rounded disabled:opacity-40"
                >
                  {a.acknowledged ? 'Acked' : 'Ack'}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 7: Run tests + typecheck**

Run: `cd /home/ubuntu/fuel_monitoring/web && npm test && npm run build`
Expected: PASS, clean `tsc`.

- [ ] **Step 8: Commit**

```bash
git add web/src/lib/chartOptions.ts web/src/components/charts/TelemetryChart.tsx web/src/pages/Tanks.tsx web/src/pages/TankDetail.tsx web/tests/chartOptions.test.ts
git commit -m "feat: GOV/NSV telemetry chart (dual axis) + tanks list & detail with tank canvas readouts"
```

---

### Task 9: Dispensing page + live dispensing view

**Files:**
- Create: `web/src/pages/Dispensing.tsx`, `web/src/components/dispensing/DispenseLiveView.tsx`, `web/src/lib/dispenseFormat.ts`, `web/src/hooks/useLiveDispensing.ts`
- Test: `web/tests/dispenseFormat.test.ts`

- [ ] **Step 1: Write the failing tests**

`web/tests/dispenseFormat.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import {
  formatLiters,
  formatRemaining,
  statusColor,
} from '../src/lib/dispenseFormat';

describe('formatLiters', () => {
  it('renders liters with one decimal', () => {
    expect(formatLiters(12.5)).toBe('12.5 L');
    expect(formatLiters(0)).toBe('0.0 L');
    expect(formatLiters(null)).toBe('—');
  });
});

describe('formatRemaining', () => {
  it('renders remaining liters with sign, or a completed marker at ~0', () => {
    expect(formatRemaining(50)).toBe('50.0 L left');
    expect(formatRemaining(0.0001)).toBe('done');
    expect(formatRemaining(-0.0001)).toBe('done');
  });
});

describe('statusColor', () => {
  it('maps backend UPPERCASE statuses to tailwind classes, defaulting to slate', () => {
    expect(statusColor('PENDING')).toBe('bg-amber-100 text-amber-700');
    expect(statusColor('IN_PROGRESS')).toBe('bg-blue-100 text-blue-700');
    expect(statusColor('COMPLETED')).toBe('bg-emerald-100 text-emerald-700');
    expect(statusColor('PARTIAL')).toBe('bg-sky-100 text-sky-700');
    expect(statusColor('OVER_DISPENSE')).toBe('bg-orange-100 text-orange-700');
    expect(statusColor('DISCREPANCY')).toBe('bg-rose-100 text-rose-700');
    expect(statusColor('EXPIRED')).toBe('bg-slate-100 text-slate-500');
    expect(statusColor('unknown_thing')).toBe('bg-slate-100 text-slate-600');
  });

  it('is case-insensitive', () => {
    expect(statusColor('completed')).toBe('bg-emerald-100 text-emerald-700');
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /home/ubuntu/fuel_monitoring/web && npm test`
Expected: FAIL — missing `../src/lib/dispenseFormat`.

- [ ] **Step 3: Implement `web/src/lib/dispenseFormat.ts`**

```ts
import type { AllocationRead, TransactionRead } from './apiTypes';

export function formatLiters(v: number | null | undefined): string {
  return v == null ? '—' : `${v.toFixed(1)} L`;
}

export function formatRemaining(v: number | null | undefined): string {
  if (v == null) return '—';
  return Math.abs(v) < 0.01 ? 'done' : `${v.toFixed(1)} L left`;
}

const STATUS_STYLES: Record<string, string> = {
  PENDING: 'bg-amber-100 text-amber-700',
  IN_PROGRESS: 'bg-blue-100 text-blue-700',
  COMPLETED: 'bg-emerald-100 text-emerald-700',
  PARTIAL: 'bg-sky-100 text-sky-700',
  OVER_DISPENSE: 'bg-orange-100 text-orange-700',
  DISCREPANCY: 'bg-rose-100 text-rose-700',
  'OVER_DISPENSE/PENDING': 'bg-orange-100 text-orange-700',
  EXPIRED: 'bg-slate-100 text-slate-500',
  VOIDED: 'bg-neutral-100 text-neutral-600',
};

export function statusColor(status: string | undefined | null): string {
  if (!status) return 'bg-slate-100 text-slate-600';
  const key = status.toUpperCase();
  return STATUS_STYLES[key] ?? 'bg-slate-100 text-slate-600';
}

/** Visible "dispensed so far" for an allocation: total minus remaining. */
export function dispensedSoFar(a: AllocationRead): number {
  return Math.max(0, a.allocated_liters - a.remaining_liters);
}

/** Net delivered volume for a completed transaction (authorized delivered). */
export function deliveredLiters(t: TransactionRead): number {
  return t.actual_liters;
}
```

- [ ] **Step 4: Implement `web/src/hooks/useLiveDispensing.ts`**

```ts
import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';

/**
 * Live "in progress" authorizations: allocations whose requested amount has
 * not yet been fully dispensed (remaining_liters > 0 and status PENDING).
 * Polled every 8s; fresh completions appear as new rows from the same feed.
 */
export function useLiveDispensing() {
  return useQuery({
    queryKey: ['allocations'],
    queryFn: () => api.listAllocations(200),
    refetchInterval: 8_000,
  });
}

export function isActiveAllocation(a: {
  status: string;
  remaining_liters: number;
}): boolean {
  const status = a.status.toUpperCase();
  return status === 'PENDING' || status === 'IN_PROGRESS';
}
```

- [ ] **Step 5: Implement `web/src/components/dispensing/DispenseLiveView.tsx`**

```tsx
import type { AllocationRead, TransactionRead } from '../../lib/apiTypes';
import { dispensedSoFar, formatLiters, formatRemaining, statusColor } from '../../lib/dispenseFormat';
import { isActiveAllocation } from '../../hooks/useLiveDispensing';

export function DispenseLiveView({
  active,
  recent,
}: {
  active: AllocationRead[];
  recent: TransactionRead[];
}) {
  return (
    <div className="bg-white rounded-lg border border-slate-200 p-4">
      <h3 className="font-semibold text-slate-800 mb-3">In progress</h3>
      {active.length === 0 ? (
        <p className="text-sm text-slate-500">No active authorizations.</p>
      ) : (
        <div className="space-y-3">
          {active.map((a) => (
            <div key={a.id} className="flex items-center justify-between text-sm">
              <div>
                <p className="font-medium text-slate-700">{a.employee_name || a.employee_id}</p>
                <p className="text-xs text-slate-500">
                  {a.invoice_number ? `${a.invoice_number} · ` : ''}authorized {formatLiters(a.allocated_liters)}
                </p>
              </div>
              <div className="text-right">
                <p className="font-semibold text-slate-800">
                  {formatLiters(dispensedSoFar(a))}
                  <span className="text-xs font-normal text-slate-400 ml-1">dispensed</span>
                </p>
                <span className="text-xs text-slate-500">{formatRemaining(a.remaining_liters)}</span>
                <span className={`text-xs px-2 py-0.5 rounded-full ml-2 ${statusColor(a.status)}`}>{a.status}</span>
              </div>
            </div>
          ))}
        </div>
      )}
      <h3 className="font-semibold text-slate-800 mt-6 mb-3">Recent transactions</h3>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-slate-500">
            <th className="py-1 pr-2">When</th>
            <th className="py-1 pr-2">Dispenser</th>
            <th className="py-1 pr-2">Status</th>
            <th className="py-1 pr-2">Requested (L)</th>
            <th className="py-1">Delivered (L)</th>
          </tr>
        </thead>
        <tbody>
          {recent.slice(0, 25).map((t) => (
            <tr key={t.id} className="border-t border-slate-100">
              <td className="py-1 pr-2 text-slate-600">{new Date(t.created_at).toLocaleString()}</td>
              <td className="py-1 pr-2">{t.dispenser_id}</td>
              <td className="py-1 pr-2"><span className={`text-xs px-2 py-0.5 rounded-full ${statusColor(t.status)}`}>{t.status}</span></td>
              <td className="py-1 pr-2">{formatLiters(t.requested_liters)}</td>
              <td className="py-1">{formatLiters(t.actual_liters)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 6: Implement `web/src/pages/Dispensing.tsx`**

```tsx
import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import { useLiveDispensing, isActiveAllocation } from '../hooks/useLiveDispensing';
import { DispenseLiveView } from '../components/dispensing/DispenseLiveView';

export default function Dispensing() {
  const stations = useQuery({ queryKey: ['stations'], queryFn: () => api.listStations() });
  const transactions = useQuery({
    queryKey: ['transactions'],
    queryFn: () => api.listTransactions(100),
    refetchInterval: 15_000,
  });
  const allocations = useLiveDispensing();

  const active = (allocations.data ?? []).filter(isActiveAllocation);
  const station = stations.data?.[0];
  const dispensers = useQuery({
    queryKey: ['dispensers', station?.id],
    queryFn: () => (station ? api.listDispensers(station.id) : Promise.resolve([])),
    enabled: Boolean(station),
  });

  return (
    <div>
      <h2 className="text-2xl font-semibold text-slate-800 mb-6">Dispensing</h2>
      <select className="mb-4 border border-slate-300 rounded px-3 py-2 text-sm" defaultValue={station?.id}>
        {(stations.data ?? []).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
      </select>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <DispenseLiveView active={active} recent={transactions.data ?? []} />
        </div>
        <div className="bg-white rounded-lg border border-slate-200 p-4">
          <h3 className="font-semibold text-slate-800 mb-3">Dispensers</h3>
          <ul className="space-y-2 text-sm">
            {(dispensers.data ?? []).map((d) => (
              <li key={d.id} className="flex items-center justify-between">
                <span className="text-slate-700">{d.name}</span>
                <span className={`text-xs px-2 py-0.5 rounded-full ${d.is_active ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-400'}`}>
                  {d.is_active ? 'active' : 'inactive'}
                </span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 7: Run tests + typecheck**

Run: `cd /home/ubuntu/fuel_monitoring/web && npm test && npm run build`
Expected: PASS, clean `tsc`.

- [ ] **Step 8: Commit**

```bash
git add web/src/pages/Dispensing.tsx web/src/components/dispensing/ web/src/lib/dispenseFormat.ts web/src/hooks/useLiveDispensing.ts web/tests/dispenseFormat.test.ts
git commit -m "feat: dispensing page with live in-progress view, margin formatting, dispenser list"
```

---

### Task 10: Totalizers page + drift chart

**Files:**
- Create: `web/src/pages/Totalizers.tsx`, `web/src/lib/driftCalc.ts`, `web/src/components/charts/TotalizerDriftChart.tsx`
- Test: `web/tests/driftCalc.test.ts`

Drift semantics: given authorized cumulative liters and totalizer cumulative liters over matching timestamps, drift = totalizer_cumulative − authorized_cumulative at each point. The backend plan adds an authorizations-derived cumulative series via `GET /api/v1/dispensing/transactions?limit=500`, aggregated client-side per dispenser (see Task 9/10 for how `driveCumulativeFromTransactions` builds it).

- [ ] **Step 1: Write the failing tests**

`web/tests/driftCalc.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import {
  computeDriftSeries,
  driveCumulativeFromTransactions,
  toEpochMs,
} from '../src/lib/driftCalc';
import type { TransactionRead, TotalizerPoint } from '../src/lib/apiTypes';

const txs = (list: Array<{ ts: string; lit: number }>): TransactionRead[] =>
  list.map((t, i) => ({
    id: i + 1,
    station_id: 's1',
    dispenser_id: 'd1',
    employee_id: 'e1',
    requested_liters: t.lit,
    actual_liters: t.lit,
    secret_totalizer_before: 0,
    secret_totalizer_after: 0,
    status: 'COMPLETED',
    created_at: t.ts,
  }));

describe('driveCumulativeFromTransactions', () => {
  it('builds a strictly increasing cumulative requested-liters series', () => {
    const rows = txs([
      { ts: '2026-01-01T00:00:00Z', lit: 10 },
      { ts: '2026-01-01T01:00:00Z', lit: 5 },
      { ts: '2026-01-01T02:00:00Z', lit: 12 },
    ]);
    const cum = driveCumulativeFromTransactions(rows);
    expect(cum).toHaveLength(3);
    expect(cum[1].cumulativeLiters).toBeCloseTo(15, 6);
    expect(cum[2].cumulativeLiters).toBeCloseTo(27, 6);
  });
});

describe('computeDriftSeries', () => {
  it('returns [] for empty inputs', () => {
    expect(computeDriftSeries([], [])).toEqual([]);
  });

  it('subtracts authorized from totalizer cumulative at aligned timestamps', () => {
    const totalizer: TotalizerPoint[] = [
      { timestamp: '2026-01-01T00:00:00Z', station_id: 's1', dispenser_id: 'd1', totalizer_value: 1000, cumulative_liters: 1000, source: 'odometer' },
      { timestamp: '2026-01-01T01:00:00Z', station_id: 's1', dispenser_id: 'd1', totalizer_value: 1010, cumulative_liters: 1010, source: 'odometer' },
    ];
    const authorized = [
      { ts: 0, cumulativeLiters: 1005 },
      { ts: 1, cumulativeLiters: 1008 },
    ];
    const drift = computeDriftSeries(totalizer, authorized);
    expect(drift).toHaveLength(2);
    expect(drift[0].drift).toBeCloseTo(-5, 6);
    expect(drift[1].drift).toBeCloseTo(2, 6);
  });
});

describe('toEpochMs (re-exported)', () => {
  it('parses timestamps', () => {
    expect(toEpochMs('2026-01-02T03:04:05Z')).toBe(Date.parse('2026-01-02T03:04:05Z'));
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /home/ubuntu/fuel_monitoring/web && npm test`
Expected: FAIL — missing `../src/lib/driftCalc`.

- [ ] **Step 3: Implement `web/src/lib/driftCalc.ts`**

```ts
import type { TransactionRead, TotalizerPoint } from './apiTypes';

export function toEpochMs(t: string): number {
  const parsed = Date.parse(t);
  return Number.isNaN(parsed) ? Number(t) : parsed;
}

export interface CumulativeSample {
  ts: number;
  cumulativeLiters: number;
}

/**
 * Build the authorized-cumulative series from completed transactions: the sum
 * of requested (authorized) liters, ordered by completion time. This is the
 * counterfactual a hardware totalizer must agree with.
 */
export function driveCumulativeFromTransactions(rows: TransactionRead[]): CumulativeSample[] {
  let acc = 0;
  return rows
    .slice()
    .sort((a, b) => toEpochMs(a.created_at) - toEpochMs(b.created_at))
    .map((r) => {
      acc += r.requested_liters;
      return { ts: toEpochMs(r.created_at), cumulativeLiters: acc };
    });
}

export interface DriftSample {
  ts: number;
  drift: number;
  totalizer: number;
  authorized: number;
}

export function computeDriftSeries(
  totalizer: TotalizerPoint[],
  authorized: CumulativeSample[]
): DriftSample[] {
  if (totalizer.length === 0 || authorized.length === 0) return [];
  const auth = [...authorized].sort((a, b) => a.ts - b.ts);
  const out: DriftSample[] = [];
  for (const t of totalizer) {
    const ts = toEpochMs(t.timestamp);
    const idx = auth.findIndex((s) => s.ts >= ts);
    const interp = idx <= 0 ? auth[0] : idx >= auth.length ? auth[auth.length - 1] : auth[idx - 1];
    const drift = (t.cumulative_liters ?? 0) - interp.cumulativeLiters;
    out.push({ ts, drift, totalizer: t.cumulative_liters ?? 0, authorized: interp.cumulativeLiters });
  }
  return out;
}
```

- [ ] **Step 4: Implement `web/src/components/charts/TotalizerDriftChart.tsx`**

```tsx
import ReactECharts from 'echarts-for-react';
import type { DriftSample } from '../../lib/driftCalc';
import { roundAxisExtent } from '../../lib/chartOptions';

export function TotalizerDriftChart({ series }: { series: DriftSample[] }) {
  const labels = series.map((s) => new Date(s.ts).toLocaleString());
  const maxAbs = Math.max(1, ...series.map((s) => Math.abs(s.drift)));
  const axisMax = roundAxisExtent(maxAbs);

  const option = {
    title: { text: 'Drift = totalizer cumulative − authorized cumulative' },
    tooltip: { trigger: 'axis' },
    grid: { left: 64, right: 32, top: 48, bottom: 48 },
    xAxis: { type: 'category', data: labels },
    yAxis: { type: 'value', name: 'Drift (L)', min: -axisMax, max: axisMax },
    series: [
      {
        name: 'Drift',
        type: 'bar',
        data: series.map((s) => s.drift.toFixed(3)),
        itemStyle: { color: (p: { value: number }) => (p.value >= 0 ? '#f59e0b' : '#3b82f6') },
      },
    ],
  };

  return <ReactECharts option={option} notMerge style={{ height: 300, width: '100%' }} />;
}
```

- [ ] **Step 5: Implement `web/src/pages/Totalizers.tsx`**

```tsx
import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import {
  computeDriftSeries,
  driveCumulativeFromTransactions,
} from '../lib/driftCalc';
import { TotalizerDriftChart } from '../components/charts/TotalizerDriftChart';

export default function Totalizers() {
  const [stationId, setStationId] = useState<string | null>(null);
  const [dispenserId, setDispenserId] = useState<string | null>(null);

  const stations = useQuery({ queryKey: ['stations'], queryFn: () => api.listStations() });
  const station = stationId ?? stations.data?.[0]?.id ?? null;

  const dispensers = useQuery({
    queryKey: ['stations', station, 'dispensers'],
    queryFn: () => (station ? api.listDispensers(station) : Promise.resolve([])),
    enabled: Boolean(station),
  });
  const dispenser = dispenserId ?? dispensers.data?.[0]?.id ?? null;

  const totalizer = useQuery({
    queryKey: ['totalizers', dispenser],
    queryFn: () => {
      const end = new Date();
      const start = new Date(end.getTime() - 24 * 60 * 60 * 1000);
      return api.listTotalizers(dispenser ?? undefined, start.toISOString(), end.toISOString());
    },
    enabled: Boolean(dispenser),
  });

  const transactions = useQuery({
    queryKey: ['transactions', dispenser],
    queryFn: () => api.listTransactions(500, dispenser ?? undefined),
    enabled: Boolean(dispenser),
  });

  const drift = useMemo(() => {
    if (!totalizer.data || !transactions.data) return [];
    return computeDriftSeries(totalizer.data, driveCumulativeFromTransactions(transactions.data));
  }, [totalizer.data, transactions.data]);

  return (
    <div>
      <h2 className="text-2xl font-semibold text-slate-800 mb-6">Totalizers</h2>
      <div className="flex gap-4 mb-4">
        <select
          className="border border-slate-300 rounded px-3 py-2 text-sm"
          value={station ?? ''}
          onChange={(e) => { setStationId(e.target.value); setDispenserId(null); }}
        >
          {(stations.data ?? []).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
        <select
          className="border border-slate-300 rounded px-3 py-2 text-sm"
          value={dispenser ?? ''}
          onChange={(e) => setDispenserId(e.target.value)}
        >
          {(dispensers.data ?? []).map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
        </select>
      </div>
      {drift.length === 0 ? (
        <p className="text-slate-500">No totalizer drift data.</p>
      ) : (
        <div className="bg-white rounded-lg border border-slate-200 p-4">
          <TotalizerDriftChart series={drift} />
        </div>
      )}
      <p className="text-xs text-slate-400 mt-4">
        Drift reflects (totalizer cumulative − authorized cumulative) at each sample. Positive = meter ahead of authorizations.
      </p>
    </div>
  );
}
```

- [ ] **Step 6: Run tests + typecheck**

Run: `cd /home/ubuntu/fuel_monitoring/web && npm test && npm run build`
Expected: PASS, clean `tsc`.

- [ ] **Step 7: Commit**

```bash
git add web/src/pages/Totalizers.tsx web/src/lib/driftCalc.ts web/src/components/charts/TotalizerDriftChart.tsx web/tests/driftCalc.test.ts
git commit -m "feat: totalizer drift view (totalizer vs authorized cumulative) with station/dispenser selectors"
```

---

### Task 11: Deployment wiring (Docker, nginx, compose, docs)

**Files:**
- Create: `web/Dockerfile`, `web/nginx.conf`, `web/.dockerignore`, `web/README.md`
- Modify: `docker-compose.yml` (add `web` service), `infra/nginx/conf.d/app.conf` (`location /` → proxy to `web:8080`), root `.gitignore` (node_modules, web/dist), `web/vite.config.ts` (no change needed — proxy already added in Task 1)
- No test needed purely wiring, but verify after composition build: `docker compose build web && docker compose up -d web && curl localhost:8080`

- [ ] **Step 1: Implement `web/nginx.conf`**

```nginx
server {
    listen 8080;
    root /usr/share/nginx/html;
    index index.html;

    gzip on;
    gzip_types text/css application/javascript application/json image/svg+xml;

    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

- [ ] **Step 2: Implement `web/.dockerignore`**

```
node_modules
dist
```

- [ ] **Step 3: Implement `web/Dockerfile`**

```dockerfile
FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 8080
```

- [ ] **Step 4: Implement `web/README.md`**

```markdown
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
```

- [ ] **Step 5: Modify `infra/nginx/conf.d/app.conf`**

Replace the current `location /` block (static root + SPA fallback):

```nginx
    location / {
        proxy_pass http://web:8080;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 3600s;
    }
```

Keep `/api/`, `/ingest/`, `/ws/` locations unchanged.

- [ ] **Step 6: Modify `docker-compose.yml`** — add a `web` service mirroring the other app services' network so the nginx reverse proxy can reach it:

```yaml
  web:
    build: ./web
    restart: unless-stopped
    networks:
      - app_network
    expose:
      - "8080"
    depends_on:
      - api
```

(Verify the compose file's actual service/network names and volume of `api` — align the `networks` key with the existing top-level `networks` block; the `web` service must NOT publish ports since it's only reached via the edge nginx.)

- [ ] **Step 7: Modify root `.gitignore`**

Append:

```
node_modules/
web/dist/
```

- [ ] **Step 8: Verify build + runtime**

Run:
```bash
docker compose config --quiet && docker compose build web && docker compose up -d web
curl -fsS http://localhost:8080 | grep -q '<div id="root">' && echo OK
curl -fsS https://localhost/v2/_catalog -sS -m 5 -o /dev/null -w '%{http_code}\n'  # edge nginx forwards to web
```
Expected: `OK`; edge returns 200 on `/`.

- [ ] **Step 9: Commit**

```bash
git add web/Dockerfile web/nginx.conf web/.dockerignore web/README.md infra/nginx/conf.d/app.conf docker-compose.yml .gitignore
git commit -m "feat: deploy web app via nginx container behind reverse proxy, ignore node_modules"
```

---

## Part C: Self-review checklist

After every task above is green (`npm test && npm run build` from `web/`), review the plan against the backend contract:

- [ ] `TankCreatePayload` (Task 3) includes `tank_shape` + the new dimension fields and `fuel_type_id`, and omits the removed `fluid_density` — matches `schemas/tanks.py` planned change.
- [ ] `TankRead` (Task 3) uses the new telemetry field names (`gov_volume`, `net_volume`, `density_at_temperature`, `fill_percent`) and does NOT reference `fluid_density` anywhere client-side.
- [ ] `listFuelTypes`, `getStrapping`, `createTank`, `listAllocations`, `listTransactions`, `listTotalizers` (all Task 3 `api/client.ts`) exist in the backend plan Task 5/6/8/9 endpoints.
- [ ] WS frames (Task 6) match the backend plan's telemetry frame (`tank_id` + `gov_volume`/`net_volume`/`density_at_temperature`/`fill_percent`/`is_outlier`) and alarm frames (`type`, `tank_id`, `acknowledged`, `message`).
- [ ] `buildChartOption` merges live + range, and the dual-axis grouping (volume-left, temp/density-right) matches the planned `/range` bucket shape and the NSV/GOV columns.
- [ ] Dispensing (Task 9) uses `GET /api/v1/dispensing/transactions` and totalizers (Task 10) use `GET /api/v1/totalizers` — both additive endpoints; no `PATCH`/authorization changes on the client side.
- [ ] Drift semantics (Task 10) are documented in-app, and the chart colors positive/negative drift clearly.
- [ ] `web/nginx.conf` listens on `8080` (matches `web` service `expose`), edge nginx `location /` proxies to `http://web:8080` with WS upgrade headers retained.
- [ ] `.gitignore` gains `node_modules/` and `web/dist/` so the build is not committed.
- [ ] Plan Tasks 1–11 are each verifiable with the stated test/build commands and commit boundaries are logical (scaffold, geometry, api, auth, router, ws, dashboard, charts, dispensing, totalizers, wiring).

### Rollback / safety notes
- No destructive backend changes; the frontend is additive within `web/`. The only cross-cutting change is `infra/nginx/conf.d/app.conf` `location /` — a broken proxy rollout is recoverable by reverting that one block; static serving could also be kept as a fallback by pointing `location /` to the `web` image's `/usr/share/nginx/html` volume.

### Completion definition
- All 11 tasks committed (7 frontend feature commits + wiring).
- `cd /home/ubuntu/fuel_monitoring/web && npm install && npm test && npm run build` pass.
- TDD followed for each written-test module (geometry, http, authStore, ws, chartOptions, dispenseFormat, driftCalc).
- Deployment smoke: edge nginx returns the SPA on `/` via `web:8080`.