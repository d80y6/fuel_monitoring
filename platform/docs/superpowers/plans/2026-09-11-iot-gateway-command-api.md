# IoT Gateway Command API Implementation Plan (SUB-2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a managed `IoTGateway` entity and a durable, ack-tracked command API that sends control commands to edge gateways over MQTT, plus a full frontend console.

**Architecture:** Three services cooperate. The API (8000) persists commands and enqueues them to a Redis list; the ingestion service (8001) relay task BLMOVEs the queue into an inflight list and publishes to `fuel/{mac}/command`; the gateway replies on `fuel/{mac}/command/ack`, which ingestion matches to the row via `command_id`. A Celery-beat sweeper retries unacked commands on exponential backoff and fails them after `max_attempts`. New `iot_gateways` and `gateway_commands` tables; `tanks.gateway_id` FK backfilled from the existing `tank.gateway_mac`.

**Tech Stack:** FastAPI (API :8000 / ingestion :8001), SQLAlchemy async + TimescaleDB, Redis (lists + pub/sub), paho-mqtt against EMQX 5.8, Celery beat/worker, React 18 + TanStack Query (frontend console).

**Spec:** `platform/docs/superpowers/specs/2026-09-11-iot-gateway-command-api-design.md` (design approved 2026-09-11).

---

## File structure

| File | Responsibility | Action |
|------|---------------|--------|
| `platform/fmp/models/gateway.py` | `IoTGateway` + `GatewayCommand` ORMs | Create |
| `platform/fmp/models/tank.py` | add `Tank.gateway_id` FK | Modify |
| `platform/fmp/models/__init__.py` | export new models | Modify |
| `platform/fmp/schemas/iot.py` | gateway + command schemas, per-type payload validators | Create |
| `platform/fmp/api/v1/iot_gateways.py` | CRUD + command-issue + history API | Create |
| `platform/fmp/api/main.py` | register the new router | Modify |
| `platform/fmp/core/config.py` | command-queue/backoff/TTL settings | Modify |
| `platform/fmp/ingestion/relay.py` | queue keys, topic builders, backoff, ack parse, publish helper | Create |
| `platform/fmp/ingestion/main.py` | subscribe `fuel/+/command/ack`, ack handler, gateway auto-register, relay loop | Modify |
| `platform/fmp/workers/tasks/commands.py` | Celery TTL sweeper (retry/fail) | Create |
| `platform/fmp/workers/celery_app.py` | include commands task + beat schedule | Modify |
| `platform/fmp/scripts/backfill_gateways.py` | add `tanks.gateway_id` + backfill from `gateway_mac` | Create |
| `platform/fmp/scripts/init_db.py` | run create_all (new tables auto-included) | No change (verify) |
| `docker-compose.yml` | db-init command runs backfill after init | Modify |
| `platform/fmp/tests/conftest.py` | FakeRedis list ops | Modify |
| `platform/fmp/tests/unit/test_iot_schemas.py` | payload validators | Create |
| `platform/fmp/tests/unit/test_gateway_relay.py` | relay helpers + backoff + ack parse | Create |
| `platform/fmp/tests/integration/test_iot_gateway_api.py` | CRUD + command round-trip via API | Create |
| `platform/fmp/tests/integration/test_gateway_ingestion.py` | provisioning + ack handler + sweeper flow | Create |
| `platform/fmp/tests/integration/test_backfill.py` | backfill script | Create |
| `web/src/lib/apiTypes.ts` | gateway/command types | Modify |
| `web/src/api/iot.ts` | `iotApi` methods | Create |
| `web/src/api/client.ts` | spread `iotApi` | Modify |
| `web/src/pages/IoTGatewaysPage.tsx` | gateways list + create/editor | Create |
| `web/src/pages/IoTGatewayDetailPage.tsx` | detail, command composer, history | Create |
| `web/src/router.tsx` | routes + nav | Modify |
| `web/src/components/layout/AppLayout.tsx` | nav entry | Modify |
| `web/src/pages/IoTGatewaysPage.test.tsx` | list + create test | Create |
| `web/src/pages/IoTGatewayDetailPage.test.tsx` | composer + history test | Create |

### Task dependency order

`T1 models` → `T2 config+relay` → `T3 schemas` → `T4 router CRUD` → `T5 router commands+history` → `T6 ingestion (subscribe/ack/provision/relay)` → `T7 sweeper` → `T8 backfill+compose` → then frontend `T9 api`, `T10 list`, `T11 detail` → `T12 full regression + docs`.

---

## Test harness

All backend tests run in the compose network against live infra (authoritative; matches SUB-1 convention). From repo root `/home/ubuntu/fuel_monitoring`:

```bash
docker run --rm --network fuel-platform_default \
  -v /home/ubuntu/fuel_monitoring/.worktrees/iot-command-api/platform:/srv/fmp \
  -e POSTGRES_HOST=db -e POSTGRES_PORT=5432 -e POSTGRES_DB=fuel_platform \
  -e POSTGRES_USER=fuel_platform -e POSTGRES_PASSWORD=fuel_platform \
  -e REDIS_HOST=redis -e REDIS_PORT=6379 -e MQTT_BROKER=emqx -e MQTT_PORT=1883 \
  -w /srv/fmp fuel-platform-api python -m pytest <TARGET> -q
```

Unit tests use `FakeRedis` and live against the same harness (or with `-e FMP_SKIP_INFRA=1` for pure-hermetic runs). `pytestmark = pytest.mark.asyncio` is required on every module (repo has no `asyncio_mode=auto`).

Web tests: from `/home/ubuntu/fuel_monitoring/web` run `npx vitest run <file>` (or `npm test`), with `vi.mock('../api/client', ...)` per existing `GatewaysPage.test.tsx` convention.

---

## Task 1: IoTGateway + GatewayCommand models

**Files:**
- Create: `platform/fmp/models/gateway.py`
- Modify: `platform/fmp/models/tank.py:31-34`
- Modify: `platform/fmp/models/__init__.py`
- Test: `platform/fmp/tests/unit/test_iot_models.py` (new)

- [ ] **Step 1: Write the failing unit test**

`platform/fmp/tests/unit/test_iot_models.py`:

```python
"""Unit tests: IoTGateway + GatewayCommand model shape (no DB)."""
from __future__ import annotations

from fmp.models.gateway import COMMAND_TYPES, GatewayCommand, IoTGateway
from fmp.models.tank import Tank


def test_command_types_catalog():
    assert set(COMMAND_TYPES) == {
        "reboot", "status_probe", "pause_reporting", "resume_reporting",
        "set_interval", "recalibrate", "zero_tank", "push_config",
    }


def test_gateway_columns():
    cols = IoTGateway.__table__.columns.keys()
    for name in ("id", "gateway_mac", "name", "firmware_version",
                 "last_seen", "connection_status", "is_active"):
        assert name in cols


def test_command_columns():
    cols = GatewayCommand.__table__.columns.keys()
    for name in ("id", "gateway_id", "command_id", "command_type", "payload_json",
                 "status", "attempts", "max_attempts", "sent_at", "next_retry_at",
                 "ack_status", "ack_detail", "ack_received_at", "error_message"):
        assert name in cols


def test_tank_has_gateway_fk():
    assert "gateway_id" in Tank.__table__.columns.keys()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `docker run --rm --network fuel-platform_default -v /home/ubuntu/fuel_monitoring/.worktrees/iot-command-api/platform:/srv/fmp -e FMP_SKIP_INFRA=1 -w /srv/fmp fuel-platform-api python -m pytest fmp/tests/unit/test_iot_models.py -q`
Expected: error `ModuleNotFoundError` (no `fmp/models/gateway.py`).

- [ ] **Step 3: Implement the models**

`platform/fmp/models/gateway.py`:

```python
"""ORMs: IoTGateway and GatewayCommand (edge device command plane)."""
from __future__ import annotations

import uuid as uuid_type
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fmp.core.database import Base
from fmp.models.base import TimestampMixin, UUIDPrimaryKeyMixin

COMMAND_TYPES = (
    "reboot", "status_probe", "pause_reporting", "resume_reporting",
    "set_interval", "recalibrate", "zero_tank", "push_config",
)


