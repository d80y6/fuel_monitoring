# SUB-3 — Frontend Shell Overhaul (Live Plan)

**Sub-project:** SUB-3 of the frontend overhaul program (roadmap: `plans/2026-09-11-frontend-overhaul-roadmap.md`).
**Spec:** `specs/2026-09-11-frontend-shell-overhaul-design.md` (approved).
**Date:** 2026-09-11
**Branch/work location:** main repo `/home/ubuntu/fuel_monitoring/web` (frontend lives only in the main repo — no worktree).

---

## Overview

The dashboard and pages currently hard-code light-only Tailwind classes (`bg-white`, `text-slate-*`, `border-slate-*`). SUB-3 introduces a **design-token system** (light + dark, class-driven), a **theme store** with a Light/System/Dark toggle, **inline SVG sidebar icons**, a **page-header shell** with a **live WS connection pill**, **state primitives** (Skeleton / EmptyState / ErrorCard), a **dashboard redesign** (alert strip), **theme-aware ECharts**, and a mechanical retrofit of every hot page to tokens.

Strategy decision (from spec §3, Approach 3): decompose into **SUB-3 (this)**, SUB-4 (3D gauge), SUB-5 (gateway live push). SUB-3 adds **no new dependencies** — icons are inline SVG, theming uses CSS variables. React-Three-Fiber is deliberately reserved for SUB-4.

### Token architecture (design refinement over spec §4)

The spec says tokens re-map per scheme. We implement this with **CSS variables flipped by a `.dark` class** on `<html>`, referenced from `tailwind.config.js`. Components therefore write **one** class (`bg-surface`, `text-primary`, `border-line`) that works in both themes — no `dark:` variants sprinkled per element. This makes the retrofit mechanical and keeps ECharts colors reachable from `getComputedStyle`-independent static maps for tests.

---

## Pre-implementation

### Dead ends
- ❌ Tailwind `dark:` variant pairs (`bg-white dark:bg-slate-900` per element) — verbose across ~25 files, error-prone. Rejected in favor of CSS-variable tokens.
- ❌ zustand `persist` middleware for theme — we need `mode: 'system'` semantics + a resolver; plain `create` with small `lib/theme.ts` helpers is simpler and testable.
- ❌ Driving ECharts colors from `getComputedStyle(document...)` — unavailable in jsdom; instead a static `chartColors` map keyed by scheme.

### Sources of truth (read, committed HEAD)
- `platform/docs/superpowers/specs/2026-09-11-frontend-shell-overhaul-design.md` — SUB-3 spec.
- `web/tailwind.config.js` — currently only `brand`+`brand-dark` colors; no `darkMode`.
- `web/src/index.css` — only tailwind directives + `height:100%`.
- `web/src/main.tsx` — `Root` mounts `useTelemetrySocket()`; QueryClient created here **and** in `App.tsx` (pre-existing duplication, out of scope).
- `web/src/router.tsx` — `AppLayout` wraps all authed routes.
- `web/src/AppLayout.tsx` — `<div class="min-h-screen flex bg-slate-100">`.
- `web/src/components/layout/Sidebar.tsx` — dark chrome (`bg-slate-900`) kept as-is in both themes; gains icons.
- `web/src/api/ws.ts` — `TelemetrySocket` emits `'status'` events `{ state: 'open' | 'closed' }` (currently unconsumed).
- `web/src/hooks/useTelemetrySocket.ts` — creates two sockets (`telemetry`, `alarms`); subscribes only `reading`/`alarm`.
- `web/src/lib/chartOptions.ts` — `buildChartOption(range, live, tankTitle, lowVolume, highVolume)`: hard-coded `rgba(248,113,113,0.12)` markArea etc.
- `web/src/components/charts/TelemetryChart.tsx`, `TotalizerDriftChart.tsx` — no theme prop.
- `web/package.json` — `echarts@5.5.1` + `echarts-for-react@3.0.2` present (theme prop + `EChartsOption` type available). zustand v4.5.5.
- `web/src/test/setup.ts` — jest-dom only; no `matchMedia` stub (must be added).
- Existing tests to update/extend: `sidebar`, `app`, `pages/Dispensing`, `pages/IoTGatewaysPage`, plus shared `ui/badge` etc. (tokens only, no assertions on classes).

### Unknowns / risks
- `window.matchMedia` is undefined in jsdom — every component that touches theme during render needs the stub; add a default stub to `src/test/setup.ts` and override in specific tests.
- `echarts-for-react` valid for `ntheme` prop: passing a known registered theme name works; unknown theme warns to console but does not crash. Register via a module-scope side effect in `chartTheme.ts`.
- Tailwind JIT won't include a class unless it appears literally in source — token class names like `bg-surface` are written literally, so fine. Do **not** build class strings dynamically.
- jsdom does not evaluate CSS, so token tests assert the CSS variable **contract** by reading `index.css` text, not computed styles.

---

## Implementation Plan

Per-task flow (TDD): write/extend failing test → run (confirm red) → implement → run (confirm green) → commit.
Commands (run from `web/`): `npx tsc --noEmit` and `npx vitest run <target>`.

---

### Task 1 — Design tokens: CSS variables + Tailwind config (+ contract test)

**Files:** `web/src/index.css`, `web/tailwind.config.js`, new `web/src/tests/tokenContract.test.ts`.

**Step 1.1 — Test (red).** Create `web/src/tests/tokenContract.test.ts`:

```ts
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const css = readFileSync(resolve(__dirname, '../index.css'), 'utf8');

const REQUIRED: Record<string, string> = {
  '--color-canvas': '',
  '--color-surface': '',
  '--color-surface-raised': '',
  '--color-inset': '',
  '--color-text-primary': '',
  '--color-text-secondary': '',
  '--color-text-muted': '',
  '--color-line': '',
  '--color-line-strong': '',
  '--color-brand': '',
  '--color-brand-dark': '',
  '--color-ok-bg': '', '--color-ok-text': '',
  '--color-warn-bg': '', '--color-warn-text': '',
  '--color-danger-bg': '', '--color-danger-text': '',
  '--color-info-bg': '', '--color-info-text': '',
};

describe('theme token contract', () => {
  it('defines every token in both :root and .dark blocks', () => {
    const root = css.split('.dark')[0] ?? '';
    const dark = css.split('.dark')[1] ?? '';
    for (const name of Object.keys(REQUIRED)) {
      expect(root, `${name} missing in :root`).toContain(`${name}:`);
      expect(dark, `${name} missing in .dark`).toContain(`${name}:`);
    }
  });

  it('sets darkMode and maps tokens in tailwind config', () => {
    const config = readFileSync(resolve(__dirname, '../../tailwind.config.js'), 'utf8');
    expect(config).toMatch(/darkMode:\s*'class'/);
    for (const name of Object.keys(REQUIRED)) {
      expect(config).toContain(`'${name}': 'var(${name})'`);
    }
  });
});
```

Run: `npx vitest run src/tests/tokenContract.test.ts` → **fails** (file missing / vars absent).

**Step 1.2 — Implement.** `web/src/index.css`:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

html,
body,
#root {
  height: 100%;
}

:root {
  --color-canvas: #f1f5f9;
  --color-surface: #ffffff;
  --color-surface-raised: #ffffff;
  --color-inset: #f8fafc;
  --color-text-primary: #1e293b;
  --color-text-secondary: #475569;
  --color-text-muted: #94a3b8;
  --color-line: #e2e8f0;
  --color-line-strong: #cbd5e1;
  --color-brand: #0ea5e9;
  --color-brand-dark: #0369a1;
  --color-ok-bg: #d1fae5;   --color-ok-text: #047857;
  --color-warn-bg: #fef3c7; --color-warn-text: #b45309;
  --color-danger-bg: #ffe4e6; --color-danger-text: #be123c;
  --color-info-bg: #e0f2fe; --color-info-text: #0369a1;
}

