"""add purchase_date to positions

Revision ID: e46b80eaf586
Revises: 0002
Create Date: 2026-05-20 14:42:30.077209

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0003'
down_revision: Union[str, None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('positions', sa.Column('purchase_date', sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column('positions', 'purchase_date')
