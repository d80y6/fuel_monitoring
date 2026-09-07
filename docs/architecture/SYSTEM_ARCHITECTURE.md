# Cloud Fuel & Dispensing Platform — System Architecture

## High-Level Architecture Overview

```mermaid
graph TB
    subgraph "EDGE LAYER"
        ESP["ESP32-S3 Gateway<br/>(Keller RS-485 Sensors)"]
        RPI["Raspberry Pi Node<br/>(Fuel Dispenser + Modbus RS-485)"]
        ESP -->|"MQTT: fuel/+/readings<br/>fuel/+/status"| EMQX
        RPI -->|"MQTT: dispense/+/validate<br/>dispense/+/complete<br/>dispense/+/heartbeat"| EMQX
        EMQX -->|"MQTT: dispense/+/code_response"| RPI
    end

    subgraph "MESSAGE BROKER"
        EMQX["EMQX Enterprise<br/>mTLS + JSON Schema<br/>Validation"]
    end

    subgraph "INGESTION LAYER"
        INGEST["Edge Ingestion Engine<br/>(FastAPI Async)"]
        INGEST -->|"Subscribe: fuel/+/readings<br/>fuel/+/status"| EMQX
        INGEST -->|"Subscribe: dispense/+/complete<br/>dispense/+/heartbeat"| EMQX
    end

    subgraph "APPLICATION LAYER"
        API["Central API<br/>(FastAPI Async)"]
        WORKER["Celery Workers<br/>(Notifications, Reports,<br/>Excel Ingestion)"]
        API -->|"Publish: dispense/+/code_response"| EMQX
        API -->|"Validate codes,<br/>manage quotas"| DB
        WORKER -->|"Send SMS/WhatsApp"| NOTIFY["Notification<br/>Dispatcher"]
        NOTIFY -->|"SMPP"| SMS_GW["SMS Gateway<br/>(SMPP)"]
        NOTIFY -->|"HTTP API"| WA_API["WhatsApp Business<br/>API"]
    end

    subgraph "PRESENTATION LAYER"
        WEB["React SPA Dashboard<br/>(Vite + Tailwind)"]
        WEB <-->|"REST API + WebSockets"| API
    end

    subgraph "DATA LAYER"
        DB[("PostgreSQL<br/>+ TimescaleDB")]
        REDIS[("Redis<br/>Pub/Sub + Cache<br/>+ Rate Limiting")]
    end

    subgraph "INFRASTRUCTURE"
        NGINX["Nginx<br/>Reverse Proxy<br/>+ Static Assets"]
        DOCKER["Docker Compose<br/>Stack"]
        CICD["GitHub Actions<br/>CI/CD"]
    end

    INGEST -->|"Bulk write<br/>measurements"| DB
    INGEST -->|"Publish SSE events"| REDIS
    REDIS -->|"Subscribe events"| API
    API --> DB
    API --> REDIS
    WEB --> NGINX
    NGINX --> API
```

## Data Ingestion Pipeline — Tank Monitoring

```mermaid
flowchart LR
    subgraph "ESP32-S3 Edge"
        S1["Keller Sensor<br/>RS-485"]
        S2["Pressure + Temp<br/>Readings"]
        S1 --> S2
    end

    S2 -->|"MQTT Publish<br/>fuel/{mac}/readings"| EMQX
    EMQX -->|"Subscribe"| INGEST

    subgraph "Edge Ingestion Engine"
        V["JSON Schema<br/>Validation"]
        L["Tank Lookup<br/>(Redis LRU Cache)"]
        P["Measurement<br/>Processor<br/>(EMA + MAD)"]
        F["Flow Rate<br/>Calculator<br/>(State Machine)"]
        B["Batch Writer<br/>(50 items / 5s)"]
        A["Alarm<br/>Manager<br/>(Threshold + Cooldown)"]
        V --> L --> P --> F --> B
        F --> A
    end

    B -->|"bulk_save_objects()"| DB[("TimescaleDB<br/>Hypertable<br/>1-day chunks")]
    A -->|"Create Alarm"| DB
    B -->|"Publish"| REDIS["Redis Pub/Sub"]
    REDIS -->|"SSE Stream"| SSE["/tank-updates<br/>EventStream"]
    SSE --> DASH["Dashboard<br/>Charts"]
```