.dark {
  --color-canvas: #020617;
  --color-surface: #0f172a;
  --color-surface-raised: #1e293b;
  --color-inset: #020617;
  --color-text-primary: #f1f5f9;
  --color-text-secondary: #cbd5e1;
  --color-text-muted: #64748b;
  --color-line: #1e293b;
  --color-line-strong: #334155;
  --color-brand: #38bdf8;
  --color-brand-dark: #0ea5e9;
  --color-ok-bg: #064e3b;   --color-ok-text: #6ee7b7;
  --color-warn-bg: #451a03; --color-warn-text: #fcd34d;
  --color-danger-bg: #4c0519; --color-danger-text: #fda4af;
  --color-info-bg: #0c4a6e; --color-info-text: #7dd3fc;
}
```

`web/tailwind.config.js` — replace the `colors` block (keep `brand`* keys for backward compat, now var-driven) and add `darkMode`:

```js
darkMode: 'class',
theme: {
  extend: {
    colors: {
      brand: 'var(--color-brand)',
      'brand-dark': 'var(--color-brand-dark)',
      canvas: 'var(--color-canvas)',
      surface: 'var(--color-surface)',
      'surface-raised': 'var(--color-surface-raised)',
      inset: 'var(--color-inset)',
      primary: 'var(--color-text-primary)',
      secondary: 'var(--color-text-secondary)',
      muted: 'var(--color-text-muted)',
      line: 'var(--color-line)',
      'line-strong': 'var(--color-line-strong)',
      ok: 'var(--color-ok-bg)',
      'ok-fg': 'var(--color-ok-text)',
      warn: 'var(--color-warn-bg)',
      'warn-fg': 'var(--color-warn-text)',
      danger: 'var(--color-danger-bg)',
      'danger-fg': 'var(--color-danger-text)',
      info: 'var(--color-info-bg)',
      'info-fg': 'var(--color-info-text)',
    },
  },
},
```

(Read the file first; preserve the rest of the config verbatim.)

**Step 1.3 — Verify (green).** `npx vitest run src/tests/tokenContract.test.ts` and `npx tsc --noEmit`.

**Step 1.4 — Commit:** `feat(web): design-token theme variables + tailwind mapping`

---

### Task 2 — Theme mode helpers, store, provider, hook

**Files:** new `web/src/lib/theme.ts`, `web/src/store/theme.ts`, `web/src/components/theme/ThemeProvider.tsx`, `web/src/hooks/useTheme.ts`; edit `web/src/test/setup.ts`; tests `web/src/tests/theme.test.ts`, `web/src/store/theme.test.ts`, `web/src/components/theme/ThemeProvider.test.tsx`.

**Step 2.1 — Test (red).**

`web/src/test/setup.ts` (edit — add default stub so future renders never crash):

```ts
import '@testing-library/jest-dom/vitest';

if (!('matchMedia' in window)) {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }),
  });
}
```

`web/src/tests/theme.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { resolveScheme, readStoredMode, writeStoredMode, THEME_STORAGE_KEY } from '../lib/theme';

const memory = (init: Record<string, string> = {}) => {
  const m = new Map(Object.entries(init));
  return { getItem: (k: string) => (m.has(k) ? m.get(k) ?? null : null), setItem: (k: string, v: string) => { m.set(k, v); } };
};

describe('resolveScheme', () => {
  it('returns the explicit mode regardless of system preference', () => {
    expect(resolveScheme('light', true)).toBe('light');
    expect(resolveScheme('dark', false)).toBe('dark');
  });
  it('follows system when mode is system', () => {
    expect(resolveScheme('system', true)).toBe('dark');
    expect(resolveScheme('system', false)).toBe('light');
  });
});

describe('stored theme mode', () => {
  it('defaults to system when nothing stored', () => {
    expect(readStoredMode(memory())).toBe('system');
  });
  it('reads a stored mode', () => {
    expect(readStoredMode(memory({ [THEME_STORAGE_KEY]: 'dark' }))).toBe('dark');
  });
  it('falls back to system for garbage values', () => {
    expect(readStoredMode(memory({ [THEME_STORAGE_KEY]: 'neon' }))).toBe('system');
  });
  it('writes a mode', () => {
    const s = memory();
    writeStoredMode('light', s);
    expect(readStoredMode(s)).toBe('light');
  });
  it('does not throw when storage is unavailable', () => {
    const broken = { setItem: () => { throw new Error('denied'); }, getItem: () => { throw new Error('denied'); } };
    expect(() => writeStoredMode('dark', broken)).not.toThrow();
    expect(readStoredMode(broken)).toBe('system');
  });
});
```

`web/src/store/theme.test.ts`:

```ts
import { describe, expect, it, beforeEach } from 'vitest';
import { useThemeStore, themeStoreReset } from './theme';

describe('useThemeStore', () => {
  beforeEach(() => themeStoreReset());
  it('starts with system mode', () => {
    expect(useThemeStore.getState().mode).toBe('system');
  });
  it('setMode updates the mode', () => {
    useThemeStore.getState().setMode('dark');
    expect(useThemeStore.getState().mode).toBe('dark');
  });
  it('applyResolvedScheme updates the resolved scheme', () => {
    useThemeStore.getState().applyResolvedScheme('dark');
    expect(useThemeStore.getState().resolvedScheme).toBe('dark');
  });
});
```

`web/src/components/theme/ThemeProvider.test.tsx`:

```tsx
import { act, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ThemeProvider } from './ThemeProvider';
import { useThemeStore } from '../../store/theme';

type Listener = () => void;
function stubMatchMedia(matches: boolean) {
  const listeners = new Set<Listener>();
  const mql = {
    matches,
    media: '(prefers-color-scheme: dark)',
    onchange: null,
    addEventListener: (_t: string, cb: Listener) => { listeners.add(cb); },
    removeEventListener: (_t: string, cb: Listener) => { listeners.delete(cb); },
    addListener: () => {}, removeListener: () => {},
    dispatchEvent: () => false,
  };
  window.matchMedia = vi.fn().mockReturnValue(mql);
  return { listeners, mql };
}

describe('ThemeProvider', () => {
  beforeEach(() => {
    document.documentElement.classList.remove('dark');
    useThemeStore.setState({ mode: 'light', resolvedScheme: 'light' });
  });
  afterEach(() => { document.documentElement.classList.remove('dark'); });

  it('renders children', () => {
    render(<ThemeProvider><p>child</p></ThemeProvider>);
    expect(screen.getByText('child')).toBeInTheDocument();
  });

  it('applies .dark when resolved scheme is dark', () => {
    const { listeners } = stubMatchMedia(true);
    useThemeStore.setState({ mode: 'system', resolvedScheme: 'light' });
    render(<ThemeProvider><p>x</p></ThemeProvider>);
    expect(document.documentElement.classList.contains('dark')).toBe(true);
    expect(listeners.size).toBeGreaterThan(0);
  });

  it('flips the class when system preference changes in system mode', () => {
    const { listeners, mql } = stubMatchMedia(false);
    useThemeStore.setState({ mode: 'system', resolvedScheme: 'light' });
    render(<ThemeProvider><p>x</p></ThemeProvider>);
    expect(document.documentElement.classList.contains('dark')).toBe(false);
    expect(listeners.size).toBeGreaterThan(0);
    mql.matches = true;
    act(() => { for (const cb of Array.from(listeners)) cb(); });
    expect(document.documentElement.classList.contains('dark')).toBe(true);
    expect(useThemeStore.getState().resolvedScheme).toBe('dark');
  });

  it('does not attach a listener when mode is explicit', () => {
    const { listeners } = stubMatchMedia(true);
    useThemeStore.setState({ mode: 'dark', resolvedScheme: 'dark' });
    render(<ThemeProvider><p>x</p></ThemeProvider>);
    expect(listeners.size).toBe(0);
  });
});
```

> Note: the provider's effect resolves the current scheme **at effect time** from `window.matchMedia(...).matches`, so stub `matches` must be set before render. The "flips" test asserts the listener exists and runs without error; keep it deterministic by asserting `documentElement.classList` after a manual `listeners` call in a subsequent assertion.

Run (red): `npx vitest run src/tests/theme.test.ts src/store/theme.test.ts src/components/theme/ThemeProvider.test.tsx` → fails (modules missing).

**Step 2.2 — Implement.**

`web/src/lib/theme.ts`:

```ts
export type ThemeMode = 'light' | 'dark' | 'system';
export type Scheme = 'light' | 'dark';

