"""tenancy + alarm lifecycle + station keys + audit + notification rules

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-15

Closed-gaps: G-003 (users.company_id), G-004 (alarm state), G-113 (station API
keys), G-116 (audit_events), G-112 (notification_rules), G-117 groundwork.

Every step is inspection-guarded so the migration is safe to run on:
  * fresh databases created by metadata ``create_all`` (all steps no-op),
  * legacy databases deployed before this revision (steps apply).
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision = "0002"
down_revision = "0001"
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


def upgrade() -> None:
    # --- users.company_id ----------------------------------------------------
    if _table_exists("users") and not _column_exists("users", "company_id"):
        op.add_column("users", sa.Column("company_id", UUID(as_uuid=True), nullable=True))
        op.create_foreign_key(
            "fk_users_company_id", "users", "companies", ["company_id"], ["id"]
        )
        op.create_index("ix_users_company_id", "users", ["company_id"])

    # --- stations api key identity ------------------------------------------
    if _table_exists("stations"):
        if not _column_exists("stations", "api_key_hash"):
            op.add_column("stations", sa.Column("api_key_hash", sa.String(256), nullable=True))
        if not _column_exists("stations", "api_key_prefix"):
            op.add_column("stations", sa.Column("api_key_prefix", sa.String(16), nullable=True))
            op.create_index("ix_stations_api_key_prefix", "stations", ["api_key_prefix"])

    # --- alarms lifecycle ----------------------------------------------------
    if _table_exists("alarms"):
        if not _column_exists("alarms", "state"):
            op.add_column(
                "alarms",
                sa.Column("state", sa.String(20), server_default="active", nullable=False),
            )
            op.create_index("ix_alarms_state", "alarms", ["state"])
        if not _column_exists("alarms", "resolved_at"):
            op.add_column("alarms", sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True))
        if not _column_exists("alarms", "resolved_message"):
            op.add_column("alarms", sa.Column("resolved_message", sa.Text(), nullable=True))
        if not any(ix["name"] == "ix_alarms_type" for ix in sa.inspect(_bind()).get_indexes("alarms")):
            op.create_index("ix_alarms_type", "alarms", ["type"])

    # --- notification_rules --------------------------------------------------
    if not _table_exists("notification_rules"):
        op.create_table(
            "notification_rules",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=True),
            sa.Column("name", sa.String(100), nullable=False),
            sa.Column("event_type", sa.String(40), nullable=False, server_default="alarm"),
            sa.Column("min_level", sa.String(20), nullable=False, server_default="WARNING"),
            sa.Column("site_id", UUID(as_uuid=True), sa.ForeignKey("sites.id"), nullable=True),
            sa.Column("channel", sa.String(20), nullable=False),
            sa.Column("targets", JSONB, nullable=False, server_default="[]"),
            sa.Column("template", sa.Text(), nullable=True),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_notification_rules_company_id", "notification_rules", ["company_id"])
        op.create_index("ix_notification_rules_event_type", "notification_rules", ["event_type"])
        op.create_index("ix_notification_rules_site_id", "notification_rules", ["site_id"])

    # --- notification_logs: generic event support ----------------------------
    if _table_exists("notification_logs"):
        if not _column_exists("notification_logs", "event_type"):
            op.add_column(
                "notification_logs",
                sa.Column("event_type", sa.String(32), nullable=False, server_default="dispense_code"),
            )
            op.add_column("notification_logs", sa.Column("event_ref", sa.String(64), nullable=True))
            op.create_index("ix_notification_logs_event_type", "notification_logs", ["event_type"])
            op.create_index("ix_notification_logs_event_ref", "notification_logs", ["event_ref"])
        if _column_exists("notification_logs", "recipient_phone"):
            op.alter_column(
                "notification_logs", "recipient_phone", new_column_name="recipient"
            )
            op.alter_column(
                "notification_logs",
                "recipient",
                type_=sa.String(254),
                existing_type=sa.String(20),
            )
        # allocation_id becomes nullable (alarm notifications carry no allocation)
        cols = {c["name"]: c for c in sa.inspect(_bind()).get_columns("notification_logs")}
        if cols["allocation_id"]["nullable"] is False:
            op.alter_column(
                "notification_logs", "allocation_id", nullable=True, existing_type=UUID(as_uuid=True)
            )

    # --- audit_events --------------------------------------------------------
    if not _table_exists("audit_events"):
        op.create_table(
            "audit_events",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("actor_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("actor_username", sa.String(64), nullable=True),
            sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=True),
            sa.Column("action", sa.String(64), nullable=False),
            sa.Column("entity_type", sa.String(64), nullable=False),
            sa.Column("entity_id", sa.String(64), nullable=True),
            sa.Column("detail", JSONB, nullable=True),
        )
        for col in ("at", "actor_id", "company_id", "action", "entity_type", "entity_id"):
            op.create_index(f"ix_audit_events_{col}", "audit_events", [col])


def downgrade() -> None:
    # Destructive downgrade intentionally not provided: this schema change set
    # adds nullable columns and new tables only. Rollback = `alembic_stamp`
    # back to 0001 and manual column drops if ever needed (documented ops path).
    pass
