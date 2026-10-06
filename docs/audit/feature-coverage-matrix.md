# Feature Coverage Matrix — main@77d4234 (Phase 1/2 combined)

Status: ✅ working+verified · 🟡 partial · 🔻 UI-only/BE-only · 🧪 simulated · ❌ missing/broken · N/A out of hardware scope.

## 5.1 Organization & multi-tenancy
| Capability | Status | Evidence |
|---|---|---|
| Companies (tenants) CRUD | 🟡 | API+UI exist (G-105 note: delete soft) — but no tenant binding to users |
| Tenant isolation (API/WS/exports/jobs) | ❌ P0 | every list/get cross-tenant; G-003 |
| Role model | 🟡 | 3 flat roles, no company/site scope; company_admin==global-minus-admin |
| Tenant-aware audit | ❌ | no audit log |
| Cross-tenant admin | 🟡 | admin only separation |

## 5.2 Site & asset management
| Region/governorate | ❌ | not modeled |
| Sites CRUD | ✅ | API+UI |
| Stations + Dispensers | 🟡 | dispenser: create/update only; no delete; terminal statuses hardcoded |
| Tanks CRUD | 🟡 | create/read only (no update/delete) G-105 |
| Tank compartments | ❌ | out of current hardware model |
| Fuel types & grades | 🟡 | create/list only |
| Nozzles | ❌ | dispenser-level only (hardware: 1 nozzle/dispenser — acceptable, documented) |
| Device (gateway) lifecycle + commands | ✅ | register/activate/command/ack |
| Device credentials provisioning | ❌ | no per-device MQTT identity (G-001) |
| History/audit trail per asset | ❌ | no audit |

## 5.3 Tank monitoring
| Live level/volume/pressure/temp | ✅ | full ingestion → WS pipeline verified live |
| GOV/NSV/density/temp-comp | ✅ | implemented; documented formulas |
| Data-quality: outlier flag (MAD) | ✅ | is_outlier persisted + chart flag |
| Stale-vs-live distinction | ❌ P1 | stale tanks render as online; no freshness metadata in DTO (G-103) |
| Threshold alarms (5 types) | 🟡 | rules exist; never resolve (G-004) |
| Water detection | N/A | hardware doesn't measure (documented constraint) |
| Sensor fault (status≠0) alarms | ❌ | status stored but never evaluates alarms |
| Historical trends/time buckets | ✅ | cagg-backed /range |
| CSV export | ✅ | streamed, keyset-paged |

## 5.4 Inventory & reconciliation
| Current inventory (measured) | ✅ | from measurements |
| Deliveries / transfers / adjustments / book inventory | ❌ | no models/endpoints — inventory movements not modeled (G-108) |
| Variance detection (Δvolume anomalies) | 🟡 | MAD flags outliers only; no reconciliation workflow |
| Daily/monthly summaries | 🟡 | consumption_summaries daily via beat |
| Immutable transaction history | 🟡 | dispense_transactions yes; inventory n/a |

## 5.5 Pumps & dispensers
| Registration/status | 🟡 | registration+is_active only; live state via station heartbeat |
| Totalizer audit vs authorized | ✅ | drift chart + audit_totalizer (caveat: cumulative compare semantics G-210) |
| Per-nozzle | ❌ documented single-nozzle mapping |
| Fault/maintenance states | ❌ | none |

## 5.6 Telemetry ingestion
| MQTT ingestion | ✅ | verified live |
| HTTPS fallback | 🟡 | works; unauthenticated + unvalidated body (G-002/G-114) |
| Device authn | ❌ P0 | none (G-001/G-113) |
| Payload schema validation | 🟡 | partial (coerce float; raw dict on HTTP) |
| Idempotency | ✅ | ON CONFLICT (tank_id, timestamp) |
| Out-of-order handling | ✅ | timestamps honored; cagg refresh policies |
| Replay protection | 🟡 | consumed-set for codes; readings natural |
| Dead-letter/observability of drops | ❌ | silent logs only |
| Offline buffering (edge) | ✅ | firmware frame_buffer + /backfill |

## 5.7 Alarms
| Trigger→persist→live push | ✅ | |
| Ack | 🟡 | spoofable acker (G-106) |
| Auto-resolve | ❌ | (G-004) |
| Escalation/assignment/suppression | ❌ | |
| Comm-loss alarm | ❌ | (G-103) |
| Alarm history + audit | 🟡 | rows persist; no audit metadata |
| Alarm dedupe/hysteresis | 🟡 | dedupe via open-set; never clears so no storm, but no hysteresis band |

## 5.8 Notifications
| SMS (SMPP) real sender | ✅ | raw SMPP 3.4 impl. w/ retries |
| WhatsApp Cloud API | ✅ | real HTTP call |
| Retry/failover/logging | ✅ | NOTIFY retries + NotificationLog |
| Templates/localization | ❌ | hardcoded English |
| Alarm-triggered notify | ❌ | never |
| Email/webhook channels | ❌ | |
| Delivery status (provider ACK) | 🟡 | submitted only; no dr callback |
| Auditability | 🟡 | logs exist, no UI |

## 5.9 Dashboards
| Ops overview (tiles) | ✅ real WS |
| KPI cards | 🟡 client-side derivations (G-204) |
| Site/tank drill | ✅ |
| Alarm center | 🟡 (N+1, styling bug) |
| Consumption/dispensing dashboards | ✅ |
| Communication status board | ❌ |
| Reports dashboards | ❌ |

## 5.10 Reports
| Tank CSV export | ✅ |
| Any other business report | ❌ (G-108) |

## Cross-cutting
| User management | ❌ |
| Audit log | ❌ |
| i18n/RTL | ❌ |
| a11y | 🟡 partial (labels, aria-modal, s-r col headers); no RTL, no focus mgmt |
| Migrations | ❌ create_all only (G-109) |
| Health/readiness | 🟡 /health only; no deep checks (G-201) |
| CI | ✅ pytest+pip-audit, tsc+vitest+npm audit |
| Perf evidence | ❌ none measured |

## Verdict distribution
- Blocks to commercial: G-001,G-002,G-003,G-004,G-005 (P0 set) + G-101..G-119 tier.
- Implementation order: P0 security+tenancy → alarm/data-plane → admin/audit → reports/inventory → i18n/UX polish → perf/ops hardening.