## Fuel Dispensing Pipeline

```mermaid
sequenceDiagram
    participant Admin as Admin Dashboard
    participant API as Central API
    participant Redis as Redis Cache
    participant Worker as Celery Worker
    participant Notify as Notification Dispatcher
    participant RPI as Raspberry Pi
    participant Dispenser as Fuel Dispenser

    Note over Admin,Dispenser: Phase 1: Allocation & Code Generation
    Admin->>API: POST /api/dispensing/upload (Excel file)
    API->>API: Validate rows, create Allocations
    API->>API: Generate 6-8 digit unique OTP codes
    API->>Redis: Cache code → allocation mapping (TTL: 7 days)
    API->>Worker: dispatch_code(allocation_id)
    Worker->>Notify: Send SMS/WhatsApp to employee
    Notify-->>RPI: Code delivered to employee phone

    Note over Admin,Dispenser: Phase 2: Dispensing at Station
    RPI->>Dispenser: Connect via RS-485 Modbus
    Employee->>RPI: Enter unique code
    RPI->>API: GET /api/dispensing/validate/{code}
    API->>Redis: Lookup code → allocation
    API-->>RPI: {valid: true, remaining_liters: 25.5, employee: "..."}
    RPI->>Dispenser: Unlock pump, dispense up to authorized limit
    Dispenser-->>RPI: Actual liters dispensed
    RPI->>Dispenser: Read secret totalizer (counter meter)
    Dispenser-->>RPI: Hardware totalizer value

    Note over Admin,Dispenser: Phase 3: Completion & Partial Dispense
    RPI->>API: POST /api/dispensing/complete
    API->>API: Record transaction, update quota
    alt actual < allocated (partial dispense)
        API->>API: Generate NEW code for remaining balance
        API->>Worker: dispatch_code(new_allocation_id)
        Worker->>Notify: Send new code to employee
    end
    API->>Redis: Invalidate old code
    API-->>RPI: {success: true, ...}

    Note over Admin,Dispenser: Phase 4: Audit
    API->>API: Compare totalizer vs cumulative transactions
    API->>API: Flag discrepancies (theft/tampering detection)
```

## MQTT Topic Architecture

```mermaid
graph LR
    subgraph "Tank Monitoring"
        T1["fuel/{gateway_mac}/readings"]
        T2["fuel/{gateway_mac}/status"]
        T3["fuel/{gateway_mac}/errors"]
        T4["fuel/{gateway_mac}/commands"]
    end

    subgraph "Fuel Dispensing"
        D1["dispense/{station_id}/validate"]
        D2["dispense/{station_id}/code_response"]
        D3["dispense/{station_id}/complete"]
        D4["dispense/{station_id}/heartbeat"]
        D5["dispense/{station_id}/ota"]
    end

    subgraph "System"
        S1["fuel/service/status"]
        S2["system/ota/{device_type}/{device_id}"]
    end
```

## Service Topology

```mermaid
graph TB
    subgraph "Docker Compose Stack"
        NGINX["nginx:alpine<br/>:80/:443"]
        WEB["web:node-alpine<br/>React SPA build"]
        API["api:python3.11<br/>FastAPI :8000"]
        INGEST["ingest:python3.11<br/>MQTT Ingestion :8001"]
        WORKER["worker:python3.11<br/>Celery Worker"]
        BEAT["beat:python3.11<br/>Celery Beat"]
        DB["postgres:16<br/>+ TimescaleDB :5432"]
        REDIS["redis:7-alpine<br/>:6379"]
        EMQX["emqx/emqx:5<br/>MQTT Broker :1883/:8083/:8883"]
    end

    NGINX --> WEB
    NGINX --> API
    API --> DB
    API --> REDIS
    INGEST --> DB
    INGEST --> REDIS
    INGEST --> EMQX
    WORKER --> DB
    WORKER --> REDIS
    BEAT --> REDIS
```
