"""initial schema: episodic / semantic / procedural memory tables

Revision ID: 0001
Revises:
Create Date: 2026-08-02
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "episodic_memory",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("namespace", sa.String(length=128), nullable=False, index=True),
        sa.Column("session_id", sa.String(length=128), nullable=True, index=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("importance", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("access_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=True),
    )
    op.create_table(
        "semantic_memory",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("namespace", sa.String(length=128), nullable=False, index=True),
        sa.Column("subject", sa.String(length=256), nullable=False, index=True),
        sa.Column("fact", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("source_episode_ids", sa.JSON(), nullable=True),
        sa.Column("access_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "procedural_memory",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("namespace", sa.String(length=128), nullable=False, index=True),
        sa.Column("trigger_condition", sa.Text(), nullable=False),
        sa.Column("steps", sa.JSON(), nullable=True),
        sa.Column("success_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("procedural_memory")
    op.drop_table("semantic_memory")
    op.drop_table("episodic_memory")
