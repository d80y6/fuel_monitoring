"""Idempotent seed of built-in fuel types."""
from __future__ import annotations

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

DEFAULT_FUELS = [
    {"code": "gasoline", "name": "Gasoline", "base_density": 750.0,
     "thermal_expansion_coeff": 0.00095, "max_vapor_pressure": 60.0, "viscosity_cst": 0.6},
    {"code": "diesel", "name": "Diesel", "base_density": 845.0,
     "thermal_expansion_coeff": 0.00080, "max_vapor_pressure": 2.0, "viscosity_cst": 2.5},
    {"code": "kerosene", "name": "Kerosene", "base_density": 800.0,
     "thermal_expansion_coeff": 0.00090, "max_vapor_pressure": 1.5, "viscosity_cst": 1.4},
    {"code": "jet_fuel", "name": "Jet Fuel", "base_density": 810.0,
     "thermal_expansion_coeff": 0.00085, "max_vapor_pressure": 1.2, "viscosity_cst": 1.1},
    {"code": "ethanol", "name": "Ethanol", "base_density": 789.0,
     "thermal_expansion_coeff": 0.00110, "max_vapor_pressure": 16.0, "viscosity_cst": 1.2},
]

UPSERT_SQL = text(
    """INSERT INTO fuel_types (id, code, name, base_density, thermal_expansion_coeff,
                              max_vapor_pressure, viscosity_cst, created_at, updated_at)
       VALUES (gen_random_uuid(), :code, :name, :base_density, :thermal_expansion_coeff,
               :max_vapor_pressure, :viscosity_cst, now(), now())
       ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name,
                                        base_density = EXCLUDED.base_density,
                                        thermal_expansion_coeff = EXCLUDED.thermal_expansion_coeff,
                                        max_vapor_pressure = EXCLUDED.max_vapor_pressure,
                                        viscosity_cst = EXCLUDED.viscosity_cst"""
)


async def seed_fuel_types(engine: AsyncEngine | None = None) -> int:
    """Upsert the built-in fuel types.

    When no engine is given, the app's default async engine is used and its
    pooled connections released. A caller-provided engine is never disposed —
    ownership stays with the caller.
    """
    from fmp.core.database import engine as default_engine

    eng = default_engine if engine is None else engine
    owns_engine = engine is None
    n = 0
    async with eng.begin() as conn:
        for fuel in DEFAULT_FUELS:
            await conn.execute(UPSERT_SQL, fuel)
            n += 1
    if owns_engine:
        await eng.dispose()
    return n


def sync_seed(bind) -> None:
    """Synchronous upsert of DEFAULT_FUELS on a caller-provided sync bind.

    Used inside Alembic migrations (the sync Connection handed to upgrade()).
    """
    for fuel in DEFAULT_FUELS:
        bind.execute(UPSERT_SQL, fuel)


if __name__ == "__main__":
    print(f"seeded {asyncio.run(seed_fuel_types())} fuel types")