export const THEME_STORAGE_KEY = 'fmp-theme';

export function resolveScheme(mode: ThemeMode, systemPrefersDark: boolean): Scheme {
  if (mode === 'system') return systemPrefersDark ? 'dark' : 'light';
  return mode;
}

export function readStoredMode(storage: Pick<Storage, 'getItem'> = localStorage): ThemeMode {
  try {
    const v = storage.getItem(THEME_STORAGE_KEY);
    return v === 'light' || v === 'dark' || v === 'system' ? v : 'system';
  } catch {
    return 'system';
  }
}

export function writeStoredMode(mode: ThemeMode, storage: Pick<Storage, 'setItem'> = localStorage): void {
  try {
    storage.setItem(THEME_STORAGE_KEY, mode);
  } catch {
    /* storage unavailable — ignore */
  }
}
```

`web/src/store/theme.ts`:

```ts
import { create } from 'zustand';
import type { Scheme, ThemeMode } from '../lib/theme';
import { readStoredMode, writeStoredMode } from '../lib/theme';

export interface ThemeState {
  mode: ThemeMode;
  resolvedScheme: Scheme;
  setMode: (mode: ThemeMode) => void;
  applyResolvedScheme: (scheme: Scheme) => void;
}

export const useThemeStore = create<ThemeState>()((set) => ({
  mode: readStoredMode(),
  resolvedScheme: 'light',
  setMode: (mode) => {
    writeStoredMode(mode);
    set({ mode });
  },
  applyResolvedScheme: (resolvedScheme) => set({ resolvedScheme }),
}));

/** Test helper: reset to a known state. */
export function themeStoreReset() {
  useThemeStore.setState({ mode: 'system', resolvedScheme: 'light' });
}
```

`web/src/store/theme.ts` export `themeStoreReset` — note it is used only by tests; annotate nothing else.

`web/src/components/theme/ThemeProvider.tsx`:

```tsx
import { ReactNode, useEffect } from 'react';
import { useThemeStore } from '../../store/theme';
import { resolveScheme } from '../../lib/theme';

export function ThemeProvider({ children }: { children: ReactNode }) {
  const mode = useThemeStore((s) => s.mode);
  const applyResolvedScheme = useThemeStore((s) => s.applyResolvedScheme);

  useEffect(() => {
    const media = window.matchMedia('(prefers-color-scheme: dark)');
    const sync = () => {
      const scheme = resolveScheme(mode, media.matches);
      applyResolvedScheme(scheme);
      document.documentElement.classList.toggle('dark', scheme === 'dark');
    };
    sync();
    if (mode === 'system') {
      media.addEventListener('change', sync);
      return () => media.removeEventListener('change', sync);
    }
  }, [mode, applyResolvedScheme]);

  return <>{children}</>;
}
```

`web/src/hooks/useTheme.ts`:

```ts
import { useThemeStore } from '../store/theme';

export function useTheme() {
  const mode = useThemeStore((s) => s.mode);
  const resolvedScheme = useThemeStore((s) => s.resolvedScheme);
  const setMode = useThemeStore((s) => s.setMode);
  return { mode, resolvedScheme, setMode };
}
```

**Step 2.3 — Verify (green).** Run the three test commands from Step 2.1 plus `npx tsc --noEmit`.

**Step 2.4 — Commit:** `feat(web): theme store, ThemeProvider, useTheme + matchMedia test stub`

---

### Task 3 — Theme toggle (Light / System / Dark)

**Files:** new `web/src/components/theme/ThemeToggle.tsx`, test `web/src/components/theme/ThemeToggle.test.tsx`.

**Step 3.1 — Test (red).**

```tsx
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';
import { ThemeToggle } from './ThemeToggle';
import { themeStoreReset, useThemeStore } from '../../store/theme';

describe('ThemeToggle', () => {
  beforeEach(() => themeStoreReset());

  it('renders the three options and marks the active one', () => {
    useThemeStore.setState({ mode: 'dark' });
    render(<ThemeToggle />);
    expect(screen.getByRole('button', { name: 'Dark' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'Light' })).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByRole('button', { name: 'System' })).toHaveAttribute('aria-pressed', 'false');
  });

  it('switches mode on click', async () => {
    useThemeStore.setState({ mode: 'system' });
    render(<ThemeToggle />);
    await userEvent.click(screen.getByRole('button', { name: 'Dark' }));
    expect(useThemeStore.getState().mode).toBe('dark');
    await userEvent.click(screen.getByRole('button', { name: 'System' }));
    expect(useThemeStore.getState().mode).toBe('system');
  });
});
```

Run (red): `npx vitest run src/components/theme/ThemeToggle.test.tsx` → fails (missing module).

**Step 3.2 — Implement.**

```tsx
import type { ThemeMode } from '../../lib/theme';
import { useTheme } from '../../hooks/useTheme';

const OPTIONS: { mode: ThemeMode; label: string }[] = [
  { mode: 'light', label: 'Light' },
  { mode: 'system', label: 'System' },
  { mode: 'dark', label: 'Dark' },
];

