"""notification channel tenant scoping + delivery-log tenant

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-05

Closes:
* G-005 — notification channel credentials are write-only over the API; the
  tenant column lets channels be scoped/managed per organization instead of
  globally by any ``company_admin``.
* G-003 — ``notification_logs.company_id`` makes delivery history tenant-scoped.

The IoT gateway tenant column is deliberately NOT in this revision: it had
already been applied to deployed databases, so amending it here would never run
again. It ships as revision 0004 instead.

Additive and inspection-guarded: safe on a fresh ``create_all`` database (every
step no-ops) and on a pre-0003 database.
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "0003"
down_revision = "0002"
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


def _unique_constraints(table: str) -> list[dict]:
    inspector = sa.inspect(_bind())
    try:
        return inspector.get_unique_constraints(table)
    except NotImplementedError:  # pragma: no cover - dialect fallback
        return []


def upgrade() -> None:
    # --- notification_gateways.company_id ------------------------------------
    if _table_exists("notification_gateways") and not _column_exists(
        "notification_gateways", "company_id"
    ):
        op.add_column(
            "notification_gateways", sa.Column("company_id", UUID(as_uuid=True), nullable=True)
        )
        op.create_foreign_key(
            "fk_notification_gateways_company_id",
            "notification_gateways",
            "companies",
            ["company_id"],
            ["id"],
        )
        op.create_index(
            "ix_notification_gateways_company_id", "notification_gateways", ["company_id"]
        )

    # Channel names become unique per tenant, not globally.
    if _table_exists("notification_gateways"):
        uniques = {c.get("name") for c in _unique_constraints("notification_gateways")}
        if uniques:
            op.drop_constraint(
                sorted(u for u in uniques if u)[0], "notification_gateways", type_="unique"
            )
        if "ix_notification_gateways_name" not in _index_names("notification_gateways"):
            op.create_index("ix_notification_gateways_name", "notification_gateways", ["name"])
        op.create_unique_constraint(
            "uq_notification_gateways_company_name",
            "notification_gateways",
            ["company_id", "name"],
        )

    # --- notification_logs.company_id -----------------------------------------
    if _table_exists("notification_logs") and not _column_exists("notification_logs", "company_id"):
        op.add_column(
            "notification_logs", sa.Column("company_id", UUID(as_uuid=True), nullable=True)
        )
        op.create_foreign_key(
            "fk_notification_logs_company_id", "notification_logs", "companies", ["company_id"], ["id"]
        )
        op.create_index("ix_notification_logs_company_id", "notification_logs", ["company_id"])


def downgrade() -> None:
    if _table_exists("notification_logs") and _column_exists("notification_logs", "company_id"):
        op.drop_index("ix_notification_logs_company_id", table_name="notification_logs")
        op.drop_constraint("fk_notification_logs_company_id", "notification_logs", type_="foreignkey")
        op.drop_column("notification_logs", "company_id")
    if _table_exists("notification_gateways"):
        try:
            op.drop_constraint("uq_notification_gateways_company_name", "notification_gateways", type_="unique")
        except Exception:  # pragma: no cover - constraint may not exist
            pass
        if _column_exists("notification_gateways", "company_id"):
            op.drop_index("ix_notification_gateways_company_id", table_name="notification_gateways")
            op.drop_constraint(
                "fk_notification_gateways_company_id", "notification_gateways", type_="foreignkey"
            )
            op.drop_column("notification_gateways", "company_id")
        op.create_unique_constraint("uq_notification_gateways_name", "notification_gateways", ["name"])
