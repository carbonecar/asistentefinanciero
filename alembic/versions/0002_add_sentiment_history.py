"""add sentiment_history table

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-17
"""

import sqlalchemy as sa

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sentiment_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("label", sa.String(10), nullable=False),
        sa.Column("article_count", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ticker", "date", name="uq_sentiment_ticker_date"),
    )
    op.create_index("ix_sentiment_ticker", "sentiment_history", ["ticker"])
    op.create_index("ix_sentiment_date", "sentiment_history", ["date"])


def downgrade() -> None:
    op.drop_index("ix_sentiment_date", table_name="sentiment_history")
    op.drop_index("ix_sentiment_ticker", table_name="sentiment_history")
    op.drop_table("sentiment_history")
