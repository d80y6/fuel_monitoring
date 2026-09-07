# Entity-Relationship Diagram — Cloud Fuel & Dispensing Platform

## Complete ERD

```mermaid
erDiagram
    USER {
        int id PK
        string username UK
        string email UK
        string password_hash
        string first_name
        string last_name
        string role
        bool is_active
        string phone
        datetime created_at
        datetime deleted_at
    }

    COMPANY {
        int id PK
        string name UK
        string address
        string contact_name
        string contact_email
        string contact_phone
        datetime created_at
        datetime deleted_at
    }

    SITE {
        int id PK
        string name
        int company_id FK
        string address
        string location
        bool is_active
        datetime created_at
        datetime deleted_at
    }

    TANK {
        int id PK
        string name
        int site_id FK
        string gateway_mac
        bigint sensor_serial_number UK
        int device_address
        string tank_orientation
        float tank_height
        float tank_diameter
        float fluid_density
        float elevation
        float low_level_threshold
        float critical_level_threshold
        float high_level_threshold
        bool is_active
        datetime last_connection
        string connection_status
        datetime deleted_at
    }

    MEASUREMENT {
        bigint id PK
        datetime timestamp
        int tank_id FK
        float pressure
        float temperature
        float level
        float volume
        float flow_rate
        float fill_percent
        int status
    }

    ALARM {
        int id PK
        int tank_id FK
        datetime timestamp
        string type
        string level
        string message
        float value
        bool acknowledged
        int acknowledged_by FK
        datetime acknowledged_at
    }

    STATION {
        int id PK
        string name
        int site_id FK
        string serial_number UK
        string raspberry_pi_id
        string firmware_version
        string connection_status
        datetime last_heartbeat
        bool is_active
        datetime deleted_at
    }

    DISPENSER {
        int id PK
        int station_id FK
        string name
        string serial_number
        string modbus_address
        string dispenser_model
        bool is_active
        datetime created_at
    }

    EMPLOYEE {
        int id PK
        int company_id FK
        string employee_id UK
        string name
        string phone
        string email
        bool is_active
        datetime created_at
        datetime deleted_at
    }

    ALLOCATION {
        int id PK
        int employee_id FK
        int upload_batch_id FK
        int company_id FK
        string invoice_number
        float allocated_liters
        float dispensed_liters
        float remaining_liters
        string status
        datetime created_at
        datetime updated_at
    }

    DISPENSE_CODE {
        int id PK
        int allocation_id FK
        string code_hash
        string code_encrypted
        int code_length
        float authorized_liters
        float consumed_liters
        string status
        int max_attempts
        int attempt_count
        datetime expires_at
        datetime created_at
        datetime used_at
    }

    DISPENSE_TRANSACTION {
        bigint id PK
        datetime timestamp
        int station_id FK
        int dispenser_id FK
        int code_id FK
        int employee_id FK
        int allocation_id FK
        float requested_liters
        float actual_liters
        bigint secret_totalizer_before
        bigint secret_totalizer_after
        string status
        string discrepancy_flag
        string notes
    }

    UPLOAD_BATCH {
        int id PK
        string filename
        string original_filename
        int uploaded_by FK
        int total_rows
        int successful_rows
        int failed_rows
        string status
        datetime created_at
        datetime completed_at
    }

    NOTIFICATION_GATEWAY {
        int id PK
        string name UK
        string type
        string config_json
        bool is_active
        int priority
        datetime created_at
        datetime updated_at
    }

    NOTIFICATION_LOG {
        int id PK
        int allocation_id FK
        int gateway_id FK
        string channel
        string recipient_phone
        string status
        string provider_message_id
        string error_message
        int retry_count
        datetime sent_at
        datetime created_at
    }

    STATION_TOTALIZER {
        bigint id PK
        datetime timestamp
        int station_id FK
        int dispenser_id FK
        bigint totalizer_value
        float cumulative_liters
        string source
    }

    USER ||--o{ ALARM : "acknowledges"
    USER ||--o{ UPLOAD_BATCH : "uploads"
    COMPANY ||--o{ SITE : "owns"
    COMPANY ||--o{ EMPLOYEE : "employs"
    SITE ||--o{ TANK : "contains"
    SITE ||--o{ STATION : "contains"
    TANK ||--o{ MEASUREMENT : "produces"
    TANK ||--o{ ALARM : "triggers"
    STATION ||--o{ DISPENSER : "operates"
    STATION ||--o{ DISPENSE_TRANSACTION : "records"
    STATION ||--o{ STATION_TOTALIZER : "tracks"
    UPLOAD_BATCH ||--o{ ALLOCATION : "creates"
    ALLOCATION ||--o{ DISPENSE_CODE : "generates"
    EMPLOYEE ||--o{ ALLOCATION : "receives"
    ALLOCATION ||--o{ DISPENSE_TRANSACTION : "settles"
    DISPENSE_CODE ||--o{ DISPENSE_TRANSACTION : "authorizes"
    NOTIFICATION_GATEWAY ||--o{ NOTIFICATION_LOG : "routes"
    ALLOCATION ||--o{ NOTIFICATION_LOG : "notifies"
```

## Table Details

### TimescaleDB Hypertables
| Table | Partition Column | Chunk Interval | Compression | Retention |
|---|---|---|---|---|
| `measurements` | `timestamp` | 1 day | 7 days | 90 days |
| `dispense_transactions` | `timestamp` | 1 day | 7 days | 365 days |
| `station_totalizers` | `timestamp` | 1 day | 7 days | 365 days |

### Dispense Code Lifecycle
```
GENERATED → ACTIVE → CONSUMED (full) 
                 └──→ PARTIAL (converted to new allocation + new code)
                 └──→ EXPIRED (TTL)
                 └──→ REVOKED
```

### Allocation Status
```
PENDING → PARTIAL_FULFILLED → FULFILLED
                └──→ EXPIRED
                └──→ VOID
```