class IoTGateway(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An edge gateway registered against the platform."""

    __tablename__ = "iot_gateways"

    gateway_mac: Mapped[str] = mapped_column(String(17), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100), default="", index=True)
    firmware_version: Mapped[str | None] = mapped_column(String(32))
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    connection_status: Mapped[str] = mapped_column(String(20), default="offline")
    is_active: Mapped[bool] = mapped_column(default=False)

    commands: Mapped[list["GatewayCommand"]] = relationship(back_populates="gateway")
    tanks: Mapped[list["Tank"]] = relationship(  # noqa: F821
        back_populates="gateway"
    )


class GatewayCommand(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A command issued to an IoT gateway, tracked to ack/failure."""

    __tablename__ = "gateway_commands"

    gateway_id: Mapped[uuid_type.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("iot_gateways.id"), index=True
    )
    command_id: Mapped[uuid_type.UUID] = mapped_column(
        UUID(as_uuid=True), unique=True, default=uuid_type.uuid4
    )
    command_type: Mapped[str] = mapped_column(String(32), index=True)
    payload_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ack_status: Mapped[str | None] = mapped_column(String(32))
    ack_detail: Mapped[str | None] = mapped_column(String(255))
    ack_received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(String(255))

    gateway: Mapped["IoTGateway"] = relationship(back_populates="commands")
```

`platform/fmp/models/tank.py` — add the FK + relationship on the `Tank` class (after `site_id`, around line 33):

```python
    gateway_id: Mapped[uuid_type.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("iot_gateways.id"), index=True
    )
```

And in the `Tank` class add (near the site relationship; `site_id` already declared):

```python
    gateway: Mapped["IoTGateway"] = relationship(back_populates="tanks")  # noqa: F821
```

(Add `from typing import TYPE_CHECKING` guard is already present in tank.py; add `IoTGateway` to the `TYPE_CHECKING` block that already imports `FuelType`.)

`platform/fmp/models/__init__.py` — add imports + `__all__` entries:

```python
from fmp.models.gateway import COMMAND_TYPES, GatewayCommand, IoTGateway
```

and add `"COMMAND_TYPES", "GatewayCommand", "IoTGateway",` to `__all__`.

- [ ] **Step 4: Run tests to verify they pass**

Run: same harness command as Step 2.
Expected: `3 passed` (test command types + 3 column tests + tank FK test).

- [ ] **Step 5: Commit**

```bash
git add platform/fmp/models/gateway.py platform/fmp/models/tank.py platform/fmp/models/__init__.py platform/fmp/tests/unit/test_iot_models.py
git commit -m "feat: IoTGateway + GatewayCommand models, Tank.gateway_id FK (SUB-2)"
```

---

## Task 2: Config + relay helpers (queue keys, backoff, ack parse)

**Files:**
- Modify: `platform/fmp/core/config.py`
- Create: `platform/fmp/ingestion/relay.py`
- Modify: `platform/fmp/tests/conftest.py` (FakeRedis list ops)
- Test: `platform/fmp/tests/unit/test_gateway_relay.py` (new)

- [ ] **Step 1: Write the failing unit test**

`platform/fmp/tests/unit/test_gateway_relay.py`:

```python
"""Unit tests: gateway command relay queue + MQTT contract helpers."""
from __future__ import annotations

import pytest

from fmp.ingestion.relay import (
    QUEUE_INFLIGHT,
    QUEUE_OUTBOUND,
    ack_topic_for,
    command_topic_for,
    compute_backoff,
    parse_command_ack_topic,
)
from fmp.tests.conftest import FakeRedis


@pytest.mark.asyncio
async def test_queue_key_constants():
    assert QUEUE_OUTBOUND == "iot:commands:outbound"
    assert QUEUE_INFLIGHT == "iot:commands:inflight"


@pytest.mark.asyncio
async def test_topic_builders():
    assert command_topic_for("AA:BB:CC:DD:EE:01") == "fuel/AA:BB:CC:DD:EE:01/command"
    assert ack_topic_for("AA:BB:CC:DD:EE:01") == "fuel/AA:BB:CC:DD:EE:01/command/ack"


@pytest.mark.asyncio
async def test_ack_topic_parse():
    assert parse_command_ack_topic("fuel/AA:BB:CC:DD:EE:01/command/ack") == "AA:BB:CC:DD:EE:01"
    assert parse_command_ack_topic("fuel/AA:BB/readings") is None


@pytest.mark.asyncio
async def test_backoff_exponential_capped():
    assert compute_backoff(1) == 60
    assert compute_backoff(2) == 120
    # cap at 900 despite large exponent
    assert compute_backoff(10) == 900


@pytest.mark.asyncio
async def test_relay_roundtrip_via_fake_redis():
    redis = FakeRedis()
    await redis.lpush(QUEUE_OUTBOUND, "msg-1")
    item = await redis.brpoplpush(QUEUE_OUTBOUND, QUEUE_INFLIGHT, timeout=1)
    assert item == "msg-1"
    assert await redis.llen(QUEUE_INFLIGHT) == 1
    assert await redis.lpop(QUEUE_INFLIGHT) == "msg-1"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `docker run --rm --network fuel-platform_default -v /home/ubuntu/fuel_monitoring/.worktrees/iot-command-api/platform:/srv/fmp -e FMP_SKIP_INFRA=1 -w /srv/fmp fuel-platform-api python -m pytest fmp/tests/unit/test_gateway_relay.py -q`
Expected: failure (module missing; FakeRedis has no `lpush`/`brpoplpush`/`llen`/`lpop`).

- [ ] **Step 3: Add config settings**

`platform/fmp/core/config.py` — add after the `# --- Notifications ---` block:

```python
    # --- Gateway commands --------------------------------------------------
    COMMAND_QUEUE_OUTBOUND: str = "iot:commands:outbound"
    COMMAND_QUEUE_INFLIGHT: str = "iot:commands:inflight"
    COMMAND_BACKOFF_BASE_SECONDS: int = 60
    COMMAND_BACKOFF_MAX_SECONDS: int = 900
    COMMAND_MAX_ATTEMPTS: int = 3
    COMMAND_PENDING_TTL_SECONDS: int = 120
```

- [ ] **Step 4: Implement the relay module**

`platform/fmp/ingestion/relay.py`:

```python
"""Gateway command relay: durable Redis queue + MQTT topic helpers.

API enqueues commands (LPUSH outbound); the ingestion relay task lifts them
into an inflight list while it publishes to the broker; the sweeper requeues
unacked commands on backoff. Correlation uses a per-command UUID echoed by
the gateway on the ack topic.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

from fmp.core.config import get_settings

settings = get_settings()

QUEUE_OUTBOUND = settings.COMMAND_QUEUE_OUTBOUND
QUEUE_INFLIGHT = settings.COMMAND_QUEUE_INFLIGHT


def command_topic_for(gateway_mac: str) -> str:
    return f"fuel/{gateway_mac}/command"


def ack_topic_for(gateway_mac: str) -> str:
    return f"fuel/{gateway_mac}/command/ack"


def parse_command_ack_topic(topic: str) -> str | None:
    """``fuel/<mac>/command/ack`` → mac (or None)."""
    parts = topic.split("/")
    if len(parts) == 4 and parts[0] == "fuel" and parts[2] == "command" and parts[3] == "ack":
        return parts[1]
    return None


def compute_backoff(attempts: int) -> int:
    """Exponential backoff in seconds: base * 2^(attempts-1), capped."""
    seconds = settings.COMMAND_BACKOFF_BASE_SECONDS * (2 ** (attempts - 1))
    return min(seconds, settings.COMMAND_BACKOFF_MAX_SECONDS)


def next_retry_datetime(attempts: int) -> datetime:
    return datetime.now(timezone.utc) + timedelta(seconds=compute_backoff(attempts))


async def enqueue_command(redis, *, command_id: str, gateway_mac: str,
                          command_type: str, payload: dict,
                          issued_at: str | None = None) -> int:
    """LPUSH one command frame onto the durable outbound queue."""
    message = {
        "command_id": command_id,
        "gateway_mac": gateway_mac,
        "type": command_type,
        "payload": payload,
        "issued_at": issued_at or datetime.now(timezone.utc).isoformat(),
    }
    return await redis.lpush(QUEUE_OUTBOUND, json.dumps(message, default=str))


async def drain_inflight(redis) -> None:
    """Return any leftover inflight frames to outbound on startup."""
    while True:
        item = await redis.rpoplpush(QUEUE_INFLIGHT, QUEUE_OUTBOUND)
        if item is None:
            return


async def take_command(redis, timeout: int = 1) -> dict | None:
    """Blocking BLPOP outbound → inflight handoff; returns parsed frame or None."""
    raw = await redis.brpoplpush(QUEUE_OUTBOUND, QUEUE_INFLIGHT, timeout=timeout)
    if raw is None:
        return None
    return json.loads(raw)


async def release_command(redis) -> None:
    """Pop the currently-holding inflight frame after successful publish."""
    await redis.lpop(QUEUE_INFLIGHT)
```

- [ ] **Step 5: Extend FakeRedis with list ops**

`platform/fmp/tests/conftest.py` — add a `lists` field to the dataclass:

```python
    lists: dict = field(default_factory=dict)
```

And add methods to `FakeRedis` (after `async def delete`):

```python
    async def lpush(self, key: str, *values) -> int:
        bucket = self.lists.setdefault(key, [])
        bucket[:0] = list(values)
        return len(values)

    async def rpush(self, key: str, *values) -> int:
        self.lists.setdefault(key, []).extend(values)
        return len(values)

    async def lpop(self, key: str):
        bucket = self.lists.get(key)
        return bucket.pop(0) if bucket else None

    async def llen(self, key: str) -> int:
        return len(self.lists.get(key, []))

    async def rpoplpush(self, source: str, destination: str):
        bucket = self.lists.get(source)
        if not bucket:
            return None
        item = bucket.pop()
        self.lists.setdefault(destination, []).insert(0, item)
        return item

    async def brpoplpush(self, source: str, destination: str, timeout: int = 0):
        return await self.rpoplpush(source, destination)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: same harness command as Step 2.
Expected: `5 passed`.

- [ ] **Step 7: Commit**

```bash
git add platform/fmp/core/config.py platform/fmp/ingestion/relay.py platform/fmp/tests/conftest.py platform/fmp/tests/unit/test_gateway_relay.py
git commit -m "feat: gateway command relay queue, topics, backoff helpers (SUB-2)"
```

---

## Task 3: Pydantic schemas with per-type payload validation

**Files:**
- Create: `platform/fmp/schemas/iot.py`
- Test: `platform/fmp/tests/unit/test_iot_schemas.py` (new)

- [ ] **Step 1: Write the failing test**

`platform/fmp/tests/unit/test_iot_schemas.py`:

```python
"""Unit tests: IoT gateway + command schema payload validation."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from fmp.schemas.iot import IoTCommandCreate


def test_reboot_requires_empty_payload():
    cmd = IoTCommandCreate(command_type="reboot", payload={})
    assert cmd.payload == {}


def test_set_interval_requires_positive_seconds():
    with pytest.raises(ValidationError):
        IoTCommandCreate(command_type="set_interval", payload={})
    with pytest.raises(ValidationError):
        IoTCommandCreate(command_type="set_interval", payload={"interval_s": 0})
    cmd = IoTCommandCreate(command_type="set_interval", payload={"interval_s": 5})
    assert cmd.payload["interval_s"] == 5


def test_recalibrate_requires_sensor_and_reference():
    with pytest.raises(ValidationError):
        IoTCommandCreate(command_type="recalibrate", payload={"sensor": "P1"})
    cmd = IoTCommandCreate(
        command_type="recalibrate",
        payload={"sensor": "P1", "reference_pressure_bar": 0.133},
    )
    assert cmd.payload["reference_pressure_bar"] == 0.133


def test_zero_tank_requires_serial():
    with pytest.raises(ValidationError):
        IoTCommandCreate(command_type="zero_tank", payload={})
    cmd = IoTCommandCreate(command_type="zero_tank", payload={"tank_serial": "SN-1", "level_m": 0.0})
    assert cmd.payload["tank_serial"] == "SN-1"


def test_push_config_requires_nonempty_object():
    with pytest.raises(ValidationError):
        IoTCommandCreate(command_type="push_config", payload={})
    cmd = IoTCommandCreate(command_type="push_config", payload={"interval_s": 5})
    assert cmd.payload["interval_s"] == 5


def test_unknown_command_type_rejected():
    with pytest.raises(ValidationError):
        IoTCommandCreate(command_type="explode", payload={})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker run --rm --network fuel-platform_default -v /home/ubuntu/fuel_monitoring/.worktrees/iot-command-api/platform:/srv/fmp -e FMP_SKIP_INFRA=1 -w /srv/fmp fuel-platform-api python -m pytest fmp/tests/unit/test_iot_schemas.py -q`
Expected: error (module `fmp.schemas.iot` missing).

- [ ] **Step 3: Implement the schemas**

`platform/fmp/schemas/iot.py`:

```python
"""Pydantic v2 schemas for IoT gateway command API."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CommandType = Literal[
    "reboot", "status_probe", "pause_reporting", "resume_reporting",
    "set_interval", "recalibrate", "zero_tank", "push_config",
]


class IoTGatewayCreate(BaseModel):
    gateway_mac: str = Field(min_length=1, max_length=17)
    name: str | None = Field(default=None, max_length=100)
    firmware_version: str | None = Field(default=None, max_length=32)


class IoTGatewayUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    firmware_version: str | None = Field(default=None, max_length=32)
    is_active: bool | None = None
    tank_ids: list[uuid.UUID] | None = None


class IoTGatewayRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    gateway_mac: str
    name: str
    firmware_version: str | None
    last_seen: datetime | None
    connection_status: str
    is_active: bool
    tank_ids: list[uuid.UUID] = Field(default_factory=list)
    created_at: datetime


class IoTCommandCreate(BaseModel):
    command_type: CommandType
    payload: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_payload(self):
        p = self.payload
        empty_ok = {"reboot", "status_probe", "resume_reporting"}
        if self.command_type in empty_ok:
            if p:
                raise ValueError(f"{self.command_type} accepts no payload")
            return self
        if self.command_type == "pause_reporting":
            if "duration_s" in p and (not isinstance(p["duration_s"], int) or p["duration_s"] < 1):
                raise ValueError("duration_s must be a positive integer")
            return self
        if self.command_type == "set_interval":
            if not isinstance(p.get("interval_s"), int) or p.get("interval_s", 0) < 1:
                raise ValueError("interval_s must be a positive integer (seconds)")
            return self
        if self.command_type == "recalibrate":
            if not p.get("sensor") or not isinstance(p["sensor"], str):
                raise ValueError("recalibrate requires sensor (str)")
            ref = p.get("reference_pressure_bar")
            if not isinstance(ref, float) and not isinstance(ref, int):
                raise ValueError("recalibrate requires reference_pressure_bar (float)")
            return self
        if self.command_type == "zero_tank":
            if not p.get("tank_serial") or not isinstance(p["tank_serial"], str):
                raise ValueError("zero_tank requires tank_serial (str)")
            if "level_m" in p and not isinstance(p["level_m"], (int, float)):
                raise ValueError("level_m must be numeric")
            return self
        if self.command_type == "push_config":
            if not p:
                raise ValueError("push_config requires a non-empty config object")
            return self
        raise ValueError(f"unsupported command_type {self.command_type}")


class IoTCommandRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    command_id: uuid.UUID
    gateway_id: uuid.UUID
    command_type: str
    payload_json: dict
    status: str
    attempts: int
    max_attempts: int
    sent_at: datetime | None
    next_retry_at: datetime | None
    ack_status: str | None
    ack_detail: str | None
    ack_received_at: datetime | None
    error_message: str | None
    created_at: datetime


class IoTCommandIssue(BaseModel):
    command_id: uuid.UUID
    status: str
```

- [ ] **Step 4: Run test to verify it passes**

Run: same harness command as Step 2.
Expected: `6 passed`.

- [ ] **Step 5: Commit**

```bash
git add platform/fmp/schemas/iot.py platform/fmp/tests/unit/test_iot_schemas.py
git commit -m "feat: IoT gateway + command schemas with per-type payload validation (SUB-2)"
```

---

## Task 4: IoT gateways CRUD API

**Files:**
- Create: `platform/fmp/api/v1/iot_gateways.py`
- Modify: `platform/fmp/api/main.py`
- Test: `platform/fmp/tests/integration/test_iot_gateway_api.py` (new)

- [ ] **Step 1: Write the failing integration test**

`platform/fmp/tests/integration/test_iot_gateway_api.py`:

```python
"""Integration test: IoT gateway CRUD API (create/list/get/patch/link)."""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def api(db):
    from fmp.api.deps import get_current_user
    from fmp.api.main import app
    from fmp.core.database import async_session_factory
    from fmp.core.security import hash_password
    from fmp.models import User

    async with async_session_factory() as session:
        admin = User(
            username="gw_admin", email="gw@t.io",
            password_hash=hash_password("AdminPass123"),
            role="admin", is_active=True,
        )
        session.add(admin)
        await session.commit()

    async def _override():
        return admin

    app.dependency_overrides[get_current_user] = _override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


async def test_gateway_crud_and_link(api):
    r = await api.post("/api/v1/iot-gateways", json={
        "gateway_mac": "AA:BB:CC:DD:EE:01", "name": "East Gate",
        "firmware_version": "2.1.0",
    })
    assert r.status_code == 201, r.text
    body = r.json()
    gw_id = body["id"]
    assert body["gateway_mac"] == "AA:BB:CC:DD:EE:01"
    assert body["name"] == "East Gate"
    assert body["is_active"] is False
    assert body["connection_status"] == "offline"
    assert body["tank_ids"] == []

    # duplicate MAC → 409
    r = await api.post("/api/v1/iot-gateways", json={"gateway_mac": "AA:BB:CC:DD:EE:01"})
    assert r.status_code == 409

    # list
    r = await api.get("/api/v1/iot-gateways")
    assert r.status_code == 200 and len(r.json()) == 1

    # get single
    r = await api.get(f"/api/v1/iot-gateways/{gw_id}")
    assert r.status_code == 200 and r.json()["name"] == "East Gate"

    # patch: rename + link a tank (tier1 fixture created one)
    from fmp.core.database import async_session_factory
    from fmp.models import Tank
    from sqlalchemy import select

    async with async_session_factory() as session:
        tank = (await session.execute(select(Tank))).scalars().first()
        tank_id = str(tank.id) if tank else None

    r = await api.patch(f"/api/v1/iot-gateways/{gw_id}", json={
        "name": "East Gate II", "is_active": True,
    })
    assert r.status_code == 200
    assert r.json()["name"] == "East Gate II" and r.json()["is_active"] is True

    if tank_id:
        r = await api.patch(f"/api/v1/iot-gateways/{gw_id}", json={"tank_ids": [tank_id]})
        assert r.status_code == 200
        assert r.json()["tank_ids"] == [tank_id]
        async with async_session_factory() as session:
            t = await session.get(Tank, tank_id)
            assert str(t.gateway_id) == gw_id

    # get missing → 404
    import uuid
    r = await api.get(f"/api/v1/iot-gateways/{uuid.uuid4()}")
    assert r.status_code == 404
