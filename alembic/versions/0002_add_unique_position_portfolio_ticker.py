"""add unique constraint on positions(portfolio_id, ticker)

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-18
"""

import sqlalchemy as sa

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Remove any duplicate (portfolio_id, ticker) rows keeping the latest id before adding the constraint.
    op.execute(
        """
        DELETE FROM positions
        WHERE id NOT IN (
            SELECT MAX(id)
            FROM positions
            GROUP BY portfolio_id, ticker
        )
        """
    )
    op.create_unique_constraint("uq_position_portfolio_ticker", "positions", ["portfolio_id", "ticker"])


def downgrade() -> None:
    op.drop_constraint("uq_position_portfolio_ticker", "positions", type_="unique")
