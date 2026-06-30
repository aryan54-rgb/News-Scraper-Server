"""source registry source type flexibility

Revision ID: 009_source_registry_source_type_flexibility
Revises: 008_keywords
Create Date: 2026-06-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "009_source_registry_source_type_flexibility"
down_revision = "008_keywords"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("source_type", sa.Column("slug", sa.String(length=80), nullable=True))
    op.add_column("source_type", sa.Column("collector_key", sa.String(length=120), nullable=True))
    op.add_column(
        "source_type",
        sa.Column("capabilities", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )
    op.add_column(
        "source_type",
        sa.Column("config_schema", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.add_column(
        "source_type",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.execute("UPDATE source_type SET slug = replace(lower(name), ' ', '_') WHERE slug IS NULL")
    op.alter_column("source_type", "slug", nullable=False)
    op.drop_constraint("uq_source_type_code", "source_type", type_="unique")
    op.create_unique_constraint("uq_source_type_slug", "source_type", ["slug"])


def downgrade() -> None:
    op.drop_constraint("uq_source_type_slug", "source_type", type_="unique")
    op.create_unique_constraint("uq_source_type_code", "source_type", ["code"])
    op.drop_column("source_type", "is_active")
    op.drop_column("source_type", "config_schema")
    op.drop_column("source_type", "capabilities")
    op.drop_column("source_type", "collector_key")
    op.drop_column("source_type", "slug")