export function ThemeToggle() {
  const { mode, setMode } = useTheme();
  return (
    <div role="group" aria-label="Theme" className="flex items-center gap-1 rounded-full border border-line bg-inset p-0.5">
      {OPTIONS.map((o) => (
        <button
          key={o.mode}
          type="button"
          aria-pressed={mode === o.mode}
          onClick={() => setMode(o.mode)}
          className={`rounded-full px-2.5 py-1 text-xs font-medium transition-colors ${
            mode === o.mode
              ? 'bg-surface-raised text-primary ring-1 ring-line-strong'
              : 'text-secondary hover:text-primary'
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
```

**Step 3.3 — Verify (green).** `npx vitest run src/components/theme/ThemeToggle.test.tsx` + `npx tsc --noEmit`.

**Step 3.4 — Commit:** `feat(web): Light/System/Dark theme toggle`

---

### Task 4 — Chart colors, ECharts theme registration, scheme-aware chartOptions

**Files:** new `web/src/lib/chartColors.ts`, `web/src/lib/chartTheme.ts`; edit `web/src/lib/chartOptions.ts`; tests `web/src/tests/chartColors.test.ts`, `web/src/tests/chartOptions.test.ts`.

**Step 4.1 — Test (red).**

`web/src/tests/chartColors.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { chartColors } from '../lib/chartColors';
import { registerChartThemes } from '../lib/chartTheme';

describe('chartColors', () => {
  it('provides distinct light and dark schemes', () => {
    expect(chartColors.light.text).not.toBe(chartColors.dark.text);
    expect(chartColors.light.splitLine).not.toBe(chartColors.dark.splitLine);
    expect(chartColors.light.tooltipBg).not.toBe(chartColors.dark.tooltipBg);
  });
});

describe('registerChartThemes', () => {
  it('is idempotent', () => {
    expect(() => { registerChartThemes(); registerChartThemes(); }).not.toThrow();
  });
});
```

`web/src/tests/chartOptions.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { buildChartOption } from '../lib/chartOptions';
import type { TelemetryPoint } from '../lib/apiTypes';
import type { LiveReading } from '../store/telemetry';

const p = (timestamp: string, extra: Partial<TelemetryPoint> = {}): TelemetryPoint =>
  ({ timestamp, gov_volume: 400, net_volume: 380, temperature: 24, density_at_temperature: 840, ...extra }) as TelemetryPoint;

describe('buildChartOption', () => {
  it('colors the threshold mark area per scheme', () => {
    const light = buildChartOption([p('2026-09-11T00:00:00Z')], undefined, 'T1', 100, 500, 'light');
    const dark = buildChartOption([p('2026-09-11T00:00:00Z')], undefined, 'T1', 100, 500, 'dark');
    const lightArea = (light.series[0] as any).markArea.itemStyle.color;
    const darkArea = (dark.series[0] as any).markArea.itemStyle.color;
    expect(lightArea).not.toBe(darkArea);
  });

  it('sets tooltip background from the scheme', () => {
    const dark = buildChartOption([], undefined, 'T1', undefined, undefined, 'dark');
    expect((dark.tooltip as any).backgroundColor).toBe('rgba(15,23,42,0.95)');
  });

  it('defaults to light scheme when omitted', () => {
    const opt = buildChartOption([], undefined, 'T1');
    expect((opt.tooltip as any).backgroundColor).toBe('rgba(255,255,255,0.95)');
  });
});
```

> Types: `buildChartOption` will return `EChartsOption` from `echarts` (already a direct dep). Accessing nested fields via `as any` in tests is acceptable.

Run (red): `npx vitest run src/tests/chartColors.test.ts src/tests/chartOptions.test.ts` → fails.

**Step 4.2 — Implement.**

`web/src/lib/chartColors.ts`:

```ts
import type { Scheme } from './theme';

export interface ChartColors {
  text: string;
  muted: string;
  axisLine: string;
  splitLine: string;
  legend: string;
  tooltipBg: string;
  tooltipBorder: string;
  threshArea: string;
}

export const chartColors: Record<Scheme, ChartColors> = {
  light: {
    text: '#1e293b',
    muted: '#94a3b8',
    axisLine: '#cbd5e1',
    splitLine: '#e2e8f0',
    legend: '#334155',
    tooltipBg: 'rgba(255,255,255,0.95)',
    tooltipBorder: '#cbd5e1',
    threshArea: 'rgba(248,113,113,0.12)',
  },
  dark: {
    text: '#e2e8f0',
    muted: '#64748b',
    axisLine: '#334155',
    splitLine: '#1e293b',
    legend: '#cbd5e1',
    tooltipBg: 'rgba(15,23,42,0.95)',
    tooltipBorder: '#334155',
    threshArea: 'rgba(248,113,113,0.25)',
  },
};
```

`web/src/lib/chartTheme.ts`:

```ts
import * as echarts from 'echarts';
import { chartColors } from './chartColors';

export const CHART_THEME_LIGHT = 'fmp-light';
export const CHART_THEME_DARK = 'fmp-dark';

let registered = false;

export function registerChartThemes(): void {
  if (registered) return;
  const mk = (c: (typeof chartColors)['light']) => ({
    textStyle: { color: c.text },
    title: { textStyle: { color: c.text } },
    legend: { textStyle: { color: c.legend } },
    tooltip: { backgroundColor: c.tooltipBg, borderColor: c.tooltipBorder, textStyle: { color: c.text } },
    categoryAxis: { axisLine: { lineStyle: { color: c.axisLine } }, axisLabel: { color: c.muted }, splitLine: { lineStyle: { color: c.splitLine } } },
    valueAxis: { axisLabel: { color: c.muted }, splitLine: { lineStyle: { color: c.splitLine } } },
  });
  echarts.registerTheme(CHART_THEME_LIGHT, mk(chartColors.light));
  echarts.registerTheme(CHART_THEME_DARK, mk(chartColors.dark));
  registered = true;
}

export function chartThemeName(scheme: 'light' | 'dark'): string {
  return scheme === 'dark' ? CHART_THEME_DARK : CHART_THEME_LIGHT;
}

void registerChartThemes();
```

`web/src/lib/chartOptions.ts` — diff (edit, preserving all curves logic):

- Import: `import type { EChartsOption } from 'echarts';`, `import { chartColors } from './chartColors';`, `import type { Scheme } from './theme';`
- Replace the `export interface ChartOption { ... }` block with `export type ChartOption = EChartsOption;`
- Change signature: `buildChartOption(range, live, tankTitle, lowVolume?, highVolume?, scheme: Scheme = 'light')`.
- `const c = chartColors[scheme];`
- markArea color: `c.threshArea`.
- Return object: `title: { text: tankTitle, textStyle: { color: c.text } }, tooltip: { trigger: 'axis', backgroundColor: c.tooltipBg, borderColor: c.tooltipBorder, textStyle: { color: c.text } }, legend: { data: ['GOV','NSV','Temperature','Density'], textStyle: { color: c.legend } }, xAxis: { type:'category', data: xs, axisLine: { lineStyle: { color: c.axisLine } }, axisLabel: { color: c.muted } }, yAxis: [ { ..., axisLabel: { color: c.muted }, splitLine: { lineStyle: { color: c.splitLine } } }, { ...same } ]`.

Note: casting the returned object to `ChartOption` may need `as ChartOption` where EChartsOption wants literal unions (e.g. `type:'value'`). ECharts `EChartsOption` accepts string literal via `as` — use `return { ... } as ChartOption;`.

**Step 4.3 — Verify (green).** `npx vitest run src/tests/chartColors.test.ts src/tests/chartOptions.test.ts` + `npx tsc --noEmit`.

**Step 4.4 — Commit:** `feat(web): theme-aware ECharts colors + scheme-aware chartOptions`

---

### Task 5 — Inline SVG icons + sidebar retrofit

**Files:** new `web/src/components/ui/icons.tsx` (+ test), edit `web/src/components/layout/Sidebar.tsx`, extend `web/src/components/layout/Sidebar.test.tsx`.

**Step 5.1 — Test (red).** `web/src/components/ui/icons.test.tsx`:

```tsx
import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Icon } from './icons';

describe('Icon', () => {
  it('renders an svg with aria-hidden and currentColor stroke', () => {
    const { container } = render(<Icon name="tank" />);
    const svg = container.querySelector('svg');
    expect(svg).not.toBeNull();
    expect(svg).toHaveAttribute('aria-hidden', 'true');
    expect(svg?.getAttribute('viewBox')).toBe('0 0 24 24');
  });

  it('passes className through', () => {
    const { container } = render(<Icon name="tank" className="w-4 h-4" />);
    expect(container.querySelector('svg')).toHaveClass('w-4');
  });

  it('renders nothing for an unknown name', () => {
    const { container } = render(<Icon name={'nope' as never} />);
    expect(container.querySelector('svg')).toBeNull();
  });
});
```

Extend `Sidebar.test.tsx`: after the existing `shows Operations and Admin for admin role` case, add:

```tsx
import { render, screen } from '@testing-library/react'; // existing
// inside a test:
it('renders icons in the navigation', () => {
  useAuthStore.setState({ user: admin });
  const { container } = render(<MemoryRouter><Sidebar /></MemoryRouter>);
  expect(container.querySelectorAll('nav svg').length).toBeGreaterThan(0);
});
```

Run (red): `npx vitest run src/components/ui/icons.test.tsx src/components/layout/Sidebar.test.tsx` → fails (missing `icons`, no svg). Sidebar test may partially fail on the new assertion only.

**Step 5.2 — Implement.** `web/src/components/ui/icons.tsx`:

```tsx
import { ReactNode } from 'react';

export type IconName =
  | 'dashboard'
  | 'tank'
  | 'dispensing'
  | 'totalizers'
  | 'alarm'
  | 'building'
  | 'fuel'
  | 'gateway';

const PATHS: Record<IconName, ReactNode> = {
  dashboard: (<><rect x="3" y="3" width="7" height="9" rx="1" /><rect x="14" y="3" width="7" height="5" rx="1" /><rect x="14" y="12" width="7" height="9" rx="1" /><rect x="3" y="16" width="7" height="5" rx="1" /></>),
  tank: (<><path d="M4 6.5A2.5 2.5 0 0 1 6.5 4h7A2.5 2.5 0 0 1 16 6.5V20H4Z" /><path d="M9 4v16" /></>),
  dispensing: (<><path d="M9 3h6v18H9z" /><path d="M15 9l3-1.5V7" /><path d="M6 4v4" /></>),
  totalizers: (<><path d="M4 7h16" /><path d="M4 7c1.5 1.5 2.5 3.5 2.5 6S5.5 15.5 4 17" /></>),
  alarm: (<><path d="M12 3l7 4v5c0 4-3 7-7 7s-7-3-7-7V7Z" /><path d="M12 8v4" /><path d="M12 15.5h.01" /></>),
  building: (<><rect x="4" y="3" width="16" height="18" rx="1" /><path d="M8 21v-5a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v5" /><path d="M9 8h.01M12 8h.01M15 8h.01" /></>),
  fuel: (<><path d="M5 21V5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v16" /><path d="M4 21h14" /><path d="M15 7h2a2 2 0 0 1 2 2v2" /><rect x="8" y="8" width="3" height="4" rx="1" /><path d="M17 14h1a1.5 1.5 0 0 1 1.5 1.5V19a1 1 0 0 1-2 0Z" /></>),
  gateway: (<><rect x="3" y="5" width="18" height="6" rx="1" /><rect x="3" y="15" width="18" height="6" rx="1" /><path d="M7 8h.01M7 18h.01" /></>),
};

export function Icon({ name, className }: { name: IconName; className?: string }) {
  if (!(name in PATHS)) return null;
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
    >
      {PATHS[name]}
    </svg>
  );
}
```

`Sidebar.tsx` changes:
- `import { Icon, type IconName } from '../../components/ui/icons';` (path: from `components/layout` to `components/ui` → `../../components/ui/icons`? Actually Sidebar is at `src/components/layout/Sidebar.tsx`; ui is `src/components/ui` → `../ui/icons`. Correct: `../ui/icons`.)
- Give `NavItem` an `icon: IconName`.
- Populate icons: Dashboard→`dashboard`; Tanks→`tank`; Dispensing→`dispensing`; Totalizers→`totalizers`; Alarm Center→`alarm`; Companies→`building`; Fuel Types→`fuel`; Gateways→`gateway`; IoT Gateways→`gateway`.
- Keep the dark chrome classes unchanged. Update `NavLink` to flex + icon:

```tsx
<NavLink
  key={l.to}
  to={l.to}
  className={({ isActive }) =>
    `flex items-center gap-2.5 rounded px-3 py-2 text-sm ${
      isActive ? 'bg-brand text-white' : 'hover:bg-slate-800'
    }`
  }
>
  <Icon name={l.icon} className="h-4 w-4 shrink-0" />
  <span className="flex-1 truncate">{l.label}</span>
  {l.to === '/dashboard' && openCount > 0 ? (
    <span className="inline-block h-2 w-2 rounded-full bg-rose-400" />
  ) : null}
</NavLink>
```

**Step 5.3 — Verify (green).** `npx vitest run src/components/ui/icons.test.tsx src/components/layout/Sidebar.test.tsx` + `npx tsc --noEmit`.

**Step 5.4 — Commit:** `feat(web): inline SVG icons + sidebar navigation retrofit`

---

### Task 6 — Header shell: PageHeader, ConnectionPill, socket status store, AppLayout

**Files:** new `web/src/store/socket.ts`, `web/src/components/ui/PageHeader.tsx`, `web/src/components/layout/ConnectionPill.tsx` (+ each test); edit `web/src/hooks/useTelemetrySocket.ts`, `web/src/components/layout/AppLayout.tsx`, `web/src/main.tsx`.

**Step 6.1 — Test (red).**

`web/src/store/socket.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { useSocketStatusStore } from './socket';

describe('useSocketStatusStore', () => {
  it('starts with both channels closed', () => {
    expect(useSocketStatusStore.getState().telemetry).toBe('closed');
    expect(useSocketStatusStore.getState().alarms).toBe('closed');
  });
  it('records channel state changes', () => {
    useSocketStatusStore.getState().setSocketState('telemetry', 'open');
    useSocketStatusStore.getState().setSocketState('alarms', 'open');
    expect(useSocketStatusStore.getState().telemetry).toBe('open');
    expect(useSocketStatusStore.getState().alarms).toBe('open');
  });
});
```

`web/src/components/layout/ConnectionPill.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { ConnectionPill } from './ConnectionPill';
import { useSocketStatusStore } from '../../store/socket';

describe('ConnectionPill', () => {
  beforeEach(() => useSocketStatusStore.setState({ telemetry: 'closed', alarms: 'closed' }));

  it('shows Live when both channels are open', () => {
    useSocketStatusStore.setState({ telemetry: 'open', alarms: 'open' });
    render(<ConnectionPill />);
    expect(screen.getByText('Live')).toBeInTheDocument();
  });

  it('shows Reconnecting when one channel is down', () => {
    useSocketStatusStore.setState({ telemetry: 'open', alarms: 'closed' });
    render(<ConnectionPill />);
    expect(screen.getByText('Reconnecting')).toBeInTheDocument();
  });

  it('shows Offline when both channels are closed', () => {
    render(<ConnectionPill />);
    expect(screen.getByText('Offline')).toBeInTheDocument();
  });
});
```

`web/src/components/ui/PageHeader.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { PageHeader } from './PageHeader';

describe('PageHeader', () => {
  it('renders title and subtitle', () => {
    render(<PageHeader title="Tanks" subtitle="Live inventory" />);
    expect(screen.getByRole('heading', { name: 'Tanks' })).toBeInTheDocument();
    expect(screen.getByText('Live inventory')).toBeInTheDocument();
  });

  it('renders actions', () => {
    render(<PageHeader title="Tanks" actions={<button>New tank</button>} />);
    expect(screen.getByRole('button', { name: 'New tank' })).toBeInTheDocument();
  });
});
```

Run (red): `npx vitest run src/store/socket.test.ts src/components/layout/ConnectionPill.test.tsx src/components/ui/PageHeader.test.tsx` → fails.

**Step 6.2 — Implement.**

`web/src/store/socket.ts`:

```ts
import { create } from 'zustand';

export type SocketChannel = 'telemetry' | 'alarms';
export type SocketConnectionState = 'open' | 'closed';

interface SocketStatusState {
  telemetry: SocketConnectionState;
  alarms: SocketConnectionState;
  setSocketState: (channel: SocketChannel, state: SocketConnectionState) => void;
}

export const useSocketStatusStore = create<SocketStatusState>()((set) => ({
  telemetry: 'closed',
  alarms: 'closed',
  setSocketState: (channel, state) => set((s) => ({ ...s, [channel]: state })),
}));
```

`web/src/components/layout/ConnectionPill.tsx`:

```tsx
import { useSocketStatusStore } from '../../store/socket';

export function ConnectionPill() {
  const telemetry = useSocketStatusStore((s) => s.telemetry);
  const alarms = useSocketStatusStore((s) => s.alarms);
  const connected = telemetry === 'open' && alarms === 'open';
  const disconnected = telemetry === 'closed' && alarms === 'closed';

  const label = connected ? 'Live' : disconnected ? 'Offline' : 'Reconnecting';
  const dot = connected ? 'bg-ok' : disconnected ? 'bg-danger' : 'bg-warn';

  return (
    <div className="flex items-center gap-2 text-xs font-medium text-secondary">
      <span aria-hidden="true" className={`inline-block h-2 w-2 rounded-full ${dot}`} />
      <span>{label}</span>
    </div>
  );
}
```

`web/src/components/ui/PageHeader.tsx`:

```tsx
import { ReactNode } from 'react';

interface PageHeaderProps {
  title: string;
  subtitle?: ReactNode;
  actions?: ReactNode;
}

export function PageHeader({ title, subtitle, actions }: PageHeaderProps) {
  return (
    <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
      <div>
        <h2 className="text-2xl font-semibold text-primary">{title}</h2>
        {subtitle ? <p className="mt-0.5 text-sm text-secondary">{subtitle}</p> : null}
      </div>
      {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
    </div>
  );
}
```

`web/src/hooks/useTelemetrySocket.ts` — thread status into the store (edit lines 16–21 region):

```ts
    const offR = tel.on('reading', (m) =>
      useTelemetryStore.getState().setReading(m as LiveReading)
    );
    const offA = alm.on('alarm', (m) =>
      useTelemetryStore.getState().setAlarm(m as AlarmSummary)
    );
    const offTelS = tel.on('status', (m) =>
      useSocketStatusStore.getState().setSocketState('telemetry', (m as { state: 'open' | 'closed' }).state)
    );
    const offAlmS = alm.on('status', (m) =>
      useSocketStatusStore.getState().setSocketState('alarms', (m as { state: 'open' | 'closed' }).state)
    );
    tel.connect();
    alm.connect();
    return () => {
      offR();
      offA();
      offTelS();
      offAlmS();
      tel.disconnect();
      alm.disconnect();
    };
```

Add import: `import { useSocketStatusStore } from '../store/socket';`.

`web/src/components/layout/AppLayout.tsx`:

```tsx
import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { ConnectionPill } from './ConnectionPill';
import { ThemeToggle } from '../theme/ThemeToggle';

export function AppLayout() {
  return (
    <div className="flex min-h-screen bg-canvas text-primary">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-end gap-4 border-b border-line bg-surface-raised px-6 py-2.5">
          <ConnectionPill />
          <ThemeToggle />
        </header>
        <main className="flex-1 overflow-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
```

Sidebar is inside the layout; its root `aside` must remain full height within the flex row: keep `flex flex-col` (already present) — no change needed beyond existing classes.

`web/src/main.tsx` — add ThemeProvider + chart theme registration:

```tsx
import { ThemeProvider } from './components/theme/ThemeProvider';
import { registerChartThemes } from './lib/chartTheme';
// ...
void registerChartThemes();
// Root:
function Root() {
  useTelemetrySocket();
  return (
    <ThemeProvider>
      <RouterProvider router={router} />
    </ThemeProvider>
  );
}
```

`App.test.tsx` renders `<App />` which does not include `ThemeProvider` (it lives in `main.tsx` Root) — no change needed. The `matchMedia` stub added in Task 2 setup covers any incidental render.

**Step 6.3 — Verify (green).** `npx vitest run src/store/socket.test.ts src/components/layout/ConnectionPill.test.tsx src/components/ui/PageHeader.test.tsx` + `npx tsc --noEmit` + `npx vitest run src/App.test.tsx` (regression).

**Step 6.4 — Commit:** `feat(web): header shell with connection pill + theme toggle + PageHeader`

---

### Task 7 — State primitives (Skeleton / EmptyState / ErrorCard)

**Files:** new `web/src/components/ui/Skeleton.tsx`, `EmptyState.tsx`, `ErrorCard.tsx` (+ each test).

**Step 7.1 — Test (red).** `web/src/components/ui/primitives.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { Skeleton } from './Skeleton';
import { EmptyState } from './EmptyState';
import { ErrorCard } from './ErrorCard';

describe('Skeleton', () => {
  it('renders a pulse block with passthrough classes', () => {
    const { container } = render(<Skeleton className="h-8 w-full" />);
    const el = container.querySelector('div');
    expect(el).not.toBeNull();
    expect(el).toHaveClass('animate-pulse', 'bg-inset', 'h-8', 'w-full');
  });
});

describe('EmptyState', () => {
  it('renders title and hint', () => {
    render(<EmptyState title="No tanks" hint="Register a tank to begin." />);
    expect(screen.getByText('No tanks')).toBeInTheDocument();
    expect(screen.getByText('Register a tank to begin.')).toBeInTheDocument();
  });
});

describe('ErrorCard', () => {
  it('renders an alert with message', () => {
    render(<ErrorCard message="Boom" />);
    expect(screen.getByRole('alert')).toHaveTextContent('Boom');
  });
  it('invokes onRetry', async () => {
    const onRetry = vi.fn();
    render(<ErrorCard message="Boom" onRetry={onRetry} />);
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(onRetry).toHaveBeenCalledOnce();
  });
});
```

Run (red): `npx vitest run src/components/ui/primitives.test.tsx` → fails.

**Step 7.2 — Implement.**

`Skeleton.tsx`:

```tsx
export function Skeleton({ className = '' }: { className?: string }) {
  return <div aria-hidden="true" className={`animate-pulse rounded bg-inset ${className}`} />;
}
```

`EmptyState.tsx`:

```tsx
import { ReactNode } from 'react';

interface EmptyStateProps {
  icon?: ReactNode;
  title: string;
  hint?: string;
}

export function EmptyState({ icon, title, hint }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-line bg-surface px-6 py-10 text-center">
      {icon ? <div className="text-secondary">{icon}</div> : null}
      <p className="mt-2 text-sm font-medium text-primary">{title}</p>
      {hint ? <p className="mt-1 text-sm text-muted">{hint}</p> : null}
    </div>
  );
}
```

`ErrorCard.tsx`:

```tsx
interface ErrorCardProps {
  message?: string;
  onRetry?: () => void;
}

export function ErrorCard({ message = 'Failed to load data.', onRetry }: ErrorCardProps) {
  return (
    <div role="alert" className="flex items-center justify-between gap-3 rounded-lg border border-line bg-surface px-4 py-3">
      <p className="text-sm text-secondary">{message}</p>
      {onRetry ? (
        <button type="button" onClick={onRetry} className="text-sm font-medium text-brand-dark hover:underline">
          Retry
        </button>
      ) : null}
    </div>
  );
}
```

**Step 7.3 — Verify (green).** `npx vitest run src/components/ui/primitives.test.tsx` + `npx tsc --noEmit`.

**Step 7.4 — Commit:** `feat(web): Skeleton / EmptyState / ErrorCard primitives`

---

### Task 8 — Dashboard redesign (alert strip, KPI cards, tank tiles, empty state)

**Files:** new `web/src/components/dashboard/AlertSummaryStrip.tsx` (+ test); edit `web/src/pages/Dashboard.tsx`, `web/src/components/dashboard/KpiCards.tsx`, `web/src/components/tanks/TankTile.tsx`.

**Step 8.1 — Test (red).** `web/src/components/dashboard/AlertSummaryStrip.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { AlertSummaryStrip } from './AlertSummaryStrip';
import type { AlarmSummary } from '../../lib/apiTypes';

vi.mock('../../hooks/useRealtimeAlarms', () => ({
  useRealtimeAlarms: () => MOCK_ALARMS as AlarmSummary[],
}));

const MOCK_ALARMS: AlarmSummary[] = [
  { id: 'a1', tank_id: 't1', timestamp: '2026-09-11T00:00:00Z', level: 'critical', type: 'low_volume', message: 'Tank low', value: 12, acknowledged: false },
  { id: 'a2', tank_id: 't2', timestamp: '2026-09-11T00:00:00Z', level: 'warning', type: 'high_volume', message: 'Tank high', value: 88, acknowledged: false },
];

describe('AlertSummaryStrip', () => {
  it('hides when there are no open alarms', () => {
    vi.mocked(useRealtimeAlarms).mockReturnValue([]);
    render(<MemoryRouter><AlertSummaryStrip /></MemoryRouter>);
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });

  it('shows open alarm count and entries', () => {
    render(<MemoryRouter><AlertSummaryStrip /></MemoryRouter>);
    expect(screen.getByText(/2 open alarms/i)).toBeInTheDocument();
    expect(screen.getByText('Tank low')).toBeInTheDocument();
    expect(screen.getByText('Tank high')).toBeInTheDocument();
  });
});
```

Run (red): `npx vitest run src/components/dashboard/AlertSummaryStrip.test.tsx` → fails.

**Step 8.2 — Implement.** `web/src/components/dashboard/AlertSummaryStrip.tsx`:

```tsx
import { Link } from 'react-router-dom';
import { useRealtimeAlarms } from '../../hooks/useRealtimeAlarms';

const LEVEL_DOT: Record<string, string> = {
  critical: 'bg-danger',
  warning: 'bg-warn',
  info: 'bg-info',
};

export function AlertSummaryStrip() {
  const alarms = useRealtimeAlarms();
  const open = alarms.filter((a) => !a.acknowledged);
  if (open.length === 0) return null;

  return (
    <div className="mb-6 rounded-lg border border-warn bg-warn px-4 py-3">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium text-warn-fg">
          {open.length} open alarm{open.length > 1 ? 's' : ''}
        </p>
        <Link to="/alarms" className="text-sm font-medium text-warn-fg underline-offset-2 hover:underline">
          View all
        </Link>
      </div>
      <ul className="mt-2 space-y-1">
        {open.slice(0, 3).map((a) => (
          <li key={a.id} className="flex items-center gap-2 text-sm">
            <span aria-hidden="true" className={`inline-block h-2 w-2 rounded-full ${LEVEL_DOT[a.level] ?? 'bg-info'}`} />
            <span className="font-medium">{a.type}</span>
            <span className="text-primary/80">{a.message}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
```

`Dashboard.tsx` — replace header block (lines 16–25) with `PageHeader` + strip, tokenize, add empty state:

```tsx
import { PageHeader } from '../components/ui/PageHeader';
import { EmptyState } from '../components/ui/EmptyState';
import { AlertSummaryStrip } from '../components/dashboard/AlertSummaryStrip';
// ...
  return (
    <div>
      <PageHeader title="Dashboard" subtitle="Live tank overview" />
      <AlertSummaryStrip />
      <KpiCards />
      {tanks.isLoading ? <Skeleton className="h-40 w-full" /> : null}
      {tanks.isError ? <ErrorCard message="Failed to load tanks." /> : null}
      {!tanks.isLoading && !tanks.isError && rows.length === 0 ? (
        <EmptyState title="No tanks" hint="Tanks will appear here once provisioned." />
      ) : null}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-4">
        {rows.map((t) => <TankRow key={t.id} tank={t} fuels={fuels.data ?? []} />)}
      </div>
    </div>
  );
```

Drop the inline `open.length` badge (superseded by `AlertSummaryStrip`); remove `useRealtimeAlarms`/`alarms`/`open` from Dashboard if no longer used (strip keeps them). Add imports for Skeleton/ErrorCard.

`KpiCards.tsx` — token retrofit (map table): `bg-white`→`bg-surface`, `border-slate-200`→`border-line`, labels `text-slate-500`→`text-muted`, values `text-slate-800`→`text-primary`, `text-rose-600`→`text-danger-fg`, `text-emerald-600`→`text-ok-fg`.

`TankTile.tsx` — token retrofit: link classes → `bg-surface rounded-lg border border-line p-3 ...`; name `text-slate-800`→`text-primary`; badge `bg-emerald-100 text-emerald-700`→`bg-ok text-ok`, `bg-slate-100 text-slate-500`→`bg-inset text-secondary`; footer `text-slate-700`→`text-secondary` (TankCanvas subtitle).

**Step 8.3 — Verify (green).** `npx vitest run src/components/dashboard/AlertSummaryStrip.test.tsx src/components/dashboard/KpiCards.test.tsx` + `npx tsc --noEmit`.

**Step 8.4 — Commit:** `feat(web): dashboard redesign (alert strip, tokens, state primitives)`

---

### Task 9 — Hot-page retrofit (tokens + PageHeader + state primitives)

Apply to: `Tanks.tsx`, `TankDetail.tsx`, `Dispensing.tsx`, `AlarmCenter.tsx`, `Totalizers.tsx`, `IoTGatewaysPage.tsx`, `IoTGatewayDetailPage.tsx`, and Dispensing sub-components (`DispenseLiveView.tsx`, `AllocationsCard.tsx`, `CodeOpsCard.tsx`, `UploadCard.tsx`).

**Step 9.1 — Test (red).** First, update each page to add the assertion scaffolding we expect to pass after retrofit. For each page with an existing test, add/extend cases:

- `IoTGatewaysPage.test.tsx` / `Dispensing.test.tsx` etc.: assert a heading via `<PageHeader>` (`getByRole('heading', { level: 2 })` still matches existing `h2`s). Assert loading renders a `Skeleton` (`document.querySelector('.animate-pulse')`) and error renders `role="alert"`. Implement at least:
  - states: loading → skeleton; error → ErrorCard (`Boom`); empty → EmptyState (`No ...`).

Add a dedicated retrofit test `web/src/pages/retrofit.test.tsx` ?? No — assert per-page inside existing test files for the touched pages. For pages without tests (Tanks, TankDetail, Totalizers, IoTGatewayDetail) create focused component tests that mount with mocked `@tanstack/react-query` + `MemoryRouter`, asserting:
- heading text present,
- loading branch renders `.animate-pulse`,
- empty branch renders EmptyState text.

Example (add to `web/src/pages/Totalizers.test.tsx`, new file):

```tsx
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it } from 'vitest';
import Totalizers from './Totalizers';

const makeClient = () =>
  new QueryClient({ defaultOptions: { queries: { retry: false } } });

describe('Totalizers', () => {
  it('renders a page header and empty state when no data', async () => {
    render(
      <QueryClientProvider client={makeClient()}>
        <Totalizers />
      </QueryClientProvider>
    );
    expect(screen.getByRole('heading', { level: 2, name: 'Totalizers' })).toBeInTheDocument();
  });
});
```

Run (red): the empty-state assertion fails because pages still render raw `<p>` text.

**Step 9.2 — Implement.** Token retrofit using the authoritative **mapping table** (Task 1 tokens):

| Old class | New token class |
|---|---|
| `bg-white` | `bg-surface` |
| `bg-slate-50` | `bg-inset` |
| `bg-slate-100` | `bg-inset` |
| `hover:bg-slate-50` | `hover:bg-inset` |
| `text-slate-800` | `text-primary` |
| `text-slate-700` | `text-secondary` |
| `text-slate-600` | `text-secondary` |
| `text-slate-500` | `text-secondary` |
| `text-slate-400` | `text-muted` |
| `border-slate-200` | `border-line` |
| `border-slate-300` | `border-line-strong` |
| `border-slate-100` | `border-line` |
| `divide-slate-200` | `divide-line` |
| `bg-slate-100 text-slate-400` | `bg-inset text-muted` |
| `bg-slate-100 text-slate-500` | `bg-inset text-secondary` |
| `bg-slate-100 text-slate-600` | `bg-inset text-secondary` |
| `bg-rose-100 text-rose-700` | `bg-danger text-danger-fg` |
| `bg-emerald-100 text-emerald-700` | `bg-ok text-ok-fg` |
| `bg-amber-100 text-amber-700` | `bg-warn text-warn-fg` |
| `bg-sky-100 text-sky-700` | `bg-info text-info-fg` |
| `text-rose-600` | `text-danger-fg` |
| `text-amber-700` (provisioning hint) | `text-warn-fg` |
| `text-emerald-600` (positive number) | `text-ok-fg` |
| **Keep as-is** | brand colors, `bg-slate-900/40` overlays, modal inputs (`text-slate-...` inside dialogs get the same treatment per table) |

**Keep dark chrome (both themes):** everything in `Sidebar`; `bg-slate-900 / text-slate-100 / border-slate-800 / text-slate-400 / hover:bg-slate-800 / hover:text-white`.

Page-specific additions:

- `Tanks.tsx`: replace header (`h2`+button, lines 39–44) with `<PageHeader title="Tanks" subtitle="Inventory" actions={<button ...>New tank</button>} />`. Add loading skeleton row + `EmptyState` when `tanks.data?.length === 0`. Dialog: tokenize (map table).
- `TankDetail.tsx`: replace `if (!tank) return <p ...>Loading tank…</p>` with a skeleton grid; replace page root `<h3>`s/cards with tokens; back-link → `text-secondary hover:text-primary`. Keep title inside right card (`tank.name · Telemetry`) — token text. Add `ErrorCard` when `tankQ.isError`.
- `Dispensing.tsx`: header → `PageHeader title="Dispensing" subtitle="Transactions, allocations and operations"`. Tabs `text-slate-600 hover:bg-slate-50`→`text-secondary hover:bg-inset`, keep `bg-brand text-white` active. Permission notice → `EmptyState title="Restricted" hint="You do not have permission to access this section."`.
- `AlarmCenter.tsx`: header → `PageHeader title="Alarm Center" actions={countBadge}` where badge = `bg-danger text-danger`; loading → Skeleton; empty → EmptyState; table tokens per map.
- `Totalizers.tsx`: header → `PageHeader title="Totalizers" subtitle="Meter vs authorization drift"`; empty drift → EmptyState; tokens.
- `IoTGatewaysPage.tsx`: header → `PageHeader title="IoT Gateways" actions={New gateway}`; loading → Skeleton; `isError` → `<ErrorCard message="Failed to load gateways." />`; empty rows → EmptyState; tokens.
- `IoTGatewayDetailPage.tsx`: loading/error branches → Skeleton / ErrorCard; cards tokenized; headers `text-slate-800`→`text-primary`, `text-slate-500` (dt) → `text-secondary`; provisioning hint `text-amber-700`→`text-warn`.
- Dispensing sub-components + `StrappingCard`/`badge`/`fields`/`Modal`: apply map table.

**Step 9.3 — Verify (green).** Run the page test suites:

```
npx vitest run src/pages/Sidebar.test.tsx src/pages/... 2>/dev/null
```

Precisely: `npx vitest run src/components/layout/Sidebar.test.tsx` (regression) and then `npx vitest run src/pages` (all page tests) plus newly created page tests + `npx tsc --noEmit`.

> Note there is no `src/pages` directory for tests — tests live as `src/pages/<X>.test.tsx` co-located. Command: `npx vitest run src/pages` runs the `pages/*.test.*` files.

**Step 9.4 — Commit:** `feat(web): retrofit hot pages to design tokens + PageHeader + state primitives`

---

### Task 10 — Theme-aware chart components

**Files:** edit `web/src/components/charts/TelemetryChart.tsx`, `web/src/components/charts/TotalizerDriftChart.tsx`; extend `web/src/tests/chartOptions.test.ts` (already covers `buildChartOption` scheme).

**Step 10.1 — Test (red).** No new unit is feasible for `ReactECharts` in jsdom without canvas; verify compile + existing green. Add a light smoke in `web/src/tests/chartComponents.test.tsx`:

```tsx
import { describe, expect, it, vi } from 'vitest';
import { chartThemeName } from '../lib/chartTheme';

describe('chartThemeName', () => {
  it('maps schemes to registered theme names', () => {
    expect(chartThemeName('light')).toBe('fmp-light');
    expect(chartThemeName('dark')).toBe('fmp-dark');
  });
});
```

Run (red): fails (module missing) — actually `chartThemeName` exists from Task 4; adjust: this is a sanity test that must simply pass post-Task-10. Keep it as a guard against renaming. Run and expect **green** after Task 4; treat any red as a regression to fix. To keep the TDD discipline for this task, add the assertion that **TelemetryChart passes the theme** via a tiny render with echarts mocked is over-engineering; the scheme pipeline is already unit-covered. We accept the transformer coverage from Task 4.

`web/src/components/charts/TelemetryChart.tsx`:

```tsx
import { useMemo } from 'react';
import ReactECharts from 'echarts-for-react';
import type { TelemetryPoint } from '../../lib/apiTypes';
import type { LiveReading } from '../../store/telemetry';
import { buildChartOption } from '../../lib/chartOptions';
import { chartThemeName } from '../../lib/chartTheme';
import { useTheme } from '../../hooks/useTheme';

// interface unchanged

export function TelemetryChart({ points, live, tankTitle, lowVolume, highVolume }: TelemetryChartProps) {
  const { resolvedScheme } = useTheme();
  const option = useMemo(
    () => buildChartOption(points, live, tankTitle, lowVolume, highVolume, resolvedScheme),
    [points, live, tankTitle, lowVolume, highVolume, resolvedScheme]
  );
  return (
    <ReactECharts
      option={option}
      theme={chartThemeName(resolvedScheme)}
      notMerge
      style={{ height: 360, width: '100%' }}
      opts={{ renderer: 'canvas' }}
    />
  );
}
```

`web/src/components/charts/TotalizerDriftChart.tsx` — full rewrite:

```tsx
import ReactECharts from 'echarts-for-react';
import type { DriftSample } from '../../lib/driftCalc';
import { roundAxisExtent } from '../../lib/chartOptions';
import { chartColors } from '../../lib/chartColors';
import { chartThemeName } from '../../lib/chartTheme';
import { useTheme } from '../../hooks/useTheme';

export function TotalizerDriftChart({ series }: { series: DriftSample[] }) {
  const { resolvedScheme } = useTheme();
  const c = chartColors[resolvedScheme];
  const labels = series.map((s) => new Date(s.ts).toLocaleString());
  const maxAbs = Math.max(1, ...series.map((s) => Math.abs(s.drift)));
  const axisMax = roundAxisExtent(maxAbs);

  const option = {
    title: {
      text: 'Drift = totalizer cumulative − authorized cumulative',
      textStyle: { color: c.text },
    },
    tooltip: { trigger: 'axis', backgroundColor: c.tooltipBg, borderColor: c.tooltipBorder, textStyle: { color: c.text } },
    grid: { left: 64, right: 32, top: 48, bottom: 48 },
    xAxis: {
      type: 'category' as const,
      data: labels,
      axisLine: { lineStyle: { color: c.axisLine } },
      axisLabel: { color: c.muted },
    },
    yAxis: {
      type: 'value' as const,
      name: 'Drift (L)',
      min: -axisMax,
      max: axisMax,
      axisLabel: { color: c.muted },
      splitLine: { lineStyle: { color: c.splitLine } },
    },
    series: [
      {
        name: 'Drift',
        type: 'bar' as const,
        data: series.map((s) => Number(s.drift.toFixed(3))),
        itemStyle: {
          color: (p: { value: number }) => (p.value >= 0 ? c.legend : c.axisLine),
        },
      },
    ],
  };

  return (
    <ReactECharts
      option={option}
      theme={chartThemeName(resolvedScheme)}
      notMerge
      style={{ height: 300, width: '100%' }}
    />
  );
}
```

**Step 10.2 — Verify.** `npx vitest run src/tests/chartComponents.test.tsx src/pages src/components` + `npx tsc --noEmit`.

**Step 10.3 — Commit:** `feat(web): theme-aware TelemetryChart + TotalizerDriftChart`

---

### Task 11 — Full regression, README, final commit

**Step 11.1 — Regression.** From `web/`:

```
npx tsc --noEmit
npx vitest run
```

Expect: `tsc` clean; **full existing suite green** (28 files baseline + new tests). Any red → fix before committing (no new failures allowed; a genuinely blocked case → stop and raise).

**Step 11.2 — README.** Append a short "Theming" section to `web/README.md` (create if absent): Light/System/Dark toggle location (header), storage key `fmp-theme`, token class vocabulary (`bg-surface`, `text-primary`, `border-line`, status tokens), and note that `.dark` flips CSS variables on `<html>` (Tailwind `darkMode: 'class'`), plus chart themes (`fmp-light`/`fmp-dark`).

**Step 11.3 — Final commit:** `feat(web): SUB-3 frontend shell overhaul (tokens, themes, header, charts)`

---

## Definition of Done

- [ ] `npx tsc --noEmit` clean.
- [ ] `npx vitest run` green (all suites incl. new token/theme/icon/socket/primitives/dashboard/page tests).
- [ ] No `.dark:`-style per-element overrides; single-class tokens everywhere except intentional dark chrome (Sidebar, overlays).
- [ ] `fmp-theme` persistence verified in toggle test; system-follow verified in ThemeProvider test.
- [ ] ConnectionPill reflects both WS channels from real socket `'status'` events.
- [ ] README documents theming.
- [ ] Docs committed (spec + roadmap already on main; plan committed with this delivery).