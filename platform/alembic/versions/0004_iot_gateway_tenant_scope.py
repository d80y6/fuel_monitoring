"""iot gateway tenant ownership

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-06

Closes the IoT-gateway half of G-003 (audit findings L2 and L4).

A gateway is shared hardware: one radio can carry tanks from several
organizations, so it cannot simply carry a single owning tenant on its data
model. What it does need is an explicit *operator* tenant, which is what this
revision adds:

* ``iot_gateways.company_id`` records which organization operates the device.
  ``NULL`` means a platform-owned gateway.
* Read visibility becomes "owned by my company, or carrying one of my tanks",
  implemented in the router; ``tank_ids`` is always filtered to the caller's own
  organization so a shared gateway never discloses another tenant's asset ids.
* Re-parenting a gateway now refuses to detach a tank outside the caller's
  organization, closing the case where a platform-level PATCH silently unpicked
  another tenant's hardware.

Shipped separately from 0003 because 0003 was already applied to deployed
databases and an amended revision never reruns.
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def _bind():
    return op.get_bind()


def _table_exists(name: str) -> bool:
    return sa.inspect(_bind()).has_table(name)


def _column_exists(table: str, column: str) -> bool:
    if not _table_exists(table):
        return False
    return column in {c["name"] for c in sa.inspect(_bind()).get_columns(table)}


def _index_names(table: str) -> set[str]:
    return {ix["name"] for ix in sa.inspect(_bind()).get_indexes(table)}


def upgrade() -> None:
    if not _table_exists("iot_gateways"):
        return
    if not _column_exists("iot_gateways", "company_id"):
        op.add_column(
            "iot_gateways", sa.Column("company_id", UUID(as_uuid=True), nullable=True)
        )
        op.create_foreign_key(
            "fk_iot_gateways_company_id",
            "iot_gateways",
            "companies",
            ["company_id"],
            ["id"],
        )
    if "ix_iot_gateways_company_id" not in _index_names("iot_gateways"):
        op.create_index("ix_iot_gateways_company_id", "iot_gateways", ["company_id"])


def downgrade() -> None:
    if not _table_exists("iot_gateways") or not _column_exists("iot_gateways", "company_id"):
        return
    if "ix_iot_gateways_company_id" in _index_names("iot_gateways"):
        op.drop_index("ix_iot_gateways_company_id", table_name="iot_gateways")
    op.drop_constraint("fk_iot_gateways_company_id", "iot_gateways", type_="foreignkey")
    op.drop_column("iot_gateways", "company_id")