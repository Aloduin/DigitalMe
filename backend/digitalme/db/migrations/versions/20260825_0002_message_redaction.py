"""Add safe derived views for normalized messages.

Revision ID: 20260825_0002
Revises: 20260824_0001
Create Date: 2026-08-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260825_0002"
down_revision: str | Sequence[str] | None = "20260824_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Existing rows intentionally remain unclassified and have no redacted view. A safe
    # consumer must not fall back to normalized_text; re-importing regenerates the view.
    with op.batch_alter_table("messages") as batch_op:
        batch_op.add_column(sa.Column("redacted_text", sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column("redaction_spans", sa.JSON(), nullable=False, server_default="[]")
        )
        batch_op.add_column(
            sa.Column(
                "sensitivity",
                sa.String(length=32),
                nullable=False,
                server_default="unclassified",
            )
        )
        batch_op.create_index("ix_messages_sensitivity", ["sensitivity"])


def downgrade() -> None:
    with op.batch_alter_table("messages") as batch_op:
        batch_op.drop_index("ix_messages_sensitivity")
        batch_op.drop_column("sensitivity")
        batch_op.drop_column("redaction_spans")
        batch_op.drop_column("redacted_text")
