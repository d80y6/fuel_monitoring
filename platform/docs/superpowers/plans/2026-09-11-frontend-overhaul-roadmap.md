# Frontend Overhaul Roadmap — SUB-3 / SUB-4 / SUB-5

## Purpose

The FuelOps SCADA web app is functionally complete (SUB-1 MQTT ingestion, SUB-2 IoT
gateway command API) but visually stuck in a light-only, slate-and-white shell with
text-only navigation, bare `Loading…` states, and no theme system. This roadmap
defines the three sub-projects that deliver the full visual + live-data overhaul,
their build order, and their dependencies.

Each sub-project follows the established flow: brainstorm → design spec → implementation
plan → subagent-driven implementation with per-task spec + code-quality review → full
regression → integration into `main`.

## The three sub-projects

| Sub-project | Title | Summary | Depends on |
|---|---|---|---|
| **SUB-3** | Visual shell overhaul | Design tokens + light/dark theme (system-follow + override), sidebar icons, page headers + connection pill, dashboard redesign, state polish primitives (skeleton/empty/error), theme-aware ECharts. | — |
| **SUB-4** | 3D tank gauge | react-three-fiber gauge on TankDetail (5 solid shapes + custom_strapping placeholder, orbit + hover tooltip + threshold bands, animated liquid surface), SVG `TankCanvas` stays as 2D dashboard tile + WebGL fallback. | SUB-3 (fuel palette + theme tokens reused by the gauge) |
| **SUB-5** | Gateway live push | Backend WS channel publishing `GatewayCommand` status changes; IoT gateway console subscribes instead of 5s polling. | SUB-3 visual language for the console |

## Build-order rationale

1. **SUB-3 first** — theme tokens are the foundation both the gauge and the console
   inherit. Locking in `dark:` semantics and the token vocabulary up front prevents
   rework in the dependents.
2. **SUB-4 second** — the highest-visibility change, self-contained in the frontend
   (adds `three` / `@react-three/fiber` / `@react-three/drei`), and consumes the
   SUB-3 fuel palette + theme.
3. **SUB-5 third** — orthogonal backend plumbing (extends the existing WS realtime
   infra parallel to `telemetry:live` / `alarms:live`); scheduled last so the console
   already sports the new visual language when live push lands.

## Explicit non-goals

No route restructuring, no auth/role changes, no backend changes in SUB-3/SUB-4,
no new runtime dependencies before SUB-4 except inline SVG icons. The legacy
Flask monolith was already removed by SUB-1 and must not be reintroduced.