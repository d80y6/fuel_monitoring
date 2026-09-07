# Cloud Fuel & Dispensing Platform — Architecture

## 1. High-Level System Architecture

```mermaid
flowchart TB
    subgraph EDGE["EDGE LAYER"]
        ESP["ESP32-S3 Gateway<br/>(Keller RS-485 === sensors)<br/>Telemetry: pressure/temp/volume"]
        RPI["Raspberry Pi Station Node<br/>(RS-485 Modbus === Fuel Dispenser)<br/>Code entry, dispense control,<br/>secret totalizer readback"]
    end

    subgraph MQTT["MQTT MESSAGE BROKER — EMQX Enterprise"]
        EMQX["EMQX Cluster<br/>mTLS X.509 device auth<br/>JSON schema validation (OpVia)<br/>Topics: fuel/+, dispense/+"]
    end

    subgraph INGEST["INGESTION LAYER — FastAPI Async (port 8001)"]
        INGEST_APP["Edge Ingestion Engine<br/>MQTT subscriber<br/>EMA smoothing / MAD Z-score<br/>Batch writes to TimescaleDB"]
    end

    subgraph API["CENTRAL API — FastAPI Async (port 8000)"]
        API_APP["API + WebSocket server<br/>REST endpoints<br/>Real-time push<br/>Auth (JWT + OAuth2) / RBAC"]
        DISP["Dispense Engine<br/>validate_code / partial dispense<br/>totalizer audit"]
        EXCEL["Excel Ingestion<br/>+ Code Generator"]
    end

    subgraph WORKERS["ASYNC WORKERS — Celery/ARQ"]
        W_NOTIFY["Notification Dispatcher<br/>SMPP / WhatsApp BSP"]
        W_REPORT["Report renderer"]
        W_AI["AI forecast"]
    end

    subgraph DATA["DATA LAYER"]
        DB[("PostgreSQL 16 + TimescaleDB<br/>Hypertables: measurements,<br/>dispense_transactions<br/>1-day chunks, compression")]
        REDIS[("Redis<br/>Cache, Pub/Sub, Rate Limit,<br/>Deduplication, Offline buffer")]
    end

    subgraph WEB["PRESENTATION LAYER"]
        SPA["React SPA (Vite)<br/>Tailwind + Lucide<br/>Chart.js/Recharts<br/>WebSocket client"]
    end

    subgraph INFRA["DEVOPS / INFRASTRUCTURE"]
        NGINX["Nginx / Traefik gateway"]
        CF["GitHub Actions CI/CD"]
        OTA["OTA firmware server"]
    end

    ESP -->|"MQTT mTLS"| EMQX
    RPI -->|"MQTT mTLS<br/>dispense/{station}/validate<br/>dispense/{station}/complete"| EMQX
    RPI -->|"WebSocket offline recovery"| API_APP
    EMQX -->|"subscribe <br/>fuel/+/readings,<br/>dispense/+/+"| INGEST_APP
    INGEST_APP -->|"bulk insert<br/>measurements"| DB
    INGEST_APP -->|"commands/OTA<br/>fuel/{mac}/commands"| EMQX
    API_APP -->|"validate/complete<br/>partial dispense"| DB
    API_APP -->|"code_response"| EMQX
    DISP --> DB
    EXCEL -->|"generate quotas + codes"| DB
    API_APP --> REDIS
    INGEST_APP --> REDIS
    WORKERS --> REDIS
    WORKERS --> DB
    W_NOTIFY -->|"SMPP/SMSC"| SMS["SMPP SMS Gateway"]
    W_NOTIFY -->|"WhatsApp Business API"| WA["WhatsApp BSP"]
    SPA -->|"HTTPS"| NGINX
    NGINX --> API_APP
    SPA <-->|"WSS real-time"| API_APP
    CF -->|"deploy"| INFRA
    OTA -->|"firmware images"| EMQX
```

## 2. Tank Monitoring Telemetry Flow

```mermaid
sequenceDiagram
    participant K as Keller Sensor (RS-485)
    participant E as ESP32-S3 (MQTT mTLS)
    participant EM as EMQX (schema validate)
    participant I as Ingestion Engine
    participant TB as TimescaleDB
    participant R as Redis
    participant W as WebSocket Server
    participant D as Dashboard SPA

    K->>E: pressure/temp reading
    E->>EM: publish fuel/{mac}/readings {pressure_bar, temperature_c, ...}
    EM->>EM: JSON schema validation
    EM->>I: forward valid reading
    I->>I: EMA smoothing, MAD Z-score, level/volume calc
    I->>TB: bulk batch write (50 msgs / 5s)
    I->>R: publish update channel
    R->>W: forward
    W->>D: WebSocket push live level/volume
```

## 3. Fuel Dispensing & Code Allocation Flow

```mermaid
sequenceDiagram
    participant A as Admin
    participant F as FastAPI API
    participant E as ExcelIngestor
    participant C as CodeGenerator
    participant N as Notification Dispatcher
    participant R as Redis
    participant D as Dashboard
    participant RPI as RPi Station Node
    participant PU as Pump/Dispenser
    participant TX as Transaction Store
    participant TOT as Totalizer

    A->>F: Upload Excel (emp_id, name, phone, invoice, liters)
    F->>E: parse & validate rows
    E->>C: generate 6-8 digit OTP per allocation
    C->>F: {allocation, code, hash}
    F->>R: store code (TTL 7d) 
    F->>N: dispatch SMS/WhatsApp {code, employee}
    N-->>D: gateway delivery status

    Note over RPI,PU: At station
    RPI->>F: POST /dispense/validate {code, station}
    F->>R: lookup code + remaining liters
    F-->>RPI: {valid, remaining_liters, employee}
    RPI->>PU: unlock & dispense <= authorized
    PU-->>RPI: actual liters + secret totalizer
    RPI->>F: POST /dispense/complete {code, actual_liters, totalizer}
    F->>TX: record transaction, consume code
    alt actual < allocated (partial)
        F->>C: generate NEW code for remainder
        F->>N: dispatch new code to employee
        F-->>RPI: {partial: true, new_code_msg}
    end
    F->>D: totalizer audit log update
```

## 4. Offline Buffering & Backfill

```mermaid
flowchart TD
    subgraph EDGE["Offline Edge"]
        Q1["RPi/ESP32 local SQLite<br/>/ flash store"]
        BUF["buffer queue (WAL)"]
    end
    subgraph CLOUD["Online"]
        ING["Ingestion API"]
        TB2["TimescaleDB"]
    end
    EDGE -->|"conn lost"| BUF
    BUF -->|"reconnect + backfill<br/>ordered by ts, idempotency key"| ING
    ING -->|"dedupe via Redis<br/>(msg id)"| TB2
```

## 5. DDR Collision of Technology Choices

```mermaid
pie title Component Runtime
    "FastAPI Edge Ingestion" : 25
    "FastAPI Central API" : 25
    "React SPA (Vite)" : 15
    "PostgreSQL/TimescaleDB" : 15
    "Celery/ARQ Workers" : 10
    "EMQX MQTT" : 10