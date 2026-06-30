"""events

Revision ID: 004_events
Revises: 003_documents
Create Date: 2026-06-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "004_events"
down_revision = "003_documents"
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
        "event",
        *audit_columns(),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("status", postgresql.ENUM(name="event_status_enum", create_type=False), nullable=False, server_default="identified"),
        sa.Column("severity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("confidence_score", sa.Numeric(5, 4)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("last_seen_at", sa.DateTime(timezone=True)),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.CheckConstraint("severity BETWEEN 1 AND 5", name="ck_event_event_severity_range"),
    )
    op.create_index("idx_event_status_last_seen", "event", ["status", "last_seen_at"])
    op.create_index("idx_event_started_at", "event", ["started_at"])
    op.create_index("idx_event_title_trgm", "event", ["title"], postgresql_using="gin", postgresql_ops={"title": "gin_trgm_ops"})
    op.create_index("idx_event_metadata_gin", "event", ["metadata"], postgresql_using="gin")
    op.create_table(
        "article_event",
        *audit_columns(),
        sa.Column("article_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("confidence_score", sa.Numeric(5, 4)),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)",
            name="ck_article_event_article_event_confidence_range",
        ),
        sa.ForeignKeyConstraint(["article_id"], ["article.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["event_id"], ["event.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("article_id", "event_id", name="uq_article_event_pair"),
    )
    op.create_index("idx_article_event_article_id", "article_event", ["article_id"])
    op.create_index("idx_article_event_event_id", "article_event", ["event_id"])


def downgrade() -> None:
    op.drop_index("idx_article_event_event_id", table_name="article_event")
    op.drop_index("idx_article_event_article_id", table_name="article_event")
    op.drop_table("article_event")
    op.drop_index("idx_event_metadata_gin", table_name="event")
    op.drop_index("idx_event_title_trgm", table_name="event")
    op.drop_index("idx_event_started_at", table_name="event")
    op.drop_index("idx_event_status_last_seen", table_name="event")
    op.drop_table("event")
