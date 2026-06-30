"""taxonomy

Revision ID: 005_taxonomy
Revises: 004_events
Create Date: 2026-06-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "005_taxonomy"
down_revision = "004_events"
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
        "taxonomy_version",
        *audit_columns(),
        sa.Column("name", sa.String(180), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.UniqueConstraint("name", "version_number", name="uq_taxonomy_version_name_number"),
    )
    op.create_index(
        "uq_taxonomy_version_current",
        "taxonomy_version",
        ["name"],
        unique=True,
        postgresql_where=sa.text("is_current = true AND deleted_at IS NULL"),
    )
    op.create_table(
        "taxonomy_node",
        *audit_columns(),
        sa.Column("taxonomy_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True)),
        sa.Column("code", sa.String(120), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("path", sa.String(1000), nullable=False),
        sa.Column("depth", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.CheckConstraint("depth >= 0", name="ck_taxonomy_node_taxonomy_node_depth_nonnegative"),
        sa.ForeignKeyConstraint(["taxonomy_version_id"], ["taxonomy_version.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["parent_id"], ["taxonomy_node.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("taxonomy_version_id", "code", name="uq_taxonomy_node_version_code"),
    )
    op.create_index("idx_taxonomy_node_version_parent", "taxonomy_node", ["taxonomy_version_id", "parent_id"])
    op.create_index("idx_taxonomy_node_path", "taxonomy_node", ["path"])
    op.create_index("idx_taxonomy_node_name_trgm", "taxonomy_node", ["name"], postgresql_using="gin", postgresql_ops={"name": "gin_trgm_ops"})
    op.create_index("idx_taxonomy_node_metadata_gin", "taxonomy_node", ["metadata"], postgresql_using="gin")


def downgrade() -> None:
    op.drop_index("idx_taxonomy_node_metadata_gin", table_name="taxonomy_node")
    op.drop_index("idx_taxonomy_node_name_trgm", table_name="taxonomy_node")
    op.drop_index("idx_taxonomy_node_path", table_name="taxonomy_node")
    op.drop_index("idx_taxonomy_node_version_parent", table_name="taxonomy_node")
    op.drop_table("taxonomy_node")
    op.drop_index("uq_taxonomy_version_current", table_name="taxonomy_version")
    op.drop_table("taxonomy_version")
