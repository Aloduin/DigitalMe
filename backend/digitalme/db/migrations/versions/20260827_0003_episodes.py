"""Add deterministic episode segments and message evidence links.

Revision ID: 20260827_0003
Revises: 20260825_0002
Create Date: 2026-08-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260827_0003"
down_revision: str | Sequence[str] | None = "20260825_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "episodes",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("pipeline_version", sa.String(length=64), nullable=False),
        sa.Column("segment_index", sa.Integer(), nullable=False),
        sa.Column("episode_type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("extraction_status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "session_id",
            "pipeline_version",
            "segment_index",
            name="uq_episodes_session_pipeline_segment",
        ),
    )
    op.create_index("ix_episodes_extraction_status", "episodes", ["extraction_status"])
    op.create_index("ix_episodes_pipeline_version", "episodes", ["pipeline_version"])
    op.create_index("ix_episodes_session_id", "episodes", ["session_id"])
    op.create_index("ix_episodes_start_at", "episodes", ["start_at"])

    op.create_table(
        "episode_messages",
        sa.Column("episode_id", sa.String(length=64), nullable=False),
        sa.Column("message_id", sa.String(length=64), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["episode_id"], ["episodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("episode_id", "message_id"),
        sa.UniqueConstraint("episode_id", "position", name="uq_episode_messages_position"),
    )
    op.create_index("ix_episode_messages_message_id", "episode_messages", ["message_id"])


def downgrade() -> None:
    op.drop_index("ix_episode_messages_message_id", table_name="episode_messages")
    op.drop_table("episode_messages")
    op.drop_index("ix_episodes_start_at", table_name="episodes")
    op.drop_index("ix_episodes_session_id", table_name="episodes")
    op.drop_index("ix_episodes_pipeline_version", table_name="episodes")
    op.drop_index("ix_episodes_extraction_status", table_name="episodes")
    op.drop_table("episodes")
