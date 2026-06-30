"""collection

Revision ID: 002_collection
Revises: 001_sources
Create Date: 2026-06-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "002_collection"
down_revision = "001_sources"
branch_labels = None
depends_on = None


def audit_columns() -> list[sa.Column]:
    return [
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True)),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True)),
    ]


def upgrade() -> None:
    op.create_table(
        "collector_job",
        *audit_columns(),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("job_type", sa.String(80), nullable=False),
        sa.Column("status", postgresql.ENUM(name="collector_status_enum", create_type=False), nullable=False, server_default="created"),
        sa.Column("cron_expression", sa.String(120)),
        sa.Column("timezone", sa.String(80), nullable=False, server_default="UTC"),
        sa.Column("next_run_at", sa.DateTime(timezone=True)),
        sa.Column("last_run_at", sa.DateTime(timezone=True)),
        sa.Column("config", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.ForeignKeyConstraint(["source_id"], ["source.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("source_id", "name", name="uq_collector_job_source_name"),
    )
    op.create_index("idx_collector_job_source_id", "collector_job", ["source_id"])
    op.create_index("idx_collector_job_status_next_run", "collector_job", ["status", "next_run_at"])
    op.create_index("idx_collector_job_config_gin", "collector_job", ["config"], postgresql_using="gin")
    op.create_table(
        "fetch_log",
        *audit_columns(),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("collector_job_id", postgresql.UUID(as_uuid=True)),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("status_code", sa.Integer()),
        sa.Column("content_hash", sa.String(128)),
        sa.Column("duration_ms", sa.Integer()),
        sa.Column("response_size_bytes", sa.Integer()),
        sa.Column("error_code", sa.String(120)),
        sa.Column("error_message", sa.Text()),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("duration_ms IS NULL OR duration_ms >= 0", name="ck_fetch_log_fetch_log_duration_nonnegative"),
        sa.CheckConstraint("response_size_bytes IS NULL OR response_size_bytes >= 0", name="ck_fetch_log_fetch_log_size_nonnegative"),
        sa.ForeignKeyConstraint(["source_id"], ["source.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["collector_job_id"], ["collector_job.id"], ondelete="SET NULL"),
    )
    op.create_index("idx_fetch_log_source_fetched_at", "fetch_log", ["source_id", "fetched_at"])
    op.create_index("idx_fetch_log_job_fetched_at", "fetch_log", ["collector_job_id", "fetched_at"])
    op.create_index("idx_fetch_log_status_code", "fetch_log", ["status_code"])
    op.create_index("idx_fetch_log_content_hash", "fetch_log", ["content_hash"])


def downgrade() -> None:
    op.drop_index("idx_fetch_log_content_hash", table_name="fetch_log")
    op.drop_index("idx_fetch_log_status_code", table_name="fetch_log")
    op.drop_index("idx_fetch_log_job_fetched_at", table_name="fetch_log")
    op.drop_index("idx_fetch_log_source_fetched_at", table_name="fetch_log")
    op.drop_table("fetch_log")
    op.drop_index("idx_collector_job_config_gin", table_name="collector_job")
    op.drop_index("idx_collector_job_status_next_run", table_name="collector_job")
    op.drop_index("idx_collector_job_source_id", table_name="collector_job")
    op.drop_table("collector_job")
