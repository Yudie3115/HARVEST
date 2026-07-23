"""catalogue candidate idempotency

Revision ID: c4a912b6e307
Revises: fb29c18ac070
Create Date: 2026-07-23 00:00:00
"""
from typing import Sequence, Union

from alembic import op

revision: str = "c4a912b6e307"
down_revision: Union[str, Sequence[str], None] = "fb29c18ac070"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "uq_catalogue_entries_source_message",
        "catalogue_entries",
        ["source_message_id"],
        unique=True,
        postgresql_where="source_message_id IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_index(
        "uq_catalogue_entries_source_message",
        table_name="catalogue_entries",
    )
