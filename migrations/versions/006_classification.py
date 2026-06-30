"""classification

Revision ID: 006_classification
Revises: 005_taxonomy
Create Date: 2026-06-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "006_classification"
down_revision = "005_taxonomy"
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
        "classification",
        *audit_columns(),
        sa.Column("article_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("taxonomy_node_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("taxonomy_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", postgresql.ENUM(name="classification_status_enum", create_type=False), nullable=False, server_default="pending"),
        sa.Column("confidence_score", sa.Numeric(5, 4), nullable=False),
        sa.Column("classifier_name", sa.String(180)),
        sa.Column("rationale", sa.Text()),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.CheckConstraint("confidence_score >= 0 AND confidence_score <= 1", name="ck_classification_classification_confidence_range"),
        sa.ForeignKeyConstraint(["article_id"], ["article.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["taxonomy_node_id"], ["taxonomy_node.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["taxonomy_version_id"], ["taxonomy_version.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("article_id", "taxonomy_node_id", "taxonomy_version_id", name="uq_classification_article_node_version"),
    )
    op.create_index("idx_classification_article_id", "classification", ["article_id"])
    op.create_index("idx_classification_node_status", "classification", ["taxonomy_node_id", "status"])
    op.create_index("idx_classification_version_status", "classification", ["taxonomy_version_id", "status"])
    op.create_index("idx_classification_metadata_gin", "classification", ["metadata"], postgresql_using="gin")
    op.create_table(
        "classification_evidence",
        *audit_columns(),
        sa.Column("classification_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("quote", sa.Text()),
        sa.Column("start_offset", sa.Integer()),
        sa.Column("end_offset", sa.Integer()),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.CheckConstraint("start_offset IS NULL OR start_offset >= 0", name="ck_classification_evidence_classification_evidence_start_nonnegative"),
        sa.CheckConstraint("end_offset IS NULL OR end_offset >= 0", name="ck_classification_evidence_classification_evidence_end_nonnegative"),
        sa.ForeignKeyConstraint(["classification_id"], ["classification.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_classification_evidence_classification_id", "classification_evidence", ["classification_id"])
    op.create_index("idx_classification_evidence_payload_gin", "classification_evidence", ["payload"], postgresql_using="gin")


def downgrade() -> None:
    op.drop_index("idx_classification_evidence_payload_gin", table_name="classification_evidence")
    op.drop_index("idx_classification_evidence_classification_id", table_name="classification_evidence")
    op.drop_table("classification_evidence")
    op.drop_index("idx_classification_metadata_gin", table_name="classification")
    op.drop_index("idx_classification_version_status", table_name="classification")
    op.drop_index("idx_classification_node_status", table_name="classification")
    op.drop_index("idx_classification_article_id", table_name="classification")
    op.drop_table("classification")
