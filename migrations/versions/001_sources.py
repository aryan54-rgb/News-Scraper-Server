"""sources

Revision ID: 001_sources
Revises:
Create Date: 2026-06-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "001_sources"
down_revision = None
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


ENUMS: Sequence[postgresql.ENUM] = (
    postgresql.ENUM("rss", "website", "api", "social", "government", "wire", "other", name="source_type_enum"),
    postgresql.ENUM("registered", "active", "degraded", "suspended", "deprecated", name="source_status_enum"),
    postgresql.ENUM("created", "scheduled", "running", "paused", "failed", "archived", name="collector_status_enum"),
    postgresql.ENUM("pending", "classified", "validated", "stale", "rejected", name="classification_status_enum"),
    postgresql.ENUM("person", "organization", "location", "government", "facility", "event", "other", name="entity_type_enum"),
    postgresql.ENUM("identified", "active", "concluded", "merged", "archived", name="event_status_enum"),
    postgresql.ENUM("low", "medium", "high", "critical", name="keyword_priority_enum"),
)


def upgrade() -> None:
    bind = op.get_bind()
    op.execute(sa.text('CREATE EXTENSION IF NOT EXISTS "pgcrypto"'))
    op.execute(sa.text('CREATE EXTENSION IF NOT EXISTS "pg_trgm"'))
    for enum_type in ENUMS:
        enum_type.create(bind, checkfirst=True)

    op.create_table(
        "source_type",
        *audit_columns(),
        sa.Column("code", postgresql.ENUM(name="source_type_enum", create_type=False), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text()),
        sa.UniqueConstraint("code", name="uq_source_type_code"),
        sa.UniqueConstraint("name", name="uq_source_type_name"),
    )
    op.create_table(
        "source_group",
        *audit_columns(),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
    )
    op.create_index(
        "uq_source_group_name_not_deleted",
        "source_group",
        ["name"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_table(
        "source",
        *audit_columns(),
        sa.Column("source_type_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("url", sa.Text()),
        sa.Column("domain", sa.String(255)),
        sa.Column("status", postgresql.ENUM(name="source_status_enum", create_type=False), nullable=False, server_default="registered"),
        sa.Column("reliability_score", sa.Numeric(3, 2)),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.CheckConstraint(
            "reliability_score IS NULL OR (reliability_score >= 0 AND reliability_score <= 1)",
            name="ck_source_source_reliability_score_range",
        ),
        sa.ForeignKeyConstraint(["source_type_id"], ["source_type.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("domain", "source_type_id", name="uq_source_domain_type"),
    )
    op.create_index("idx_source_source_type_id", "source", ["source_type_id"])
    op.create_index("idx_source_domain", "source", ["domain"])
    op.create_index("idx_source_status", "source", ["status"])
    op.create_index("idx_source_active_not_deleted", "source", ["status"], postgresql_where=sa.text("deleted_at IS NULL"))
    op.create_index("idx_source_metadata_gin", "source", ["metadata"], postgresql_using="gin")
    op.create_table(
        "source_group_membership",
        *audit_columns(),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_group_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["source.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_group_id"], ["source_group.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("source_id", "source_group_id", name="uq_source_group_membership_pair"),
    )
    op.create_index("idx_source_group_membership_source_id", "source_group_membership", ["source_id"])
    op.create_index("idx_source_group_membership_group_id", "source_group_membership", ["source_group_id"])


def downgrade() -> None:
    op.drop_index("idx_source_group_membership_group_id", table_name="source_group_membership")
    op.drop_index("idx_source_group_membership_source_id", table_name="source_group_membership")
    op.drop_table("source_group_membership")
    op.drop_index("idx_source_metadata_gin", table_name="source")
    op.drop_index("idx_source_active_not_deleted", table_name="source")
    op.drop_index("idx_source_status", table_name="source")
    op.drop_index("idx_source_domain", table_name="source")
    op.drop_index("idx_source_source_type_id", table_name="source")
    op.drop_table("source")
    op.drop_index("uq_source_group_name_not_deleted", table_name="source_group")
    op.drop_table("source_group")
    op.drop_table("source_type")
    bind = op.get_bind()
    for enum_type in reversed(ENUMS):
        enum_type.drop(bind, checkfirst=True)
