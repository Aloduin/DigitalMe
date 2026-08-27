"""Add semantic Episode fields and evidence-linked Memory Candidates.

Revision ID: 20260827_0004
Revises: 20260827_0003
Create Date: 2026-08-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260827_0004"
down_revision: str | Sequence[str] | None = "20260827_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("episodes") as batch_op:
        batch_op.add_column(sa.Column("projects", sa.JSON(), nullable=False, server_default="[]"))
        batch_op.add_column(sa.Column("decisions", sa.JSON(), nullable=False, server_default="[]"))
        batch_op.add_column(
            sa.Column("open_questions", sa.JSON(), nullable=False, server_default="[]")
        )

    op.create_table(
        "memory_candidates",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("episode_id", sa.String(length=64), nullable=False),
        sa.Column("extractor_version", sa.String(length=64), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("candidate_type", sa.String(length=64), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("scope", sa.String(length=255), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("salience", sa.Float(), nullable=False),
        sa.Column("evidence_strength", sa.String(length=8), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("sensitivity", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["episode_id"], ["episodes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_memory_candidates_candidate_type", "memory_candidates", ["candidate_type"])
    op.create_index("ix_memory_candidates_content_hash", "memory_candidates", ["content_hash"])
    op.create_index("ix_memory_candidates_episode_id", "memory_candidates", ["episode_id"])
    op.create_index(
        "ix_memory_candidates_evidence_strength", "memory_candidates", ["evidence_strength"]
    )
    op.create_index(
        "ix_memory_candidates_extractor_version", "memory_candidates", ["extractor_version"]
    )
    op.create_index("ix_memory_candidates_scope", "memory_candidates", ["scope"])
    op.create_index("ix_memory_candidates_sensitivity", "memory_candidates", ["sensitivity"])
    op.create_index("ix_memory_candidates_status", "memory_candidates", ["status"])

    op.create_table(
        "candidate_evidence",
        sa.Column("candidate_id", sa.String(length=64), nullable=False),
        sa.Column("message_id", sa.String(length=64), nullable=False),
        sa.Column("quote_snapshot", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["candidate_id"], ["memory_candidates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("candidate_id", "message_id"),
    )
    op.create_index("ix_candidate_evidence_message_id", "candidate_evidence", ["message_id"])


def downgrade() -> None:
    op.drop_index("ix_candidate_evidence_message_id", table_name="candidate_evidence")
    op.drop_table("candidate_evidence")
    op.drop_index("ix_memory_candidates_status", table_name="memory_candidates")
    op.drop_index("ix_memory_candidates_sensitivity", table_name="memory_candidates")
    op.drop_index("ix_memory_candidates_scope", table_name="memory_candidates")
    op.drop_index("ix_memory_candidates_extractor_version", table_name="memory_candidates")
    op.drop_index("ix_memory_candidates_evidence_strength", table_name="memory_candidates")
    op.drop_index("ix_memory_candidates_episode_id", table_name="memory_candidates")
    op.drop_index("ix_memory_candidates_content_hash", table_name="memory_candidates")
    op.drop_index("ix_memory_candidates_candidate_type", table_name="memory_candidates")
    op.drop_table("memory_candidates")
    with op.batch_alter_table("episodes") as batch_op:
        batch_op.drop_column("open_questions")
        batch_op.drop_column("decisions")
        batch_op.drop_column("projects")
