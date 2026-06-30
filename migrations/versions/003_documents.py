"""documents

Revision ID: 003_documents
Revises: 002_collection
Create Date: 2026-06-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "003_documents"
down_revision = "002_collection"
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
        "raw_document",
        *audit_columns(),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fetch_log_id", postgresql.UUID(as_uuid=True)),
        sa.Column("uri", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(128), nullable=False),
        sa.Column("content_type", sa.String(120)),
        sa.Column("storage_url", sa.Text()),
        sa.Column("inline_content", sa.Text()),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.ForeignKeyConstraint(["source_id"], ["source.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["fetch_log_id"], ["fetch_log.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("content_hash", name="uq_raw_document_content_hash"),
    )
    op.create_index("idx_raw_document_source_received_at", "raw_document", ["source_id", "received_at"])
    op.create_index("idx_raw_document_fetch_log_id", "raw_document", ["fetch_log_id"])
    op.create_index("idx_raw_document_metadata_gin", "raw_document", ["metadata"], postgresql_using="gin")
    op.create_table(
        "article",
        *audit_columns(),
        sa.Column("raw_document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("summary", sa.Text()),
        sa.Column("content_plain", sa.Text(), nullable=False),
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column("language_code", sa.String(12), nullable=False, server_default="und"),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("word_count", sa.Integer()),
        sa.Column("search_vector", postgresql.TSVECTOR()),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.CheckConstraint("word_count IS NULL OR word_count >= 0", name="ck_article_article_word_count_nonnegative"),
        sa.ForeignKeyConstraint(["raw_document_id"], ["raw_document.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_id"], ["source.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("raw_document_id", name="uq_article_raw_document_id"),
        sa.UniqueConstraint("canonical_url", name="uq_article_canonical_url"),
    )
    op.create_index("idx_article_source_published_at", "article", ["source_id", "published_at"])
    op.create_index("idx_article_published_at", "article", ["published_at"])
    op.create_index("idx_article_title_trgm", "article", ["title"], postgresql_using="gin", postgresql_ops={"title": "gin_trgm_ops"})
    op.create_index("idx_article_search_vector_gin", "article", ["search_vector"], postgresql_using="gin")
    op.create_index("idx_article_metadata_gin", "article", ["metadata"], postgresql_using="gin")


def downgrade() -> None:
    op.drop_index("idx_article_metadata_gin", table_name="article")
    op.drop_index("idx_article_search_vector_gin", table_name="article")
    op.drop_index("idx_article_title_trgm", table_name="article")
    op.drop_index("idx_article_published_at", table_name="article")
    op.drop_index("idx_article_source_published_at", table_name="article")
    op.drop_table("article")
    op.drop_index("idx_raw_document_metadata_gin", table_name="raw_document")
    op.drop_index("idx_raw_document_fetch_log_id", table_name="raw_document")
    op.drop_index("idx_raw_document_source_received_at", table_name="raw_document")
    op.drop_table("raw_document")
