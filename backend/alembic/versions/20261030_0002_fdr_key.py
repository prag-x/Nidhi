"""Normalised FDR number for fast duplicate detection.

Revision ID: 0002_fdr_key
Revises: 0001_nidhi
"""

import sqlalchemy as sa

from alembic import op

revision: str = "0002_fdr_key"
down_revision: str | None = "0001_nidhi"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("instruments") as batch:
        batch.add_column(sa.Column("fdr_key", sa.String(length=40), nullable=True))
        batch.create_index("ix_instruments_fdr_key", ["fdr_key"])
    from app.services.checks import _norm_fdr

    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, fdr_number FROM instruments")).all()
    for rid, fdr in rows:
        conn.execute(sa.text("UPDATE instruments SET fdr_key = :k WHERE id = :i"), {"k": _norm_fdr(fdr), "i": rid})


def downgrade() -> None:
    with op.batch_alter_table("instruments") as batch:
        batch.drop_index("ix_instruments_fdr_key")
        batch.drop_column("fdr_key")