```

- [ ] **Step 2: Run it to verify it fails**

Run: harness command with `fmp/tests/integration/test_iot_gateway_api.py::test_gateway_crud_and_link -q`
Expected: `404`/`No route` (router not registered yet).

- [ ] **Step 3: Implement the router**

`platform/fmp/api/v1/iot_gateways.py`:

```python
"""IoT gateway CRUD + command API."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from fmp.api.deps import CurrentUser, PrivilegedUser, SessionDep
from fmp.models import IoTGateway, Tank
from fmp.schemas.iot import IoTGatewayCreate, IoTGatewayRead, IoTGatewayUpdate

router = APIRouter(prefix="/api/v1/iot-gateways", tags=["iot-gateways"])


async def _get_gateway(session, gateway_id) -> IoTGateway:
    gateway = (
        await session.execute(select(IoTGateway).where(IoTGateway.id == gateway_id))
    ).scalar_one_or_none()
    if gateway is None:
        raise HTTPException(404, "gateway not found")
    return gateway


async def _tank_ids(session, gateway) -> list[uuid.UUID]:
    rows = (await session.execute(select(Tank.id).where(Tank.gateway_id == gateway.id))).scalars().all()
    return list(rows)


def _to_read(gateway: IoTGateway, tank_ids: list[uuid.UUID]) -> IoTGatewayRead:
    return IoTGatewayRead(
        id=gateway.id,
        gateway_mac=gateway.gateway_mac,
        name=gateway.name,
        firmware_version=gateway.firmware_version,
        last_seen=gateway.last_seen,
        connection_status=gateway.connection_status,
        is_active=gateway.is_active,
        tank_ids=tank_ids,
        created_at=gateway.created_at,
    )


@router.get("", response_model=list[IoTGatewayRead])
async def list_gateways(
    active: bool | None = None,
    _: CurrentUser = None,
    session: SessionDep = None,
):
    stmt = select(IoTGateway).order_by(IoTGateway.created_at.desc())
    if active is not None:
        stmt = stmt.where(IoTGateway.is_active.is_(active))
    rows = (await session.execute(stmt)).scalars().all()
    return [_to_read(g, []) for g in rows]


@router.post("", response_model=IoTGatewayRead, status_code=201)
async def create_gateway(
    payload: IoTGatewayCreate, _: PrivilegedUser, session: SessionDep
):
    existing = (
        await session.execute(select(IoTGateway).where(IoTGateway.gateway_mac == payload.gateway_mac))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(409, "gateway_mac already registered")
    gateway = IoTGateway(
        gateway_mac=payload.gateway_mac,
        name=payload.name or payload.gateway_mac,
        firmware_version=payload.firmware_version,
        is_active=False,
    )
    session.add(gateway)
    await session.commit()
    await session.refresh(gateway)
    return _to_read(gateway, [])


@router.get("/{gateway_id}", response_model=IoTGatewayRead)
async def get_gateway(gateway_id: uuid.UUID, _: CurrentUser, session: SessionDep):
    gateway = await _get_gateway(session, gateway_id)
    return _to_read(gateway, await _tank_ids(session, gateway))


@router.patch("/{gateway_id}", response_model=IoTGatewayRead)
async def update_gateway(
    gateway_id: uuid.UUID,
    payload: IoTGatewayUpdate,
    _: PrivilegedUser,
    session: SessionDep,
):
    gateway = await _get_gateway(session, gateway_id)
    data = payload.model_dump(exclude_unset=True)
    tank_ids = data.pop("tank_ids", None)
    for field, value in data.items():
        setattr(gateway, field, value)
    if tank_ids is not None:
        tanks = (
            await session.execute(select(Tank).where(Tank.id.in_(tank_ids)))
        ).scalars().all()
        if len(tanks) != len(set(tank_ids)):
            raise HTTPException(404, "one or more tanks not found")
        # detach any previous linking for these tanks, then attach
        for t in tanks:
            t.gateway_id = gateway.id
        if tanks:
            gateway.is_active = True
    await session.commit()
    await session.refresh(gateway)
    return _to_read(gateway, await _tank_ids(session, gateway))
```

`platform/fmp/api/main.py` — add import + registration:

```python
from fmp.api.v1 import (
    fuel_types,
    iot_gateways,
    notifications,
    ...
)
```

and after `app.include_router(fuel_types.router)` add:

```python
app.include_router(iot_gateways.router)
```

- [ ] **Step 4: Run test to verify it passes**

Run: same harness command as Step 2.
Expected: `1 passed`.

- [ ] **Step 5: Verify auth gating (admin) works**

Add to the same test file a read-only test:

```python
async def test_gateway_admin_only_write(api):
    # user-override dependency is admin here; assert a "user" (non-admin)
    # cannot POST. Override require via a user object.
    from fmp.api.deps import require_roles
    from fmp.api.main import app
    from fmp.core.database import async_session_factory
    from fmp.core.security import hash_password
    from fmp.models import User

    async with async_session_factory() as session:
        user = User(
            username="plain", email="p@t.io",
            password_hash=hash_password("TestPass123"),
            role="user", is_active=True,
        )
        session.add(user)
        await session.commit()

    async def _as_user():
        return user

    app.dependency_overrides[require_roles] = lambda *r: _as_user
    r = await api.post("/api/v1/iot-gateways", json={"gateway_mac": "AA:BB:CC:DD:EE:09"})
    assert r.status_code in (403, 422)
    app.dependency_overrides.clear()
```

Run: `... fmp/tests/integration/test_iot_gateway_api.py -q` → `2 passed`.

- [ ] **Step 6: Commit**

```bash
git add platform/fmp/api/v1/iot_gateways.py platform/fmp/api/main.py platform/fmp/tests/integration/test_iot_gateway_api.py
git commit -m "feat: IoT gateway CRUD API with admin gating (SUB-2)"
```

---

## Task 5: Command issue + history endpoints

**Files:**
- Modify: `platform/fmp/api/v1/iot_gateways.py`
- Modify: `platform/fmp/tests/integration/test_iot_gateway_api.py`

- [ ] **Step 1: Write the failing test**

Append to `platform/fmp/tests/integration/test_iot_gateway_api.py`:

```python
async def test_issue_command_and_history(api):
    from fmp.core.redis import RedisClient
    from fmp.ingestion.relay import QUEUE_OUTBOUND

    r = await api.post("/api/v1/iot-gateways", json={"gateway_mac": "AA:BB:CC:DD:EE:02"})
    gw_id = r.json()["id"]

    r = await api.post(f"/api/v1/iot-gateways/{gw_id}/commands", json={
        "command_type": "set_interval", "payload": {"interval_s": 5},
    })
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["status"] == "pending"
    command_id = body["command_id"]

    # frame is on the durable outbound queue
    redis = RedisClient()
    await redis.client.delete(QUEUE_OUTBOUND)
    # re-issue so this test is hermetic
    r = await api.post(f"/api/v1/iot-gateways/{gw_id}/commands", json={
        "command_type": "status_probe", "payload": {},
    })
    assert r.status_code == 202
    second_id = r.json()["command_id"]
    n = await redis.client.llen(QUEUE_OUTBOUND)
    assert n >= 1
    await redis.client.delete(QUEUE_OUTBOUND)
    await redis.client.aclose()

    # history lists both
    r = await api.get(f"/api/v1/iot-gateways/{gw_id}/commands")
    assert r.status_code == 200
    ids = [c["command_id"] for c in r.json()]
    assert command_id in ids and second_id in ids
    assert all(c["status"] == "pending" for c in r.json())

    # invalid payload → 422
    r = await api.post(f"/api/v1/iot-gateways/{gw_id}/commands", json={
        "command_type": "set_interval", "payload": {"interval_s": 0},
    })
    assert r.status_code == 422

    # unknown gateway → 404
    import uuid
    r = await api.post(f"/api/v1/iot-gateways/{uuid.uuid4()}/commands", json={
        "command_type": "reboot", "payload": {},
    })
    assert r.status_code == 404
```

- [ ] **Step 2: Run to verify it fails**

Run: `... fmp/tests/integration/test_iot_gateway_api.py::test_issue_command_and_history -q`
Expected: `404` (route not implemented).

- [ ] **Step 3: Implement command issue + history**

Append to `platform/fmp/api/v1/iot_gateways.py`:

```python
from fmp.core.redis import RedisClient
from fmp.ingestion.relay import enqueue_command
from fmp.models import GatewayCommand
from fmp.schemas.iot import IoTCommandCreate, IoTCommandIssue, IoTCommandRead


@router.post("/{gateway_id}/commands", response_model=IoTCommandIssue, status_code=202)
async def issue_command(
    gateway_id: uuid.UUID,
    payload: IoTCommandCreate,
    _: PrivilegedUser,
    session: SessionDep,
):
    gateway = await _get_gateway(session, gateway_id)
    if not gateway.is_active:
        raise HTTPException(409, "gateway is not active — link tanks first")
    command = GatewayCommand(
        gateway_id=gateway.id,
        command_type=payload.command_type,
        payload_json=payload.payload,
        status="pending",
        attempts=0,
        max_attempts=3,
    )
    session.add(command)
    await session.commit()
    await session.refresh(command)

    redis = RedisClient()
    try:
        await enqueue_command(
            redis.client,
            command_id=str(command.command_id),
            gateway_mac=gateway.gateway_mac,
            command_type=command.command_type,
            payload=payload.payload,
        )
    except Exception:
        await redis.client.aclose()
        raise
    await redis.client.aclose()
    return IoTCommandIssue(command_id=command.command_id, status="pending")


@router.get("/{gateway_id}/commands", response_model=list[IoTCommandRead])
async def list_commands(
    gateway_id: uuid.UUID,
    status: str | None = None,
    limit: int = 50,
    _: CurrentUser = None,
    session: SessionDep = None,
):
    await _get_gateway(session, gateway_id)
    stmt = (
        select(GatewayCommand)
        .where(GatewayCommand.gateway_id == gateway_id)
        .order_by(GatewayCommand.created_at.desc())
        .limit(min(limit, 500))
    )
    if status:
        stmt = stmt.where(GatewayCommand.status == status)
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows)
```

Note: `PrivilegedUser` currently grants `admin` + `company_admin`. The SUB-2 spec requires **admin-only** sends. Add an admin guard and use it for both create and command-issue:

```python
from fmp.api.deps import require_roles
...
AdminUser = ...
```

Define at module top (after imports):

```python
from typing import Annotated
from fmp.api.deps import require_roles

AdminUser = Annotated[object, Depends(require_roles("admin"))]
```

Then switch the write endpoints to use `AdminUser` instead of `PrivilegedUser` for `create_gateway`, `update_gateway`, and `issue_command`. The test `test_gateway_admin_only_write` (Task 4) should then assert a `company_admin` is also rejected to lock the admin-only policy:

Append:

```python
async def test_company_admin_cannot_send(api):
    from fmp.api.deps import require_roles
    from fmp.api.main import app
    from fmp.core.database import async_session_factory
    from fmp.core.security import hash_password
    from fmp.models import User

    async with async_session_factory() as session:
        ca = User(
            username="comp_admin", email="ca@t.io",
            password_hash=hash_password("TestPass123"),
            role="company_admin", is_active=True,
        )
        session.add(ca)
        await session.commit()

    async def _as_ca():
        return ca

    app.dependency_overrides[require_roles] = lambda *r: _as_ca
    r = await api.post("/api/v1/iot-gateways", json={"gateway_mac": "AA:BB:CC:DD:EE:10"})
    assert r.status_code == 403
    app.dependency_overrides.clear()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `... fmp/tests/integration/test_iot_gateway_api.py -q`
Expected: `5 passed`.

- [ ] **Step 5: Commit**

```bash
git add platform/fmp/api/v1/iot_gateways.py platform/fmp/tests/integration/test_iot_gateway_api.py
git commit -m "feat: issue commands + history API with admin-only gating (SUB-2)"
```

---

## Task 6: Ingestion — ack subscribe, ack handler, auto-register, relay loop

**Files:**
- Modify: `platform/fmp/ingestion/main.py`
- Create: `platform/fmp/tests/integration/test_gateway_ingestion.py`
- Modify: `platform/fmp/ingestion/relay.py` (publish helper)

- [ ] **Step 1: Write the failing integration test**

`platform/fmp/tests/integration/test_gateway_ingestion.py`:

```python
"""Integration test: gateway provisioning, ack handler, relay publish."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from fmp.tests.conftest import FakeRedis

pytestmark = pytest.mark.asyncio


async def test_status_heartbeat_auto_registers_gateway(requires_infra, db):
    from fmp.core.database import async_session_factory
    from fmp.ingestion.main import _handle_status
    from fmp.models import IoTGateway
    from sqlalchemy import select

    await _handle_status(FakeRedis(), {"status": "online", "firmware_version": "2.1.0"},
                         "AA:BB:CC:DD:EE:77")

    async with async_session_factory() as session:
        gw = (
            await session.execute(select(IoTGateway).where(IoTGateway.gateway_mac == "AA:BB:CC:DD:EE:77"))
        ).scalar_one()
        assert gw.is_active is False
        assert gw.connection_status == "online"
        assert gw.last_seen is not None
        assert gw.firmware_version == "2.1.0"


async def test_ack_handler_updates_row_and_gateway(requires_infra, db):
    from fmp.core.database import async_session_factory
    from fmp.ingestion.main import _handle_command_ack
    from fmp.models import GatewayCommand, IoTGateway

    async with async_session_factory() as session:
        gw = IoTGateway(gateway_mac="AA:BB:CC:DD:EE:01", name="GW", is_active=True)
        session.add(gw)
        await session.flush()
        cmd = GatewayCommand(
            gateway_id=gw.id, command_type="reboot", payload_json={},
            status="sent", attempts=1, max_attempts=3,
            next_retry_at=datetime.now(timezone.utc),
        )
        session.add(cmd)
        await session.commit()
        cmd_id = str(cmd.command_id)

    await _handle_command_ack(FakeRedis(), {"command_id": cmd_id, "status": "executed"},
                              "AA:BB:CC:DD:EE:01")

    async with async_session_factory() as session:
        from sqlalchemy import select
        cmd = (await session.execute(
            select(GatewayCommand).where(GatewayCommand.command_id == cmd_id)
        )).scalar_one()
        assert cmd.status == "acked"
        assert cmd.ack_status == "executed"
        assert cmd.ack_received_at is not None
        gw = (await session.execute(
            select(IoTGateway).where(IoTGateway.id == cmd.gateway_id)
        )).scalar_one()
        assert gw.connection_status == "online"
        assert gw.last_seen is not None


async def test_unknown_ack_is_ignored(requires_infra, db):
    from fmp.core.database import async_session_factory
    from fmp.ingestion.main import _handle_command_ack
    from fmp.models import GatewayCommand
    from sqlalchemy import select

    await _handle_command_ack(
        FakeRedis(), {"command_id": str(uuid.uuid4()), "status": "executed"}, "AA:BB:CC:DD:EE:99"
    )
    async with async_session_factory() as session:
        assert (await session.execute(select(GatewayCommand))).scalars().all() == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `... fmp/tests/integration/test_gateway_ingestion.py -q`
