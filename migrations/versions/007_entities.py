"""entities

Revision ID: 007_entities
Revises: 006_classification
Create Date: 2026-06-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "007_entities"
down_revision = "006_classification"
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
        "entity",
        *audit_columns(),
        sa.Column("entity_type", postgresql.ENUM(name="entity_type_enum", create_type=False), nullable=False),
        sa.Column("canonical_name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("external_ids", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.UniqueConstraint("entity_type", "canonical_name", name="uq_entity_type_canonical_name"),
    )
    op.create_index("idx_entity_type", "entity", ["entity_type"])
    op.create_index("idx_entity_canonical_name_trgm", "entity", ["canonical_name"], postgresql_using="gin", postgresql_ops={"canonical_name": "gin_trgm_ops"})
    op.create_index("idx_entity_external_ids_gin", "entity", ["external_ids"], postgresql_using="gin")
    op.create_index("idx_entity_metadata_gin", "entity", ["metadata"], postgresql_using="gin")
    op.create_table(
        "entity_alias",
        *audit_columns(),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("alias", sa.String(255), nullable=False),
        sa.Column("language_code", sa.String(12), nullable=False, server_default="und"),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.ForeignKeyConstraint(["entity_id"], ["entity.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("entity_id", "alias", "language_code", name="uq_entity_alias_entity_alias_language"),
    )
    op.create_index("idx_entity_alias_entity_id", "entity_alias", ["entity_id"])
    op.create_index("idx_entity_alias_alias_trgm", "entity_alias", ["alias"], postgresql_using="gin", postgresql_ops={"alias": "gin_trgm_ops"})
    op.create_table(
        "entity_mention",
        *audit_columns(),
        sa.Column("article_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mention_text", sa.String(500), nullable=False),
        sa.Column("start_offset", sa.Integer(), nullable=False),
        sa.Column("end_offset", sa.Integer(), nullable=False),
        sa.Column("confidence_score", sa.Numeric(5, 4)),
        sa.Column("context", sa.Text()),
        sa.CheckConstraint("start_offset >= 0", name="ck_entity_mention_entity_mention_start_nonnegative"),
        sa.CheckConstraint("end_offset >= start_offset", name="ck_entity_mention_entity_mention_offsets_ordered"),
        sa.CheckConstraint(
            "confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)",
            name="ck_entity_mention_entity_mention_confidence_range",
        ),
        sa.ForeignKeyConstraint(["article_id"], ["article.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["entity_id"], ["entity.id"], ondelete="RESTRICT"),
    )
    op.create_index("idx_entity_mention_article_id", "entity_mention", ["article_id"])
    op.create_index("idx_entity_mention_entity_id", "entity_mention", ["entity_id"])
    op.create_index("idx_entity_mention_text_trgm", "entity_mention", ["mention_text"], postgresql_using="gin", postgresql_ops={"mention_text": "gin_trgm_ops"})


def downgrade() -> None:
    op.drop_index("idx_entity_mention_text_trgm", table_name="entity_mention")
    op.drop_index("idx_entity_mention_entity_id", table_name="entity_mention")
    op.drop_index("idx_entity_mention_article_id", table_name="entity_mention")
    op.drop_table("entity_mention")
    op.drop_index("idx_entity_alias_alias_trgm", table_name="entity_alias")
    op.drop_index("idx_entity_alias_entity_id", table_name="entity_alias")
    op.drop_table("entity_alias")
    op.drop_index("idx_entity_metadata_gin", table_name="entity")
    op.drop_index("idx_entity_external_ids_gin", table_name="entity")
    op.drop_index("idx_entity_canonical_name_trgm", table_name="entity")
    op.drop_index("idx_entity_type", table_name="entity")
    op.drop_table("entity")
