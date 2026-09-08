"""fuel dynamics: fuel_types + strapping_tables, tank/measurement columns

Revision ID: 0001
Revises:
Create Date: 2026-09-08

Brings the physical schema in line with the current ORM models:
  - creates fuel_types + strapping_tables
  - adds shape/density FK columns to tanks (replacing legacy fluid_density)
  - adds GOV/NSV/density volume-tracking columns to measurements
  - seeds the built-in fuel rows and backfills tanks.fuel_type_id
Every step is guarded (inspect-first) so the migration is a no-op-safe idempotent
upgrade against schemas that already match the current models.
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op
from fmp.scripts.seed_fuel_types import sync_seed

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def _table_exists(bind, name: str) -> bool:
    return sa.inspect(bind).has_table(name)


def _column_exists(bind, table: str, column: str) -> bool:
    if not _table_exists(bind, table):
        return False
    return column in {c["name"] for c in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()

    # --- fuel_types ---------------------------------------------------------
    if not _table_exists(bind, "fuel_types"):
        op.create_table(
            "fuel_types",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("code", sa.String(32), nullable=False),
            sa.Column("name", sa.String(64), nullable=False),
            sa.Column("base_density", sa.Float(), nullable=False),
            sa.Column("thermal_expansion_coeff", sa.Float(), nullable=False),
            sa.Column("max_vapor_pressure", sa.Float(), nullable=False),
            sa.Column("viscosity_cst", sa.Float(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )
        op.create_index("ix_fuel_types_code", "fuel_types", ["code"], unique=True)

    # --- strapping_tables --------------------------------------------------
    # Guard also requires tanks to exist (FK target); on a brand-new DB the
    # schema is minted by init_db's create_all, not the migration.
    if _table_exists(bind, "tanks") and not _table_exists(bind, "strapping_tables"):
        op.create_table(
            "strapping_tables",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("tank_id", UUID(as_uuid=True), nullable=False),
            sa.Column(
                "calibration_data",
                JSONB(),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
            sa.Column(
                "interpolation_method",
                sa.String(20),
                nullable=False,
                server_default="linear",
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(
                ["tank_id"], ["tanks.id"], name="fk_strapping_tables_tank_id"
            ),
        )
        op.create_index(
            "ix_strapping_tables_tank_id", "strapping_tables", ["tank_id"], unique=True
        )

    # --- tanks: shape + fuel/strapping columns -----------------------------
    if _table_exists(bind, "tanks"):
        if not _column_exists(bind, "tanks", "tank_shape"):
            op.add_column(
                "tanks",
                sa.Column(
                    "tank_shape",
                    sa.String(20),
                    nullable=False,
                    server_default="vertical_cylinder",
                ),
            )
        if not _column_exists(bind, "tanks", "dish_depth"):
            op.add_column("tanks", sa.Column("dish_depth", sa.Float(), nullable=True))
        if not _column_exists(bind, "tanks", "tank_width"):
            op.add_column("tanks", sa.Column("tank_width", sa.Float(), nullable=True))
        if not _column_exists(bind, "tanks", "fuel_type_id"):
            op.add_column(
                "tanks", sa.Column("fuel_type_id", UUID(as_uuid=True), nullable=True)
            )
            op.create_foreign_key(
                "fk_tanks_fuel_type_id",
                "tanks",
                "fuel_types",
                ["fuel_type_id"],
                ["id"],
            )
            op.create_index("ix_tanks_fuel_type_id", "tanks", ["fuel_type_id"])
        if not _column_exists(bind, "tanks", "strapping_table_id"):
            op.add_column(
                "tanks",
                sa.Column("strapping_table_id", UUID(as_uuid=True), nullable=True),
            )
            op.create_foreign_key(
                "fk_tanks_strapping_table_id",
                "tanks",
                "strapping_tables",
                ["strapping_table_id"],
                ["id"],
            )
            op.create_index(
                "ix_tanks_strapping_table_id", "tanks", ["strapping_table_id"]
            )

    # --- seed fuels + backfill tanks.fuel_type_id --------------------------
    sync_seed(bind)

    if _column_exists(bind, "tanks", "fluid_density"):
        # Backfill by NEAREST base_density (documented plan correction). The
        # original plan cascade (gasoline <=775, diesel <=860, else ethanol)
        # misattributes edge fuels: ethanol (789 kg/m3) falls inside diesel's
        # band and gasoline just above 775 is labeled diesel. Nearest-base maps
        # each legacy tank to the physically closest fuel instead.
        fuels = [
            (row[0], row[1])
            for row in bind.execute(sa.text("SELECT id, base_density FROM fuel_types"))
        ]
        rows = bind.execute(
            sa.text(
                "SELECT id, fluid_density FROM tanks "
                "WHERE fluid_density IS NOT NULL AND fuel_type_id IS NULL"
            )
        ).fetchall()
        for tank_id, fluid_density in rows:
            fuel_id = min(fuels, key=lambda f: abs(f[1] - fluid_density))[0]
            bind.execute(
                sa.text("UPDATE tanks SET fuel_type_id = :fuel_id WHERE id = :tank_id"),
                {"fuel_id": fuel_id, "tank_id": tank_id},
            )

    if _column_exists(bind, "tanks", "fluid_density"):
        op.drop_column("tanks", "fluid_density")

    # --- measurements: GOV/NSV/density volume columns ----------------------
    if _table_exists(bind, "measurements"):
        for col in ("gov_volume", "net_volume", "density_at_temperature"):
            if not _column_exists(bind, "measurements", col):
                op.add_column("measurements", sa.Column(col, sa.Float(), nullable=True))


def downgrade() -> None:
    # Downgrade is guarded symmetrically with upgrade's no-op-safety: on a
    # bare DB where upgrade created only fuel_types, every section that
    # touches tanks / measurements / strapping_tables is skipped.
    bind = op.get_bind()

    # --- tanks: restore legacy fluid_density --------------------------------
    if _table_exists(bind, "tanks"):
        op.add_column("tanks", sa.Column("fluid_density", sa.Float(), nullable=True))
        bind.execute(
            sa.text(
                "UPDATE tanks SET fluid_density = COALESCE("
                "  (SELECT ft.base_density FROM fuel_types ft"
                "    WHERE ft.id = tanks.fuel_type_id), 0)"
            )
        )
        op.alter_column(
            "tanks",
            "fluid_density",
            existing_type=sa.Float(),
            existing_nullable=True,
            nullable=False,
        )

    # --- measurements: drop GOV/NSV/density columns -------------------------
    if _table_exists(bind, "measurements"):
        for col in ("density_at_temperature", "net_volume", "gov_volume"):
            if _column_exists(bind, "measurements", col):
                op.drop_column("measurements", col)

    # --- tanks: drop FK + FK-column pairs -----------------------------------
    if _table_exists(bind, "tanks"):
        for col, idx in (
            ("strapping_table_id", "ix_tanks_strapping_table_id"),
            ("fuel_type_id", "ix_tanks_fuel_type_id"),
        ):
            if _column_exists(bind, "tanks", col):
                op.drop_index(idx, table_name="tanks")
                for fk in (
                    fk["name"]
                    for fk in sa.inspect(bind).get_foreign_keys("tanks")
                    if col in fk["constrained_columns"]
                ):
                    op.drop_constraint(fk, "tanks", type_="foreignkey")
                op.drop_column("tanks", col)

        for col in ("tank_width", "dish_depth", "tank_shape"):
            if _column_exists(bind, "tanks", col):
                op.drop_column("tanks", col)

    # --- strapping_tables + index -------------------------------------------
    if _table_exists(bind, "strapping_tables"):
        op.drop_index("ix_strapping_tables_tank_id", table_name="strapping_tables")
        op.drop_table("strapping_tables")

    # --- fuel_types + index -------------------------------------------------
    if _table_exists(bind, "fuel_types"):
        op.drop_index("ix_fuel_types_code", table_name="fuel_types")
        op.drop_table("fuel_types")