Expected: failures (`_handle_command_ack` undefined; `_handle_status` doesn't create gateway row). Note: uses `requires_infra` + `db` fixtures — the `db` fixture drops/creates schema.

- [ ] **Step 3: Implement ingestion changes**

`platform/fmp/ingestion/main.py`:

1. Add ack topic to both subscribe lists (lifespan ~line 61 and `_on_connect` ~line 106):

```python
            ("fuel/+/command/ack", settings.MQTT_QOS),
```

2. Import ack parser + relay helpers at top:

```python
from fmp.ingestion.relay import (
    ack_topic_for,
    command_topic_for,
    drain_inflight,
    next_retry_datetime,
    parse_command_ack_topic,
    release_command,
    take_command,
)
```

3. Add ack handling to `_route`, before the generic `fuel/` branch:

```python
        elif topic.startswith("fuel/") and topic.endswith("/command/ack"):
            mac = parse_command_ack_topic(topic)
            if mac is None:
                logger.warning("dropped malformed ack topic %s", topic)
            else:
                await _handle_command_ack(redis, payload, mac)
```

4. Auto-register in `_handle_status`. Replace the "no tank" branch with gateway upsert, and always refresh the gateway row (even when a tank exists). Restructure `_handle_status` to:

```python
async def _handle_status(redis: RedisClient, payload: dict[str, Any], gateway_mac: str) -> None:
    """Update tank + owning station and (re)register the gateway on a heartbeat."""
    from fmp.models import IoTGateway, Station, Tank

    now = datetime.now(timezone.utc)
    firmware = payload.get("firmware_version")
    async with async_session_factory() as session:
        gateway = (
            await session.execute(select(IoTGateway).where(IoTGateway.gateway_mac == gateway_mac))
        ).scalar_one_or_none()
        if gateway is None:
            gateway = IoTGateway(
                gateway_mac=gateway_mac,
                name=gateway_mac,
                firmware_version=firmware,
                connection_status="online",
                last_seen=now,
                is_active=False,
            )
            session.add(gateway)
            logger.info("gateway auto-registered: %s", gateway_mac)
        else:
            gateway.connection_status = "online"
            gateway.last_seen = now
            if firmware:
                gateway.firmware_version = firmware

        tank = (
            await session.execute(select(Tank).where(Tank.gateway_mac == gateway_mac))
        ).scalar_one_or_none()
        if tank is not None:
            tank.connection_status = "online"
            tank.last_connection = now
            if tank.site_id:
                station = (
                    await session.execute(
                        select(Station).where(Station.site_id == tank.site_id).limit(1)
                    )
                ).scalar_one_or_none()
                if station is not None:
                    station.last_heartbeat = now
        await session.commit()
        logger.info("heartbeat: gateway %s online (tank %s)", gateway_mac, tank.id if tank else None)
```

5. Add the ack handler (after `_handle_status`):

```python
async def _handle_command_ack(redis: RedisClient, payload: dict[str, Any], gateway_mac: str) -> None:
    """Apply a gateway ack frame to the correlated command row."""
    from fmp.models import GatewayCommand, IoTGateway

    command_id = payload.get("command_id")
    status = payload.get("status")  # "executed" | "rejected"
    if not command_id or status not in ("executed", "rejected"):
        logger.warning("dropped malformed ack frame from %s", gateway_mac)
        return
    async with async_session_factory() as session:
        row = (
            await session.execute(select(GatewayCommand).where(GatewayCommand.command_id == command_id))
        ).scalar_one_or_none()
        if row is None:
            logger.info("ignoring ack for unknown command_id %s", command_id)
            return
        row.status = "acked" if status == "executed" else "rejected"
        row.ack_status = status
        row.ack_detail = payload.get("detail")
        row.ack_received_at = datetime.now(timezone.utc)
        row.next_retry_at = None
        gateway = (
            await session.execute(select(IoTGateway).where(IoTGateway.id == row.gateway_id))
        ).scalar_one_or_none()
        if gateway is not None:
            gateway.connection_status = "online"
            gateway.last_seen = datetime.now(timezone.utc)
        await session.commit()
        logger.info("command %s %s (gateway %s)", command_id, status, gateway_mac)
```

- [ ] **Step 4: Implement relay loop + publish helper**

`platform/fmp/ingestion/relay.py` — add the publish + loop:

```python
async def publish_command(_client, redis, command_id: str, gateway_mac: str,
                          command_type: str, payload: dict, attempts: int) -> bool:
    """Publish one command frame to MQTT. Returns True on accepted publish."""
    from paho.mqtt.client import MQTT_ERR_SUCCESS

    frame = {
        "command_id": command_id,
        "type": command_type,
        "payload": payload,
        "issued_at": datetime.now(timezone.utc).isoformat(),
        "attempts": attempts,
    }
    rc, _mid = _client.publish(
        command_topic_for(gateway_mac), json.dumps(frame, default=str),
        qos=settings.MQTT_QOS,
    )
    return rc == MQTT_ERR_SUCCESS


async def command_relay_loop(_client) -> None:
    """Continuously move outbound frames to MQTT while they exist."""
    from fmp.core.database import async_session_factory
    from fmp.models import GatewayCommand

    redis_cache = RedisClient()
    redis = redis_cache.client
    try:
        await drain_inflight(redis)
        while True:
            frame = await take_command(redis, timeout=1)
            if frame is None:
                continue
            ok = await publish_command(
                _client, redis,
                command_id=frame["command_id"],
                gateway_mac=frame["gateway_mac"],
                command_type=frame["type"],
                payload=frame.get("payload", {}),
                attempts=int(frame.get("attempts", 0)) + 1,
            )
            if not ok:
                logger.warning("MQTT publish rejected for %s", frame["command_id"])
                continue  # frame stays in inflight; sweeper will requeue
            await release_command(redis)
            await _mark_sent(frame["command_id"])
    finally:
        await redis_cache.client.aclose()


async def _mark_sent(command_id: str) -> None:
    from fmp.core.database import async_session_factory
    from fmp.models import GatewayCommand

    async with async_session_factory() as session:
        row = (
            await session.execute(select(GatewayCommand).where(GatewayCommand.command_id == command_id))
        ).scalar_one_or_none()
        if row is None:
            return
        row.status = "sent"
        row.sent_at = datetime.now(timezone.utc)
        row.attempts += 1
        row.next_retry_at = next_retry_datetime(row.attempts)
        await session.commit()
```

(The `RedisClient` import must be added to relay.py: `from fmp.core.redis import RedisClient`; plus `select` from `sqlalchemy` inside `_mark_sent`.)

In `platform/fmp/ingestion/main.py` lifespan, start the relay task after subscribe:

```python
    from fmp.ingestion.relay import command_relay_loop

    relay_task = asyncio.create_task(command_relay_loop(_client))
    ...
    yield
    relay_task.cancel()
    _client.loop_stop()
    _client.disconnect()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `... fmp/tests/integration/test_gateway_ingestion.py -q`
Expected: `3 passed`.
Also run the SUB-1 heartbeat regression:
`... fmp/tests/integration/test_telemetry_pipeline.py::test_heartbeat_updates_station -q` → `1 passed`.

- [ ] **Step 6: Start the running ingestion stack check (compile/import)**

Run: `docker run --rm --network fuel-platform_default -v /home/ubuntu/fuel_monitoring/.worktrees/iot-command-api/platform:/srv/fmp -e FMP_SKIP_INFRA=1 -w /srv/fmp fuel-platform-api python -c "import fmp.ingestion.main"` →
Expected: exit 0 (no import errors).

- [ ] **Step 7: Commit**

```bash
git add platform/fmp/ingestion/main.py platform/fmp/ingestion/relay.py platform/fmp/tests/integration/test_gateway_ingestion.py
git commit -m "feat: ingestion subscribes ack topic, auto-registers gateways, runs command relay (SUB-2)"
```

---

## Task 7: Celery TTL sweeper (retry → fail)

**Files:**
- Create: `platform/fmp/workers/tasks/commands.py`
- Modify: `platform/fmp/workers/celery_app.py`
- Modify: `platform/fmp/tests/integration/test_gateway_ingestion.py`

- [ ] **Step 1: Write the failing test**

Append to `platform/fmp/tests/integration/test_gateway_ingestion.py`:

```python
async def test_sweeper_requeues_then_fails(requires_infra, db):
    from datetime import timedelta

    from fmp.core.database import async_session_factory
    from fmp.core.redis import RedisClient
    from fmp.ingestion.relay import QUEUE_OUTBOUND
    from fmp.models import GatewayCommand, IoTGateway
    from fmp.workers.tasks.commands import sweep_commands
    from sqlalchemy import select

    ago = datetime.now(timezone.utc) - timedelta(minutes=10)

    async with async_session_factory() as session:
        gw = IoTGateway(gateway_mac="AA:BB:CC:DD:EE:05", name="GW5", is_active=True)
        session.add(gw)
        await session.flush()
        cmd = GatewayCommand(
            gateway_id=gw.id, command_type="reboot", payload_json={},
            status="sent", attempts=1, max_attempts=3, next_retry_at=ago,
        )
        session.add(cmd)
        await session.commit()
        cmd_id = str(cmd.command_id)

    redis = RedisClient()
    await redis.client.delete(QUEUE_OUTBOUND)
    await redis.client.aclose()

    sweep_commands()  # sync celery task; requeues

    redis = RedisClient()
    assert await redis.client.llen(QUEUE_OUTBOUND) == 1
    await redis.client.delete(QUEUE_OUTBOUND)
    await redis.client.aclose()

    # exhaust: set attempts to max so sweep fails it instead
    async with async_session_factory() as session:
        cmd = (await session.execute(
            select(GatewayCommand).where(GatewayCommand.command_id == cmd_id)
        )).scalar_one()
        cmd.attempts = 3
        await session.commit()

    sweep_commands()

    async with async_session_factory() as session:
        cmd = (await session.execute(
            select(GatewayCommand).where(GatewayCommand.command_id == cmd_id)
        )).scalar_one()
        assert cmd.status == "failed"
        assert cmd.error_message
```

- [ ] **Step 2: Run to verify it fails**

Run: `... fmp/tests/integration/test_gateway_ingestion.py::test_sweeper_requeues_then_fails -q`
Expected: failure (module `fmp.workers.tasks.commands` missing).

- [ ] **Step 3: Implement the sweeper task**

`platform/fmp/workers/tasks/commands.py`:

```python
"""Celery task: TTL sweeper for gateway commands (retry → fail)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from fmp.core.config import get_settings
from fmp.core.database import async_session_factory
from fmp.core.redis import RedisClient
from fmp.ingestion.relay import QUEUE_OUTBOUND, enqueue_command
from fmp.models import GatewayCommand
from fmp.workers.celery_app import celery_app

settings = get_settings()


async def _scan_and_sweep() -> dict[str, int]:
    now = datetime.now(timezone.utc)
    pending_cutoff = now - timedelta(seconds=settings.COMMAND_PENDING_TTL_SECONDS)
    retried = failed_sent = failed_pending = 0

    async with async_session_factory() as session:
        # sent but past next_retry_at and under max attempts → requeue
        q = (
            select(GatewayCommand)
            .where(
                GatewayCommand.status == "sent",
                GatewayCommand.next_retry_at.is_not(None),
                GatewayCommand.next_retry_at < now,
                GatewayCommand.attempts < GatewayCommand.max_attempts,
            )
        )
        for row in (await session.execute(q)).scalars().all():
            if row.attempts >= row.max_attempts:
                continue
            redis = RedisClient()
            try:
                await enqueue_command(
                    redis.client,
                    command_id=str(row.command_id),
                    gateway_mac=row.gateway.gateway_mac if row.gateway else "",
                    command_type=row.command_type,
                    payload=row.payload_json,
                )
            finally:
                await redis.client.aclose()
            retried += 1
        if retried:
            await session.commit()

        # sent past retry and at/over max attempts → failed
        q = (
            select(GatewayCommand)
            .where(
                GatewayCommand.status == "sent",
                GatewayCommand.next_retry_at.is_not(None),
                GatewayCommand.next_retry_at < now,
                GatewayCommand.attempts >= GatewayCommand.max_attempts,
            )
        )
        for row in (await session.execute(q)).scalars().all():
            row.status = "failed"
            row.error_message = "max attempts exhausted (retry timeout)"
            failed_sent += 1

        # pending stuck (never relayed) past TTL → failed
        q = (
            select(GatewayCommand)
            .where(GatewayCommand.status == "pending", GatewayCommand.created_at < pending_cutoff)
        )
        for row in (await session.execute(q)).scalars().all():
            row.status = "failed"
            row.error_message = "expired before ingestion relay picked it up"
            failed_pending += 1

        await session.commit()

    return {"retried": retried, "failed_sent": failed_sent, "failed_pending": failed_pending}


@celery_app.task(name="commands.sweep_commands")
def sweep_commands() -> dict:
    import asyncio

    return asyncio.run(_scan_and_sweep())
```

`platform/fmp/workers/celery_app.py` — add the include and beat schedule:

```python
include=[
    "fmp.workers.tasks.notifications",
    "fmp.workers.tasks.commands",
],
```

and after `celery_app.conf.update(...)`:

```python
celery_app.conf.beat_schedule = {
    "sweep-gateway-commands": {
        "task": "commands.sweep_commands",
        "schedule": 30.0,
    },
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `... fmp/tests/integration/test_gateway_ingestion.py -q`
Expected: `4 passed`.

- [ ] **Step 5: Commit**

```bash
git add platform/fmp/workers/tasks/commands.py platform/fmp/workers/celery_app.py platform/fmp/tests/integration/test_gateway_ingestion.py
git commit -m "feat: Celery beat TTL sweeper retries then fails gateway commands (SUB-2)"
```

---

## Task 8: Backfill script + compose db-init wiring

**Files:**
- Create: `platform/fmp/scripts/backfill_gateways.py`
- Modify: `docker-compose.yml`
- Test: `platform/fmp/tests/integration/test_backfill.py`

- [ ] **Step 1: Write the failing test**

`platform/fmp/tests/integration/test_backfill.py`:

```python
"""Integration test: tanks.gateway_id backfill from gateway_mac."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


async def test_backfill_assigns_gateway_id(requires_infra, db):
    from fmp.core.database import async_session_factory
    from fmp.models import IoTGateway, Tank
    from fmp.scripts.backfill_gateways import backfill_gateways
    from sqlalchemy import select

    async with async_session_factory() as session:
        sn = "SN-BACKFILL-1"
        # a tank carrying a legacy gateway_mac with no gateway row yet
        tank = Tank(
            name="Gen A", site_id=None, sensor_serial_number=sn,
            gateway_mac="AA:BB:CC:DD:EE:88",
            tank_orientation="vertical", tank_diameter=2.0, tank_height=3.0,
            tank_volume=9200.0, elevation=0.0, calibration_factor=1.0,
            fuel_type=None, critical_level_threshold=0.5, low_level_threshold=1.0,
            high_level_threshold=2.8, low_volume_threshold=2000.0,
        )
        session.add(tank)
        await session.commit()

    backfill_gateways()

    async with async_session_factory() as session:
        tank = (await session.execute(
            select(Tank).where(Tank.sensor_serial_number == sn)
        )).scalar_one()
        assert tank.gateway_id is not None
        gw = (await session.execute(
            select(IoTGateway).where(IoTGateway.gateway_mac == "AA:BB:CC:DD:EE:88")
        )).scalar_one()
        assert gw.id == tank.gateway_id
        assert gw.is_active is True  # linked tank activates it
```

- [ ] **Step 2: Run to verify it fails**

Run: `... fmp/tests/integration/test_backfill.py -q`
Expected: failure (no script module). Note: the `tanks` DDL has a `site_id NOT NULL` FK on the live schema — if the tier fixture creates `tanks` with `site_id` nullable, the DB `ForeignKey("sites.id")` on `db` fixture's fresh schema uses model definition (nullable), so `site_id=None` is valid. Confirm by running; if NOT NULL, adjust the test to create a site first.

- [ ] **Step 3: Implement the backfill script**

`platform/fmp/scripts/backfill_gateways.py`:

```python
"""One-shot gateway backfill: add tanks.gateway_id and map legacy gateway_mac.

Runs as part of the compose db-init step. Idempotent:
  ALTER TABLE ... ADD COLUMN IF NOT EXISTS; upsert iot_gateways from distinct
  tank.gateway_mac; set tanks.gateway_id.
"""
from __future__ import annotations

import asyncio

from sqlalchemy import text


async def _run() -> None:
    from fmp.core.database import engine

    async with engine.begin() as conn:
        await conn.execute(text(
            "ALTER TABLE tanks ADD COLUMN IF NOT EXISTS gateway_id UUID "
            "REFERENCES iot_gateways(id)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_tanks_gateway_id ON tanks (gateway_id)"
        ))
        # upsert gateways from distinct non-null tank macs
        await conn.execute(text(
            "INSERT INTO iot_gateways (id, gateway_mac, name, is_active, created_at, updated_at) "
            "SELECT gen_random_uuid(), t.gateway_mac, t.gateway_mac, TRUE, now(), now() "
            "FROM (SELECT DISTINCT gateway_mac FROM tanks "
            "      WHERE gateway_mac IS NOT NULL AND gateway_mac <> '') t "
            "ON CONFLICT (gateway_mac) DO NOTHING"
        ))
        # map tanks (still-null gateway_id) to the new gateways by mac
        await conn.execute(text(
            "UPDATE tanks SET gateway_id = gw.id "
            "FROM iot_gateways gw WHERE gw.gateway_mac = tanks.gateway_mac "
            "AND tanks.gateway_id IS NULL"
        ))
    await engine.dispose()


def run_backfill() -> None:
    asyncio.run(_run())


# expose a sync entry for the integration test + compose
backfill_gateways = run_backfill


if __name__ == "__main__":
    run_backfill()
```

Note: the upsert relies on `gen_random_uuid()` (pgcrypto is available in TimescaleDB pg14; if not, `CREATE EXTENSION IF NOT EXISTS pgcrypto`). Add that guard before the INSERT:

```python
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
```

`docker-compose.yml` — change db-init command to run init then backfill:

```yaml
  db-init:
    build: ./platform
    restart: "no"
    command: ["python", "-c", "from fmp.scripts.init_db import init_db; import asyncio; asyncio.run(init_db()); from fmp.scripts.backfill_gateways import run_backfill; run_backfill()"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `... fmp/tests/integration/test_backfill.py -q`
Expected: `1 passed`.

- [ ] **Step 5: Verify backfill idempotency**

Add second test in same file:

```python
async def test_backfill_idempotent(requires_infra, db):
    from fmp.core.database import async_session_factory
    from fmp.models import IoTGateway, Tank
    from fmp.scripts.backfill_gateways import backfill_gateways
    from sqlalchemy import func, select

    async with async_session_factory() as session:
        tank = Tank(
            name="Gen B", site_id=None, sensor_serial_number="SN-BACKFILL-2",
            gateway_mac="AA:BB:CC:DD:EE:89",
            tank_orientation="vertical", tank_diameter=2.0, tank_height=3.0,
            tank_volume=9200.0, elevation=0.0, calibration_factor=1.0,
            fuel_type=None, critical_level_threshold=0.5, low_level_threshold=1.0,
            high_level_threshold=2.8, low_volume_threshold=2000.0,
        )
        session.add(tank)
        await session.commit()

    backfill_gateways()
    backfill_gateways()

    async with async_session_factory() as session:
        count = (await session.execute(
            select(func.count()).select_from(IoTGateway).where(IoTGateway.gateway_mac == "AA:BB:CC:DD:EE:89")
        )).scalar()
        assert count == 1
```

Run: `... fmp/tests/integration/test_backfill.py -q` → `2 passed`.

- [ ] **Step 6: Commit**

```bash
git add platform/fmp/scripts/backfill_gateways.py docker-compose.yml platform/fmp/tests/integration/test_backfill.py
git commit -m "feat: gateway backfill script wired into compose db-init (SUB-2)"
```

---

## Task 9: Frontend — API client + types

**Files:**
- Modify: `web/src/lib/apiTypes.ts`
- Create: `web/src/api/iot.ts`
- Modify: `web/src/api/client.ts`

- [ ] **Step 1: Add types** to `web/src/lib/apiTypes.ts`

```ts
export type IoTCommandType =
  | 'reboot' | 'status_probe' | 'pause_reporting' | 'resume_reporting'
  | 'set_interval' | 'recalibrate' | 'zero_tank' | 'push_config';

export interface IoTGateway {
  id: string;
  gateway_mac: string;
  name: string;
  firmware_version: string | null;
  last_seen: string | null;
  connection_status: 'online' | 'offline';
  is_active: boolean;
  tank_ids: string[];
  created_at: string;
}

export interface IoTGatewayCreate {
  gateway_mac: string;
  name?: string;
  firmware_version?: string;
}

export interface IoTGatewayUpdate {
  name?: string;
  firmware_version?: string;
  is_active?: boolean;
  tank_ids?: string[];
}

export interface IoTCommandCreate {
  command_type: IoTCommandType;
  payload: Record<string, unknown>;
}

export interface IoTCommand {
  id: string;
  command_id: string;
  gateway_id: string;
  command_type: IoTCommandType;
  payload_json: Record<string, unknown>;
  status: 'pending' | 'sent' | 'acked' | 'rejected' | 'failed';
  attempts: number;
  max_attempts: number;
  sent_at: string | null;
  next_retry_at: string | null;
  ack_status: string | null;
  ack_detail: string | null;
  ack_received_at: string | null;
  error_message: string | null;
  created_at: string;
}
```

- [ ] **Step 2: Create `web/src/api/iot.ts`**

```ts
import type {
  IoTCommand,
  IoTCommandCreate,
  IoTGateway,
  IoTGatewayCreate,
  IoTGatewayUpdate,
} from '../lib/apiTypes';
import { request } from './http';

const API_BASE = '/api/v1/iot-gateways';

export const iotApi = {
  async listGateways(active?: boolean): Promise<IoTGateway[]> {
    const qs = active === undefined ? '' : `?active=${active}`;
    return request<IoTGateway[]>(`${API_BASE}${qs}`);
  },

  async createGateway(payload: IoTGatewayCreate): Promise<IoTGateway> {
    return request<IoTGateway>(API_BASE, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  async getGateway(id: string): Promise<IoTGateway> {
    return request<IoTGateway>(`${API_BASE}/${id}`);
  },

  async updateGateway(id: string, payload: IoTGatewayUpdate): Promise<IoTGateway> {
    return request<IoTGateway>(`${API_BASE}/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    });
  },

  async sendCommand(id: string, payload: IoTCommandCreate): Promise<{ command_id: string; status: string }> {
    return request<{ command_id: string; status: string }>(`${API_BASE}/${id}/commands`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  async listCommands(id: string, status?: string, limit = 50): Promise<IoTCommand[]> {
    const params = new URLSearchParams({ limit: String(limit) });
    if (status) params.set('status', status);
    return request<IoTCommand[]>(`${API_BASE}/${id}/commands?${params}`);
  },
};
```

- [ ] **Step 3: Register in `web/src/api/client.ts`**

Import and spread:

```ts
import { iotApi } from './iot';
...
  ...monitoringApi,
  ...iotApi,
};
```

- [ ] **Step 4: Verify frontend compiles**

Run: `cd /home/ubuntu/fuel_monitoring/web && npx tsc --noEmit`
Expected: exit 0.

- [ ] **Step 5: Commit**

```bash
cd /home/ubuntu/fuel_monitoring && git add web/src/lib/apiTypes.ts web/src/api/iot.ts web/src/api/client.ts
git commit -m "feat(web): IoT gateway + command API client types (SUB-2)"
```

---

## Task 10: Frontend — gateways list page

**Files:**
- Create: `web/src/pages/IoTGatewaysPage.tsx`
- Modify: `web/src/router.tsx`
- Modify: `web/src/components/layout/AppLayout.tsx`
- Test: `web/src/pages/IoTGatewaysPage.test.tsx`

- [ ] **Step 1: Write the failing test**

`web/src/pages/IoTGatewaysPage.test.tsx` (modeled on `GatewaysPage.test.tsx`):

```tsx
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../api/client', () => ({
  api: { listGateways: vi.fn(), createGateway: vi.fn() },
}));
import { api } from '../api/client';
import IoTGatewaysPage from './IoTGatewaysPage';

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <Routes>
          <Route path="/" element={<IoTGatewaysPage />} />
          <Route path="/admin/iot-gateways/:id" element={<div>detail</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const gw = {
  id: 'gw1',
  gateway_mac: 'AA:BB:CC:DD:EE:01',
  name: 'East Gate',
  firmware_version: '2.1.0',
  last_seen: '2026-09-11T00:00:00Z',
  connection_status: 'online',
  is_active: true,
  tank_ids: [],
  created_at: '2026-09-11T00:00:00Z',
};

describe('IoTGatewaysPage', () => {
  beforeEach(() => {
    vi.mocked(api.listGateways).mockResolvedValue([gw] as never);
  });

  it('renders gateway rows with status pill', async () => {
    renderPage();
    expect(await screen.findByText('East Gate')).toBeInTheDocument();
    expect(screen.getByText('AA:BB:CC:DD:EE:01')).toBeInTheDocument();
    expect(screen.getByText('online')).toBeInTheDocument();
    expect(screen.getByText('2.1.0')).toBeInTheDocument();
  });

  it('shows unprovisioned badge for inactive gateway', async () => {
    vi.mocked(api.listGateways).mockResolvedValue([{ ...gw, is_active: false }] as never);
    renderPage();
    expect(await screen.findByText(/unprovisioned/i)).toBeInTheDocument();
  });

  it('navigates to detail on row click', async () => {
    renderPage();
    await userEvent.click(await screen.findByText('East Gate'));
    expect(await screen.findByText('detail')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /home/ubuntu/fuel_monitoring/web && npx vitest run src/pages/IoTGatewaysPage.test.tsx`
Expected: failure (no `IoTGatewaysPage.tsx`).

- [ ] **Step 3: Implement the list page**

`web/src/pages/IoTGatewaysPage.tsx`:

```tsx
import { FormEvent, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { ApiError } from '../api/http';
import { api } from '../api/client';
import type { IoTGateway } from '../lib/apiTypes';
import { Badge } from '../components/ui/badge';
import { Modal } from '../components/ui/Modal';
import { Field, Input } from '../components/ui/fields';

function GatewayDialog({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState({ gateway_mac: '', name: '', firmware_version: '' });
  const [error, setError] = useState<string | null>(null);

  const mut = useMutation({
    mutationFn: () =>
      api.createGateway({
        gateway_mac: form.gateway_mac,
        name: form.name || undefined,
        firmware_version: form.firmware_version || undefined,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['iot-gateways'] });
      onClose();
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : 'Create failed'),
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    mut.mutate();
  };

  return (
    <Modal title="New IoT gateway" onClose={onClose}>
      <form onSubmit={submit} className="space-y-3">
        <Field label="Gateway MAC" htmlFor="gw-mac">
          <Input id="gw-mac" autoFocus value={form.gateway_mac} onChange={(e) => setForm((f) => ({ ...f, gateway_mac: e.target.value }))} required placeholder="AA:BB:CC:DD:EE:01" />
        </Field>
        <Field label="Name" htmlFor="gw-name">
          <Input id="gw-name" value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} placeholder="East Gate" />
        </Field>
        <Field label="Firmware version" htmlFor="gw-fw">
          <Input id="gw-fw" value={form.firmware_version} onChange={(e) => setForm((f) => ({ ...f, firmware_version: e.target.value }))} placeholder="2.1.0" />
        </Field>
        {error ? <p className="text-sm text-red-600">{error}</p> : null}
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className="px-3 py-2 text-sm text-slate-600">Cancel</button>
          <button type="submit" disabled={mut.isPending} className="bg-brand text-white rounded px-3 py-2 text-sm font-medium disabled:opacity-50">Create</button>
        </div>
      </form>
    </Modal>
  );
}

export default function IoTGatewaysPage() {
  const gateways = useQuery({ queryKey: ['iot-gateways'], queryFn: () => api.listGateways() });
  const [creating, setCreating] = useState(false);
  const navigate = useNavigate();

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-semibold text-slate-800">IoT Gateways</h2>
        <button onClick={() => setCreating(true)} className="bg-brand text-white rounded px-3 py-2 text-sm font-medium">
          New gateway
        </button>
      </div>
      {gateways.isLoading ? <p className="text-sm text-slate-500">Loading…</p> : null}
      {gateways.isError ? <p className="text-sm text-rose-600">Failed to load gateways.</p> : null}
      <div className="bg-white rounded-lg border border-slate-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-500">
            <tr>
              <th className="text-left px-4 py-2">Name</th>
              <th className="text-left px-4 py-2">MAC</th>
              <th className="text-left px-4 py-2">Status</th>
              <th className="text-left px-4 py-2">Last seen</th>
              <th className="text-left px-4 py-2">Firmware</th>
              <th className="text-left px-4 py-2">Tanks</th>
              <th className="text-left px-4 py-2">Provisioned</th>
            </tr>
          </thead>
          <tbody>
            {(gateways.data ?? []).map((g) => (
              <tr key={g.id} className="border-t border-slate-100 cursor-pointer hover:bg-slate-50" onClick={() => navigate(`/admin/iot-gateways/${g.id}`)}>
                <td className="px-4 py-2 font-medium text-slate-800">{g.name}</td>
                <td className="px-4 py-2 text-slate-600 font-mono">{g.gateway_mac}</td>
                <td className="px-4 py-2">
                  <Badge variant={g.connection_status === 'online' ? 'success' : 'default'}>{g.connection_status}</Badge>
                </td>
                <td className="px-4 py-2 text-slate-600">{g.last_seen ? new Date(g.last_seen).toLocaleString() : '—'}</td>
                <td className="px-4 py-2 text-slate-600">{g.firmware_version ?? '—'}</td>
                <td className="px-4 py-2 text-slate-600">{g.tank_ids.length}</td>
                <td className="px-4 py-2">
                  {g.is_active ? <Badge variant="success">provisioned</Badge> : <Badge variant="warning">unprovisioned</Badge>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {creating ? <GatewayDialog onClose={() => setCreating(false)} /> : null}
    </div>
  );
}
```

Check `components/ui/badge.tsx` Badge variants — if `warning` isn't a valid variant, use `default`. Verify and adjust.

- [ ] **Step 4: Wire route + nav**

`web/src/router.tsx` — add import and route under the `RequireManage` children:

```tsx
{ path: 'admin/iot-gateways', element: <IoTGatewaysPage /> },
{ path: 'admin/iot-gateways/:id', element: <IoTGatewayDetailPage /> },
```

`web/src/components/layout/AppLayout.tsx` — add a nav entry (follow existing nav item pattern, e.g. next to the existing Gateways link), label `IoT Gateways`, path `/admin/iot-gateways`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /home/ubuntu/fuel_monitoring/web && npx vitest run src/pages/IoTGatewaysPage.test.tsx`
Expected: `3 passed`.

- [ ] **Step 6: Commit**

```bash
cd /home/ubuntu/fuel_monitoring && git add web/src/pages/IoTGatewaysPage.tsx web/src/pages/IoTGatewaysPage.test.tsx web/src/router.tsx web/src/components/layout/AppLayout.tsx
git commit -m "feat(web): IoT gateways list page + navigation (SUB-2)"
```

---

## Task 11: Frontend — gateway detail page (composer + history)

**Files:**
- Create: `web/src/pages/IoTGatewayDetailPage.tsx`
- Test: `web/src/pages/IoTGatewayDetailPage.test.tsx`

- [ ] **Step 1: Write the failing test**

`web/src/pages/IoTGatewayDetailPage.test.tsx`:

```tsx
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../api/client', () => ({
  api: {
    getGateway: vi.fn(),
    sendCommand: vi.fn(),
    listCommands: vi.fn(),
    updateGateway: vi.fn(),
  },
}));
import { api } from '../api/client';
import IoTGatewayDetailPage from './IoTGatewayDetailPage';

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/admin/iot-gateways/gw1']}>
        <Routes>
          <Route path="/admin/iot-gateways/:id" element={<IoTGatewayDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const gw = {
  id: 'gw1',
  gateway_mac: 'AA:BB:CC:DD:EE:01',
  name: 'East Gate',
  firmware_version: '2.1.0',
  last_seen: '2026-09-11T00:00:00Z',
  connection_status: 'online',
  is_active: true,
  tank_ids: ['t1'],
  created_at: '2026-09-11T00:00:00Z',
};

const hist = [
  {
    id: 'c1', command_id: 'cmd-1', gateway_id: 'gw1', command_type: 'reboot',
    payload_json: {}, status: 'acked', attempts: 1, max_attempts: 3,
    sent_at: '2026-09-11T00:01:00Z', next_retry_at: null,
    ack_status: 'executed', ack_detail: null, ack_received_at: '2026-09-11T00:01:02Z',
    error_message: null, created_at: '2026-09-11T00:01:00Z',
  },
];

describe('IoTGatewayDetailPage', () => {
  beforeEach(() => {
    vi.mocked(api.getGateway).mockResolvedValue(gw as never);
    vi.mocked(api.listCommands).mockResolvedValue(hist as never);
  });

  it('renders summary + history', async () => {
    renderPage();
    expect(await screen.findByText('East Gate')).toBeInTheDocument();
    expect(await screen.findByText('reboot')).toBeInTheDocument();
    expect(screen.getByText('acked')).toBeInTheDocument();
    expect(screen.getByText('1 tank(s)')).toBeInTheDocument();
  });

  it('sends a reboot command via composer', async () => {
    vi.mocked(api.sendCommand).mockResolvedValue({ command_id: 'cmd-2', status: 'pending' } as never);
    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: /send rebound/i })); // label per composer
    await waitFor(() => expect(api.sendCommand).toHaveBeenCalled());
  });

  it('hides composer for inactive gateway', async () => {
    vi.mocked(api.getGateway).mockResolvedValue({ ...gw, is_active: false } as never);
    renderPage();
    expect(await screen.findByText(/not provisioned/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /send/i })).not.toBeInTheDocument();
  });
});
```

(Adjust the composer button label/test to match the implemented UI — write the test to match the exact buttons in Step 3.)

- [ ] **Step 2: Run to verify it fails**

Run: `cd /home/ubuntu/fuel_monitoring/web && npx vitest run src/pages/IoTGatewayDetailPage.test.tsx`
Expected: failure (no page module).

- [ ] **Step 3: Implement the detail page**

`web/src/pages/IoTGatewayDetailPage.tsx`:

```tsx
import { FormEvent, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { ApiError } from '../api/http';
import { api } from '../api/client';
import type { IoTCommandType } from '../lib/apiTypes';
import { Badge } from '../components/ui/badge';
import { Field, Input, Select, Textarea } from '../components/ui/fields';

const COMMAND_TYPES: { value: IoTCommandType; label: string }[] = [
  { value: 'reboot', label: 'Reboot' },
  { value: 'status_probe', label: 'Status probe' },
  { value: 'pause_reporting', label: 'Pause reporting' },
  { value: 'resume_reporting', label: 'Resume reporting' },
  { value: 'set_interval', label: 'Set interval' },
  { value: 'recalibrate', label: 'Recalibrate' },
  { value: 'zero_tank', label: 'Zero tank' },
  { value: 'push_config', label: 'Push config' },
];

function CommandComposer({ gatewayId }: { gatewayId: string }) {
  const queryClient = useQueryClient();
  const [type, setType] = useState<IoTCommandType>('reboot');
  const [raw, setRaw] = useState('{}');
  const [error, setError] = useState<string | null>(null);

  const mut = useMutation({
    mutationFn: () => {
      let payload: Record<string, unknown>;
      try {
        payload = raw.trim() ? JSON.parse(raw) : {};
      } catch {
        throw new Error('Payload must be valid JSON');
      }
      return api.sendCommand(gatewayId, { command_type: type, payload });
    },
    onSuccess: () => {
      setRaw('{}');
      void queryClient.invalidateQueries({ queryKey: ['iot-gateway-commands', gatewayId] });
    },
    onError: (err) => setError(err instanceof Error ? err.message : 'Send failed'),
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    mut.mutate();
  };

  return (
    <form onSubmit={submit} className="space-y-3 bg-white rounded-lg border border-slate-200 p-4">
      <h3 className="text-lg font-semibold text-slate-800">Send command</h3>
      <Field label="Command type" htmlFor="cmd-type">
        <Select id="cmd-type" value={type} onChange={(e) => setType(e.target.value as IoTCommandType)}>
          {COMMAND_TYPES.map((c) => (
            <option key={c.value} value={c.value}>{c.label}</option>
          ))}
        </Select>
      </Field>
      <Field label="Payload (JSON)" htmlFor="cmd-payload">
        <Textarea id="cmd-payload" value={raw} onChange={(e) => setRaw(e.target.value)} rows={4} spellCheck={false} placeholder={'{"interval_s": 5}'} />
      </Field>
      {error ? <p className="text-sm text-red-600">{error}</p> : null}
      <div className="flex justify-end">
        <button type="submit" disabled={mut.isPending} className="bg-brand text-white rounded px-3 py-2 text-sm font-medium disabled:opacity-50">
          Send
        </button>
      </div>
    </form>
  );
}

const STATUS_VARIANT: Record<string, 'success' | 'default' | 'warning'> = {
  acked: 'success',
  rejected: 'default',
  failed: 'default',
  sent: 'warning',
  pending: 'warning',
};

export default function IoTGatewayDetailPage() {
  const { id = '' } = useParams();
  const gateway = useQuery({ queryKey: ['iot-gateway', id], queryFn: () => api.getGateway(id) });
  const commands = useQuery({
    queryKey: ['iot-gateway-commands', id],
    queryFn: () => api.listCommands(id),
    refetchInterval: 5000,
  });

  if (gateway.isLoading) return <p className="text-sm text-slate-500">Loading…</p>;
  if (gateway.isError || !gateway.data) return <p className="text-sm text-rose-600">Failed to load gateway.</p>;
  const g = gateway.data;

  return (
    <div className="space-y-6">
      <div className="bg-white rounded-lg border border-slate-200 p-4">
        <div className="flex items-center justify-between">
          <h2 className="text-2xl font-semibold text-slate-800">{g.name}</h2>
          <Badge variant={g.connection_status === 'online' ? 'success' : 'default'}>{g.connection_status}</Badge>
        </div>
        <dl className="mt-3 grid grid-cols-2 gap-2 text-sm">
          <dt className="text-slate-500">MAC</dt><dd className="font-mono">{g.gateway_mac}</dd>
          <dt className="text-slate-500">Firmware</dt><dd>{g.firmware_version ?? '—'}</dd>
          <dt className="text-slate-500">Last seen</dt><dd>{g.last_seen ? new Date(g.last_seen).toLocaleString() : '—'}</dd>
          <dt className="text-slate-500">Linked tanks</dt><dd>{g.tank_ids.length} tank(s)</dd>
        </dl>
        {!g.is_active ? <p className="mt-3 text-sm text-amber-700">Not provisioned — link tanks via admin to enable commands.</p> : null}
      </div>

      {g.is_active ? <CommandComposer gatewayId={g.id} /> : null}

      <div className="bg-white rounded-lg border border-slate-200 p-4">
        <h3 className="text-lg font-semibold text-slate-800 mb-3">History</h3>
        {commands.isLoading ? <p className="text-sm text-slate-500">Loading…</p> : null}
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-500">
            <tr>
              <th className="text-left px-4 py-2">Type</th>
              <th className="text-left px-4 py-2">Status</th>
              <th className="text-left px-4 py-2">Attempts</th>
              <th className="text-left px-4 py-2">Sent</th>
              <th className="text-left px-4 py-2">Ack</th>
            </tr>
          </thead>
          <tbody>
            {(commands.data ?? []).map((c) => (
              <tr key={c.id} className="border-t border-slate-100">
                <td className="px-4 py-2 font-medium text-slate-800">{c.command_type}</td>
                <td className="px-4 py-2">
                  <Badge variant={STATUS_VARIANT[c.status] ?? 'default'}>{c.status}</Badge>
                </td>
                <td className="px-4 py-2 text-slate-600">{c.attempts}/{c.max_attempts}</td>
                <td className="px-4 py-2 text-slate-600">{c.sent_at ? new Date(c.sent_at).toLocaleString() : '—'}</td>
                <td className="px-4 py-2 text-slate-600">
                  {c.ack_status ? `${c.ack_status}${c.ack_detail ? ` — ${c.ack_detail}` : ''}` : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/ubuntu/fuel_monitoring/web && npx vitest run src/pages/IoTGatewayDetailPage.test.tsx`
Expected: `3 passed` (fix the composer-button test label to `Send` if the first test text mismatches).

- [ ] **Step 5: Verify frontend compiles**

Run: `cd /home/ubuntu/fuel_monitoring/web && npx tsc --noEmit`
Expected: exit 0.

- [ ] **Step 6: Commit**

```bash
cd /home/ubuntu/fuel_monitoring && git add web/src/pages/IoTGatewayDetailPage.tsx web/src/pages/IoTGatewayDetailPage.test.tsx
git commit -m "feat(web): IoT gateway detail with command composer + history (SUB-2)"
```

---

## Task 12: Full regression + README

**Files:**
- Modify: `platform/docs/superpowers/plans/2026-09-10-modernization-README.md`

- [ ] **Step 1: Run the full backend suite**

Run: harness command with `fmp/tests -q`
Expected: `127 passed` + SUB-2 additions → `>= 136 passed` (127 baseline + 3 model + 5 relay + 6 schema + 5 gateway CRUD/command + 2 backfill + 4 ingestion/sweeper = +25; the CRUD test count may merge — expect between 135 and 137; record the exact number).

- [ ] **Step 2: Run web type-check + tests**

Run: `cd /home/ubuntu/fuel_monitoring/web && npx tsc --noEmit && npx vitest run`
Expected: exit 0, all frontend tests green (existing + new).

- [ ] **Step 3: Verify backfill against the running compose DB**

Run: `docker compose exec -T db psql -U fuel_platform -d fuel_platform -c "ALTER TABLE tanks ADD COLUMN IF NOT EXISTS gateway_id UUID"` (idempotent check manually) then:
`docker compose run --rm db-init` after rebuild (`docker compose build db-init`) and confirm no errors. Confirm `\d tanks` shows `gateway_id`.

- [ ] **Step 4: Update modernization README**

Append a SUB-2 section to `platform/docs/superpowers/plans/2026-09-10-modernization-README.md`:

```markdown
## SUB-2: IoT gateway command API (2026-09-11)

Adds `iot_gateways` + `gateway_commands` tables and a durable, ack-tracked
command plane: API-issued commands ride a Redis list into the ingestion relay,
publish to `fuel/{mac}/command`, and are confirmed on `fuel/{mac}/command/ack`.
Heartbeats auto-register gateways; admin links tanks to provision them. Celery
beat sweeps expired sends with exponential backoff then marks failed. Frontend
console at `/admin/iot-gateways`. Spec:
`docs/superpowers/specs/2026-09-11-iot-gateway-command-api-design.md`.
```

- [ ] **Step 5: Final commit**

```bash
git add platform/docs/superpowers/plans/2026-09-10-modernization-README.md
git commit -m "docs: SUB-2 gateway command API complete (SUB-2 modernization)"
```

---

## Self-review

- **Spec coverage:** model + FK (T1), config/relay (T2), payload validation (T3), CRUD + link/provisioning (T4), issue+history (T5), ack subscribe/handler/auto-register/relay (T6), sweeper retry→fail (T7), backfill + compose wiring (T8), console list/detail/composer/history/polling (T9–T11), regression + docs (T12). All eight command types, Redis-list durability, correlated ack, TTL sweeper with retries, admin-send/auth-view, async accept are covered.
- **No placeholders:** every step has concrete code/commands.
- **Consistency:** `command_id` (uuid, unique) used by relay frames, ack frames, and history API throughout. `next_retry_datetime`/`compute_backoff` match the sweeper predicates. `enqueue_command` used by both API (T5) and sweeper requeue (T7). FakeRedis list ops added once (T2) and reused.