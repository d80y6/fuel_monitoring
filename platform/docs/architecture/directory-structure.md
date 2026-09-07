# Refactored Project Directory Structure

```
fuel_monitoring/
├── .env.example
├── .gitignore
├── docker-compose.yml                  # Full multi-service stack (Step 4)
├── Makefile
├── README.md
│
├── .github/
│   └── workflows/
│       ├── ci.yml                      # Build + test + lint on PR
│       └── deploy.yml                  # Docker build + push + SSH deploy
│
├── edge/                               # ========== EDGE LAYER ==========
│   ├── esp32/                          # ESP32-S3 MicroPython gateway
│   │   ├── boot.py
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── mqtt_client.py              # mTLS, QoS1, offline buffering
│   │   ├── sensor/
│   │   │   ├── keller_reader.py        # RS-485 Keller protocol
│   │   │   └── calibration.py
│   │   ├── storage/
│   │   │   └── flash_buffer.py         # SQLite-less flash ring buffer
│   │   └── ota/
│   │       └── ota_updater.py
│   └── rpi/                            # Raspberry Pi station node
│       ├── main.py                     # entrypoint
│       ├── config.py
│       ├── dispenser/
│       │   ├── modbus_client.py        # RS-485 Modbus RTU to dispenser
│       │   ├── code_interface.py       # local code entry UI (LCD/keypad)
│       │   └── pump_control.py         # unlock/dispense control
│       ├── security/
│       │   ├── totalizer.py            # secret counter meter readback
│       │   └── tamper_detect.py        # hardware tamper detection
│       ├── networking/
│       │   ├── api_client.py           # HTTPS client to FastAPI
│       │   ├── mqtt_client.py          # mTLS MQTT
│       │   └── ws_client.py            # WebSocket fallback
│       ├── storage/
│       │   └── offline_queue.py        # SQLite offline buffer
│       └── ota/
│           └── ota_updater.py
│
├── infra/                              # ========== INFRA ==========
│   ├── emqx/
│   │   ├── emqx.conf                   # mTLS, ACL, schema
│   │   └── acl.conf
│   ├── nginx/
│   │   └── conf.d/
│   │       └── app.conf
│   ├── grafana/
│   │   └── provisioning/
│   └── ssl/                            # mTLS CA/certs (mounted in prod)
│       └── README.md
│
├── mqtt/                               # MQTT topic schema definitions
│   ├── readings.schema.json
│   ├── status.schema.json
│   ├── dispense_validate.schema.json
│   └── dispense_complete.schema.json
│
├── platform/                           # ========== BACKEND ==========
│   ├── pyproject.toml
│   ├── requirements.txt
│   ├── alembic.ini
│   ├── alembic/
│   │   ├── env.py
│   │   └── versions/
│   ├── fmp/
│   │   │
│   │   ├── core/                       # Shared foundation
│   │   │   ├── __init__.py
│   │   │   ├── config.py               # pydantic-settings env config
│   │   │   ├── database.py             # async SQLAlchemy engine/session
│   │   │   ├── redis.py                # redis client + helpers
│   │   │   ├── security.py             # JWT, password hashing, RBAC deps
│   │   │   ├── logging.py
│   │   │   └── exceptions.py
│   │   │
│   │   ├── models/                     # SQLAlchemy 2.0 ORM models
│   │   │   ├── __init__.py
│   │   │   ├── base.py                 # Base + TimestampMixin + SoftDelete
│   │   │   ├── user.py                 # User, UploadBatch
│   │   │   ├── station.py              # Company, Site, Station, Dispenser, Employee
│   │   │   ├── tank.py                 # Tank, Alarm, Measurement (hypertable)
│   │   │   ├── dispensing.py           # Allocation, DispenseCode, Transaction, StationTotalizer
│   │   │   └── notifications.py        # NotificationGateway, NotificationLog
│   │   │
│   │   ├── schemas/                    # Pydantic v2 schemas
│   │   │   ├── __init__.py
│   │   │   ├── user.py                 # User DTOs
│   │   │   ├── org.py                  # Company/Site/Station/Dispenser DTOs
│   │   │   ├── dispensing.py
│   │   │   ├── notifications.py        # dispatch DTOs + NotificationGateway CRUD
│   │   │   ├── tanks.py                # tanks + telemetry + alarm DTOs
│   │   │   └── totalizers.py           # secret counter readback DTOs
│   │   │
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── auth.py                 # authenticate + JWT issue/load
│   │   │   ├── dispensing/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── code_generator.py      # secure code gen
│   │   │   │   ├── dispense_engine.py     # validate + partial engine
│   │   │   │   ├── excel_ingestion.py     # Excel CSV/xlsx ingest
│   │   │   │   ├── totalizer_audit.py     # secret counter audit
│   │   │   │   └── cache.py               # code/remaining cache
│   │   │   ├── notifications/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── dispatcher.py          # async dispatch orchestrator
│   │   │   │   ├── smpp.py                # SMPP client interface
│   │   │   │   ├── whatsapp.py            # WhatsApp Business API
│   │   │   │   └── deps.py                # gateway selection
│   │   │   └── mqtt/
│   │   │       ├── __init__.py
│   │   │       ├── broker.py              # EMQX/Mosquitto pub/sub (aio-mqtt)
│   │   │       └── schema.py              # JSON schema loaders/validators
│   │   │
│   │   ├── ingestion/                    # ===== Edge Ingestion Engine =====
│   │   │   ├── __init__.py
│   │   │   ├── main.py                   # standalone FastAPI :8001 + MQTT sub
│   │   │   ├── processor.py              # EMA + MAD Z-score + volume calc (pure)
│   │   │   ├── pipeline.py               # reading → calibrate → alarms → persist
│   │   │   └── batch_writer.py           # hypertable promotion + batch inserts
│   │   │
│   │   ├── scripts/
│   │   │   └── init_db.py              # compose db-init: create_all + hypertables
│   │   │
│   │   ├── api/                          # ===== Central API =====
│   │   │   ├── __init__.py
│   │   │   ├── deps.py                  # session, get_current_user, require_roles
│   │   │   ├── main.py                   # FastAPI :8000, routers, CORS
│   │   │   ├── realtime.py               # in-process WebSocket push manager
│   │   │   └── v1/
│   │   │       ├── __init__.py
│   │   │       ├── auth.py              # POST /auth/login, GET /auth/me
│   │   │       ├── companies.py         # company registry CRUD
│   │   │       ├── sites.py             # site CRUD + stations
│   │   │       ├── stations.py          # station CRUD + dispensers
│   │   │       ├── dispensing.py        # upload / validate / complete
│   │   │       ├── tanks.py             # tank inventory + telemetry + alarms
│   │   │       ├── totalizers.py        # secret counter readback series
│   │   │       └── realtime.py          # /ws/telemetry + /ws/alarms stream
│   │   │
│   │   ├── workers/                       # ===== Async workers =====
│   │   │   ├── __init__.py
│   │   │   ├── celery_app.py
│   │   │   ├── beat.py
│   │   │   └── tasks/
│   │   │       ├── __init__.py
│   │   │       ├── notifications.py       # dispatch SMS/WhatsApp
│   │   │       ├── excel_process.py       # long-running Excel parse
│   │   │       ├── reports.py
│   │   │       └── forecasting.py
│   │   │
│   │   └── tests/
│   │       ├── __init__.py
│   │       ├── conftest.py
│   │       ├── unit/
│   │       │   ├── test_code_generator.py
│   │       │   ├── test_dispense_engine.py
│   │       │   ├── test_excel_ingestion.py
│   │       │   ├── test_processor.py      # physics + EMA + MAD
│   │       │   ├── test_alarm_rules.py
│   │       │   ├── test_pipeline_events.py
│   │   │   ├── test_realtime.py       # WS broadcast filters
│   │   │   ├── test_auth.py           # authenticate + JWT load
│   │   │   └── test_totalizer_audit.py
│   │   └── integration/
│   │       ├── test_dispense_flow.py
│   │       ├── test_telemetry_pipeline.py  # hypertables + full pipeline
│   │       └── test_api_surface.py         # live org CRUD + authz via httpx
│   │
│   └── alembic/
│
├── web/                                  # ======== PRESENTATION ========
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   ├── index.html
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── api/                          # REST + WS clients
│       │   ├── http.ts
│       │   └── websocket.ts
│       ├── components/
│       │   ├── layout/
│       │   ├── charts/
│       │   └── ui/
│       ├── context/                      # auth store (zustand)
│       ├── pages/
│       │   ├── login.tsx
│       │   ├── dashboard.tsx
│       │   ├── tanks.tsx
│       │   ├── dispensing/
│       │   │   ├── upload.tsx
│       │   │   ├── allocations.tsx
│       │   │   └── transactions.tsx
│       │   ├── stations.tsx
│       │   └── totalizers.tsx
│       └── lib/
│
├── scripts/                              # ======== OPS SCRIPTS ========
│   ├── gen_mtls_certs.sh                 # X.509 device certificate provisioning
│   ├── init_timescale.sh                 # hypertables + policies
│   └── docker-entrypoint.sh
│
└── docs/
    ├── architecture/
    │   ├── architecture.md
    │   └── entity_relationship.md
    └── API_CONTRACTS.md
```