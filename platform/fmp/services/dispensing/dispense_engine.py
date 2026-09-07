"""Dispense Validation & Partial Dispense Engine.

Responsibilities
----------------
1. ``validate_code``    – authorize a dispense request at an RPi station.
2. ``complete_dispense`` – settle a transaction, consume the code, and — if
   only partially dispensed — atomically generate a NEW code for the leftover
   litres and return it for immediate dispatch.
3. ``audit_totalizer``  – compare the hardware secret counter against logged
   cumulative litres to detect theft/tampering.

Design notes
------------
* Codes are stored as salted PBKDF2 hashes (at-rest secret). Lookup uses the
  deterministic HMAC ``code_fp`` index column → O(log N), plus a final
  ``verify_code`` re-derivation as defence-in-depth.
* Redis fast-paths: a ``CONSUMED`` fingerprint set gives idempotent replay
  protection; a short-TTL per-code cache avoids DB hits during validate.
* A pessimistic ``SELECT ... FOR UPDATE`` on the code row, plus a short Redis
  lock, prevent two concurrent station callbacks settling the same code.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from fmp.core.config import get_settings
from fmp.core.redis import RedisClient
from fmp.core.security import code_fingerprint, hash_code, verify_code
from fmp.models.dispensing import (
    Allocation,
    DispenseCode,
    DispenseTransaction,
    StationTotalizer,
)
from fmp.schemas.dispensing import (
    CodeValidateRequest,
    CodeValidateResponse,
    DispenseCompleteRequest,
    DispenseCompleteResponse,
    PartialDispenseOutcome,
)
from fmp.services.dispensing.code_generator import (
    code_expiry,
    generate_unique_code,
)

logger = logging.getLogger(__name__)
settings = get_settings()

CONSUMED_SET = "dispense:used_fingerprints"
LOCK_PREFIX = "dispense:lock:"
CODE_CACHE_PREFIX = "dispense:code:"


def _cache_key(code: str) -> str:
    return f"{CODE_CACHE_PREFIX}{code_fingerprint(code)}"


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------
async def validate_code(
    session: AsyncSession,
    redis: RedisClient,
    req: CodeValidateRequest,
) -> CodeValidateResponse:
    code = req.code

    # 1. Fast knockout: already-consumed fingerprint
    if await redis.client.sismember(CONSUMED_SET, code_fingerprint(code)):
        return _reject("code_already_used")

    # 2. Per-station brute-force throttling
    allowed, _ = await redis.rate_limit(
        f"dispense:validate:{req.station_id}", settings.CODE_RATE_LIMIT_PER_MIN, 60
    )
    if not allowed:
        return _reject("rate_limited")

    # 3. Redis cached fast path
    cached = await redis.get_json(_cache_key(code))
    if cached is not None:
        return _valid_from_cache(cached)

    # 4. Indexed DB lookup
    stored = await _lookup_code(session, code)
    if stored is None:
        return _reject("invalid_code")
    disp_code, allocation = stored

    # 5. State checks
    if disp_code.status != "ACTIVE":
        return _reject("code_not_active")
    if disp_code.attempt_count >= disp_code.max_attempts:
        return _reject("max_attempts_exceeded")
    if disp_code.expires_at is not None and disp_code.expires_at < datetime.now(timezone.utc):
        return _reject("code_expired")
    if allocation.status in {"FULFILLED", "VOID"}:
        return _reject("allocation_settled")

    disp_code.attempt_count += 1
    await session.commit()

    # 6. Warm short-TTL cache
    remaining = round(max(0.0, allocation.remaining_liters), 3)
    payload = {
        "code_id": str(disp_code.id),
        "allocation_id": str(allocation.id),
        "employee_name": allocation.employee.name if allocation.employee else "",
        "remaining_liters": remaining,
    }
    await redis.set_json(_cache_key(code), payload, ttl=300)

    return CodeValidateResponse(
        valid=True,
        employee_name=payload["employee_name"],
        remaining_liters=remaining,
        code_id=disp_code.id,
    )


# --------------------------------------------------------------------------
# Settlement
# --------------------------------------------------------------------------
async def complete_dispense(
    session: AsyncSession,
    redis: RedisClient,
    req: DispenseCompleteRequest,
) -> DispenseCompleteResponse:
    fp = code_fingerprint(req.code)

    if not await _acquire_lock(redis, req.code):
        raise TimeoutError("dispense lock busy; retry later")

    try:
        # Replay guard: if fingerprint already consumed, return settled txn.
        if await redis.client.sismember(CONSUMED_SET, fp):
            existing = await _find_existing_txn(session, req.code)
            if existing is not None:
                return _from_existing(existing)
            return _reject_complete("code_already_used_no_txn")

        stored = await _lookup_code(session, req.code)
        if stored is None:
            return _reject_complete("invalid_code")
        disp_code, allocation = stored

        actual = round(req.actual_liters, 3)
        remaining_before = allocation.remaining_liters
        over = actual > remaining_before + settings.DISPENSE_GRACE_LITERS
        is_partial = (
            not over
            and (remaining_before - actual) > settings.PARTIAL_MIN_REMAINING_LITERS
        )

        # --- settle allocation & code --------------------------------------
        allocation.dispensed_liters = round(allocation.dispensed_liters + actual, 3)
        allocation.remaining_liters = round(max(0.0, remaining_before - actual), 3)
        disp_code.consumed_liters = round(disp_code.consumed_liters + actual, 3)
        disp_code.status = "CONSUMED"
        disp_code.used_at = datetime.now(timezone.utc)

        txn = DispenseTransaction(
            station_id=req.station_id,
            dispenser_id=req.dispenser_id,
            code_id=disp_code.id,
            employee_id=allocation.employee_id,
            allocation_id=allocation.id,
            requested_liters=round(req.requested_liters, 3),
            actual_liters=actual,
            secret_totalizer_before=req.secret_totalizer_before,
            secret_totalizer_after=req.secret_totalizer_after,
            status="COMPLETED" if not over else "OVER_DISPENSE",
            notes=None,
        )
        session.add(txn)

        partial_outcome: PartialDispenseOutcome | None = None
        new_code: str | None = None

        if is_partial:
            remainder = round(allocation.remaining_liters, 3)

            new_alloc = Allocation(
                employee_id=allocation.employee_id,
                upload_batch_id=allocation.upload_batch_id,
                company_id=allocation.company_id,
                invoice_number=allocation.invoice_number,
                allocated_liters=remainder,
                dispensed_liters=0.0,
                remaining_liters=remainder,
                status="PENDING",
            )
            session.add(new_alloc)
            await session.flush()

            new_code, new_hash, new_fp = await generate_unique_code(
                redis,
                existing_hashes_check=_hash_exists(session),
                existing_fingerprints_check=_fp_exists(session),
            )
            new_disp = DispenseCode(
                allocation_id=new_alloc.id,
                code_hash=new_hash,
                code_fp=new_fp,
                code_length=len(new_code),
                authorized_liters=remainder,
                consumed_liters=0.0,
                status="ACTIVE",
                max_attempts=settings.CODE_MAX_ATTEMPTS,
                expires_at=code_expiry(),
            )
            session.add(new_disp)
            await session.flush()

            allocation.status = "PARTIAL_FULFILLED"

            partial_outcome = PartialDispenseOutcome(
                partial=True,
                original_code_id=disp_code.id,
                dispensed_liters=actual,
                remaining_liters=remainder,
                new_code=new_code,
                new_code_id=new_disp.id,
                new_allocation_id=new_alloc.id,
            )
        else:
            allocation.status = "FULFILLED"
            partial_outcome = PartialDispenseOutcome(
                partial=False,
                original_code_id=disp_code.id,
                dispensed_liters=actual,
                remaining_liters=0.0,
            )

        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            # Newly-issued code collided (extremely rare); regenerate.
            logger.exception("IntegrityError settling dispense for code fingerprint=%s", fp)
            raise

        # ---- post-commit side effects -------------------------------------
        await redis.client.sadd(CONSUMED_SET, fp)
        await redis.delete(_cache_key(req.code))
        if is_partial and new_code and partial_outcome:
            await redis.set_json(
                _cache_key(new_code),
                {
                    "code_id": str(partial_outcome.new_code_id) or "",
                    "allocation_id": str(partial_outcome.new_allocation_id) or "",
                    "employee_name": allocation.employee.name if allocation.employee else "",
                    "remaining_liters": partial_outcome.remaining_liters,
                },
                ttl=300,
            )

        status = (
            "OVER_DISPENSE"
            if over
            else ("PARTIAL" if is_partial else "COMPLETED")
        )
        return DispenseCompleteResponse(
            success=True,
            transaction_id=txn.id,
            status=status,
            actual_liters=actual,
            requested_liters=round(req.requested_liters, 3),
            partial=partial_outcome,
        )
    finally:
        await _release_lock(redis, req.code)


# --------------------------------------------------------------------------
# Totalizer audit (called by ingestion worker after each settle)
# --------------------------------------------------------------------------
async def audit_totalizer(
    session: AsyncSession,
    redis: RedisClient,
    station_id: uuid.UUID,
    dispenser_id: uuid.UUID,
    totalizer_value: int,
    source: str = "hardware",
) -> tuple[bool, float | None]:
    """Compare the hardware secret counter against cumulative logged litres.

    Returns ``(ok, discrepancy_liters)``. Seeding the first reading is a no-op
    discrepancy. 100 pulses/litre is a per-pump calibration constant; a real
    deployment reads it from the dispenser config.
    """
    last = (
        await session.execute(
            select(StationTotalizer)
            .where(StationTotalizer.dispenser_id == dispenser_id)
            .order_by(StationTotalizer.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    if last is None:
        session.add(
            StationTotalizer(
                station_id=station_id,
                dispenser_id=dispenser_id,
                totalizer_value=totalizer_value,
                cumulative_liters=0.0,
                source=source,
            )
        )
        await session.commit()
        return True, None

    delta = totalizer_value - last.totalizer_value
    if delta < 0:
        return False, None

    dispensed_now = round(delta / 100.0, 3)  # pulses/litre calibration
    cumul = (
        await session.execute(
            select(DispenseTransaction.actual_liters).where(
                DispenseTransaction.dispenser_id == dispenser_id,
                DispenseTransaction.status == "COMPLETED",
            )
        )
    ).scalars().all()
    logged = round(sum(map(float, cumul)), 3)
    discrepancy = round(abs(logged - dispensed_now), 3)

    session.add(
        StationTotalizer(
            station_id=station_id,
            dispenser_id=dispenser_id,
            totalizer_value=totalizer_value,
            cumulative_liters=logged,
            source=source,
        )
    )
    await session.commit()

    ok = discrepancy <= settings.TOTALIZER_DISCREPANCY_TOLERANCE_LITERS
    return ok, discrepancy


# --------------------------------------------------------------------------
# Internals
# --------------------------------------------------------------------------
async def _lookup_code(
    session: AsyncSession, code: str
) -> tuple[DispenseCode, Allocation] | None:
    """Resolve a code by its indexed fingerprint, then verify via PBKDF2."""
    stmt = (
        select(DispenseCode)
        .where(DispenseCode.code_fp == code_fingerprint(code))
        .with_for_update()
    )
    disp_code = (await session.execute(stmt)).scalar_one_or_none()
    if disp_code is None:
        return None
    if not verify_code(code, disp_code.code_hash):
        return None
    alloc = (
        await session.execute(
            select(Allocation).where(Allocation.id == disp_code.allocation_id)
        )
    ).scalar_one_or_none()
    if alloc is None:
        return None
    return disp_code, alloc


def _hash_exists(session: AsyncSession):
    """Factory returning an async check for existing stored hash."""
    from sqlalchemy import select

    async def _exists(code_hash: str) -> bool:
        res = await session.execute(
            select(DispenseCode.id).where(DispenseCode.code_hash == code_hash)
        )
        return res.scalar_one_or_none() is not None

    return _exists


def _fp_exists(session: AsyncSession):
    """Factory returning an async check for existing stored fingerprint."""
    from sqlalchemy import select

    async def _exists(code_fp: str) -> bool:
        res = await session.execute(
            select(DispenseCode.id).where(DispenseCode.code_fp == code_fp)
        )
        return res.scalar_one_or_none() is not None

    return _exists


async def _find_existing_txn(
    session: AsyncSession, code: str
) -> DispenseTransaction | None:
    stored = await _lookup_code(session, code)
    if stored is None:
        return None
    disp_code, _ = stored
    txn = (
        await session.execute(
            select(DispenseTransaction)
            .where(DispenseTransaction.code_id == disp_code.id)
            .order_by(DispenseTransaction.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return txn


async def _acquire_lock(redis: RedisClient, code: str) -> bool:
    for _ in range(50):  # ~10s
        ok = await redis.client.set(
            f"{LOCK_PREFIX}{code_fingerprint(code)}", "1", nx=True, ex=30
        )
        if ok:
            return True
        await asyncio.sleep(0.2)
    return False


async def _release_lock(redis: RedisClient, code: str) -> None:
    await redis.delete(f"{LOCK_PREFIX}{code_fingerprint(code)}")


# ---- response helpers ------------------------------------------------------
def _reject(reason: str) -> CodeValidateResponse:
    return CodeValidateResponse(valid=False, reason=reason)


def _valid_from_cache(cached: dict) -> CodeValidateResponse:
    return CodeValidateResponse(
        valid=True,
        employee_name=cached.get("employee_name"),
        remaining_liters=cached.get("remaining_liters"),
        code_id=uuid.UUID(cached["code_id"]) if cached.get("code_id") else None,
    )


def _reject_complete(reason: str) -> DispenseCompleteResponse:
    return DispenseCompleteResponse(
        success=False,
        transaction_id=0,
        status="REJECTED",
        actual_liters=0.0,
        requested_liters=0.0,
        partial=None,
    )


def _from_existing(txn: DispenseTransaction) -> DispenseCompleteResponse:
    return DispenseCompleteResponse(
        success=True,
        transaction_id=txn.id,
        status="COMPLETED",
        actual_liters=txn.actual_liters,
        requested_liters=txn.requested_liters,
        partial=None,
    )