"""Machine-to-machine identity for edge devices (G-002 / G-113).

Two independent device trust boundaries:

**Station keys.** A dispenser controller (Raspberry Pi class) authenticates to
the dispensing endpoints with ``X-Station-Key: <key>``. The station is identified
by ``X-Station-Id``. Keys are 32 random bytes rendered base32, stored salted with
PBKDF2-SHA256 (the same primitive as passwords), and never readable after
issuance — only an 8-character prefix survives for rotation bookkeeping.

**Ingest key.** The standalone ingestion service's HTTP fallback
(``/api/v1/ingest/*``) is protected by one shared secret from
``INGEST_API_KEY``. When that setting is empty the HTTP fallback is *disabled*
outright (404) rather than left open; MQTT is the normal device path.

Both dependencies fail closed: an unknown station, a station without a key, a
wrong key and a missing header are all 401.
"""
from __future__ import annotations

import logging
import secrets
import uuid
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fmp.core.config import get_settings
from fmp.core.database import get_session
from fmp.models import Site, Station

logger = logging.getLogger(__name__)

STATION_KEY_HEADER = "X-Station-Key"
STATION_ID_HEADER = "X-Station-Id"
INGEST_KEY_HEADER = "X-Ingest-Key"

#: Number of PBKDF2 iterations for device keys. Device controllers authenticate
#: a few times per dispense, so this sits below the interactive password cost.
DEVICE_KEY_ITERATIONS = 120_000


def _hash_device_key(plain: str) -> str:
    """PBKDF2-SHA256 device key hash, format ``pbkdf2_sha256$<iter>$<salt>$<dk>``."""
    import base64
    import hashlib

    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256", plain.encode("utf-8"), salt, DEVICE_KEY_ITERATIONS, dklen=32
    )
    return "pbkdf2_sha256${0}${1}${2}".format(
        DEVICE_KEY_ITERATIONS,
        base64.b64encode(salt).decode(),
        base64.b64encode(dk).decode(),
    )


def _verify_device_key(plain: str, stored: str) -> bool:
    import base64
    import hashlib

    parts = stored.split("$")
    if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
        return False
    try:
        iterations = int(parts[1])
        salt = base64.b64decode(parts[2])
        expected = base64.b64decode(parts[3])
    except (ValueError, TypeError):
        return False
    dk = hashlib.pbkdf2_hmac(
        "sha256", plain.encode("utf-8"), salt, iterations, dklen=len(expected)
    )
    return secrets.compare_digest(dk, expected)


def generate_station_key() -> tuple[str, str, str]:
    """Mint a new station key. Returns ``(plaintext, hash, prefix)``.

    The plaintext is shown to the operator exactly once; only the hash is stored.
    """
    plaintext = "fmk_" + secrets.token_urlsafe(32)
    key_hash = _hash_device_key(plaintext)
    return plaintext, key_hash, plaintext[:12]


async def get_station_by_serial(session: AsyncSession, identifier: str) -> Station | None:
    """Resolve a station from a UUID, a serial number, or a raspberry_pi_id."""
    station: Station | None = None
    try:
        station = (
            await session.execute(
                select(Station).where(Station.id == uuid.UUID(identifier))
            )
        ).scalar_one_or_none()
    except (ValueError, AttributeError, TypeError):
        station = None
    if station is None:
        stmt = select(Station).where(
            (Station.serial_number == identifier) | (Station.raspberry_pi_id == identifier)
        )
        station = (await session.execute(stmt)).scalars().first()
    return station


async def authenticate_station(
    session: AsyncSession,
    station_id: str | None,
    presented_key: str | None,
) -> Station:
    """Validate a device identity or raise 401. Never reveals which part failed."""
    if not station_id or not presented_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"device identity required ({STATION_ID_HEADER} + {STATION_KEY_HEADER})",
            headers={"WWW-Authenticate": "DeviceKey"},
        )
    station = await get_station_by_serial(session, station_id)
    if station is None or not station.api_key_hash:
        # Same error for "no such station" and "station without a key" so the
        # endpoint cannot be used to enumerate stations.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid device credentials",
            headers={"WWW-Authenticate": "DeviceKey"},
        )
    if not _verify_device_key(presented_key, station.api_key_hash):
        logger.warning(
            "station key rejected station_id=%s serial=%s", station_id, station.serial_number
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid device credentials",
            headers={"WWW-Authenticate": "DeviceKey"},
        )
    return station


async def require_station(
    session: Annotated[AsyncSession, Depends(get_session)],
    x_station_id: Annotated[str | None, Header(alias=STATION_ID_HEADER)] = None,
    x_station_key: Annotated[str | None, Header(alias=STATION_KEY_HEADER)] = None,
) -> Station:
    """FastAPI dependency authenticating a dispenser controller."""
    return await authenticate_station(session, x_station_id, x_station_key)


async def company_id_for_station_row(session: AsyncSession, station: Station) -> uuid.UUID | None:
    """Tenant owning a station (site -> company)."""
    row = (
        await session.execute(select(Site.company_id).where(Site.id == station.site_id))
    ).first()
    return row[0] if row else None


def require_ingest_key(
    x_ingest_key: Annotated[str | None, Header(alias=INGEST_KEY_HEADER)] = None,
) -> bool:
    """FastAPI dependency guarding the ingestion HTTP fallback.

    Fails closed: with no ``INGEST_API_KEY`` configured the endpoint must not be
    mounted at all, and this dependency rejects every caller (404 is raised by
    the router when the feature is disabled).
    """
    settings = get_settings()
    expected = settings.INGEST_API_KEY
    if not expected:
        raise HTTPException(status_code=404, detail="HTTP ingestion fallback is disabled")
    if not x_ingest_key or not secrets.compare_digest(x_ingest_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid ingestion key",
            headers={"WWW-Authenticate": "IngestKey"},
        )
    return True
