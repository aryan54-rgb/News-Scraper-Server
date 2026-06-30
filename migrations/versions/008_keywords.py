"""keywords

Revision ID: 008_keywords
Revises: 007_entities
Create Date: 2026-06-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "008_keywords"
down_revision = "007_entities"
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
        "keyword_group",
        *audit_columns(),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index(
        "uq_keyword_group_name_not_deleted",
        "keyword_group",
        ["name"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_table(
        "keyword",
        *audit_columns(),
        sa.Column("keyword_group_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("term", sa.String(255), nullable=False),
        sa.Column("match_type", sa.String(40), nullable=False, server_default="exact"),
        sa.Column("language_code", sa.String(12), nullable=False, server_default="und"),
        sa.Column("priority", postgresql.ENUM(name="keyword_priority_enum", create_type=False), nullable=False, server_default="medium"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.ForeignKeyConstraint(["keyword_group_id"], ["keyword_group.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("keyword_group_id", "term", "language_code", name="uq_keyword_group_term_language"),
    )
    op.create_index("idx_keyword_group_id", "keyword", ["keyword_group_id"])
    op.create_index("idx_keyword_term_trgm", "keyword", ["term"], postgresql_using="gin", postgresql_ops={"term": "gin_trgm_ops"})
    op.create_index("idx_keyword_priority", "keyword", ["priority"])
    op.create_index("idx_keyword_active_not_deleted", "keyword", ["is_active"], postgresql_where=sa.text("deleted_at IS NULL"))
    op.create_index("idx_keyword_metadata_gin", "keyword", ["metadata"], postgresql_using="gin")
    op.create_table(
        "keyword_hit",
        *audit_columns(),
        sa.Column("article_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("keyword_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("matched_text", sa.String(500), nullable=False),
        sa.Column("start_offset", sa.Integer()),
        sa.Column("end_offset", sa.Integer()),
        sa.Column("confidence_score", sa.Numeric(5, 4)),
        sa.CheckConstraint("start_offset IS NULL OR start_offset >= 0", name="ck_keyword_hit_keyword_hit_start_nonnegative"),
        sa.CheckConstraint("end_offset IS NULL OR end_offset >= start_offset", name="ck_keyword_hit_keyword_hit_offsets_ordered"),
        sa.CheckConstraint(
            "confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)",
            name="ck_keyword_hit_keyword_hit_confidence_range",
        ),
        sa.ForeignKeyConstraint(["article_id"], ["article.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["keyword_id"], ["keyword.id"], ondelete="RESTRICT"),
    )
    op.create_index("idx_keyword_hit_article_id", "keyword_hit", ["article_id"])
    op.create_index("idx_keyword_hit_keyword_id", "keyword_hit", ["keyword_id"])
    op.create_index("idx_keyword_hit_created_at", "keyword_hit", ["created_at"])


def downgrade() -> None:
    op.drop_index("idx_keyword_hit_created_at", table_name="keyword_hit")
    op.drop_index("idx_keyword_hit_keyword_id", table_name="keyword_hit")
    op.drop_index("idx_keyword_hit_article_id", table_name="keyword_hit")
    op.drop_table("keyword_hit")
    op.drop_index("idx_keyword_metadata_gin", table_name="keyword")
    op.drop_index("idx_keyword_active_not_deleted", table_name="keyword")
    op.drop_index("idx_keyword_priority", table_name="keyword")
    op.drop_index("idx_keyword_term_trgm", table_name="keyword")
    op.drop_index("idx_keyword_group_id", table_name="keyword")
    op.drop_table("keyword")
    op.drop_index("uq_keyword_group_name_not_deleted", table_name="keyword_group")
    op.drop_table("keyword_group")
