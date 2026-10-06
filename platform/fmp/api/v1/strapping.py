"""Per-tank strapping (calibration) table API."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from fmp.api.deps import CurrentUser, PrivilegedUser, SessionDep
from fmp.core.tenancy import company_id_for_tank, tenant_scope
from fmp.models import StrappingTable, Tank
from fmp.schemas.strapping import StrappingTableRead, StrappingTableUpsert

router = APIRouter(prefix="/api/v1/tanks/{tank_id}/strapping", tags=["strapping"])


def _to_read(row: StrappingTable) -> StrappingTableRead:
    data = row.calibration_data or []
    return StrappingTableRead(
        id=row.id, tank_id=row.tank_id,
        calibration_data=[{"height": p["height"], "volume": p["volume"]} for p in data],
        interpolation_method=row.interpolation_method,
        created_at=row.created_at,
    )


async def _require_tank(tank_id, session, scope) -> Tank:
    """Load a tank the caller may use, or 404.

    A strapping table is calibration data for a physical asset, so it carries the
    same tenant boundary as the tank itself.
    """
    tank = (await session.execute(
        select(Tank).where(Tank.id == tank_id, Tank.deleted_at.is_(None))
    )).scalar_one_or_none()
    if tank is None:
        raise HTTPException(404, "tank not found")
    if not scope.is_platform:
        company_id = await company_id_for_tank(session, tank_id)
        if company_id is None or company_id != scope.company_id:
            raise HTTPException(404, "tank not found")
    return tank


@router.get("", response_model=StrappingTableRead)
async def get_strapping(tank_id: uuid.UUID, current: CurrentUser, session: SessionDep):
    await _require_tank(tank_id, session, tenant_scope(current))
    row = (await session.execute(
        select(StrappingTable).where(StrappingTable.tank_id == tank_id)
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "no strapping table for this tank")
    return _to_read(row)


@router.put("", response_model=StrappingTableRead)
async def upsert_strapping(
    tank_id: uuid.UUID, payload: StrappingTableUpsert, current: PrivilegedUser, session: SessionDep
):
    tank = await _require_tank(tank_id, session, tenant_scope(current))
    row = (await session.execute(
        select(StrappingTable).where(StrappingTable.tank_id == tank_id)
    )).scalar_one_or_none()
    if row is None:
        row = StrappingTable(
            tank_id=tank_id,
            calibration_data=[p.model_dump() for p in payload.calibration_data],
            interpolation_method=payload.interpolation_method,
        )
        session.add(row)
    else:
        row.calibration_data = [p.model_dump() for p in payload.calibration_data]
        row.interpolation_method = payload.interpolation_method
    await session.flush()
    tank.strapping_table_id = row.id
    await session.commit()
    await session.refresh(row)
    return _to_read(row)
