"""persist chat follow-up suggestions

Revision ID: 4f2d1c8a9b70
Revises: c4a912b6e307
Create Date: 2026-07-24 00:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "4f2d1c8a9b70"
down_revision: Union[str, Sequence[str], None] = "c4a912b6e307"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "chat_messages",
        sa.Column(
            "suggested_questions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("chat_messages", "suggested_questions")
