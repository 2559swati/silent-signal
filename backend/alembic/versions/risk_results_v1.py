"""Alembic migration: create risk_results table for Phase 5 Risk Engine.

Revision ID: risk_results_v1
Revises: 20230907_01_fusion_results

One row per (asset_id, day) holding the Phase 5 risk derivation from
existing Phase 3/4 evidence. No existing tables are modified; no data is
touched. asset_id uses sa.UUID() to match the frozen Phase 1 assets.id
type (same pattern as the fusion_results migration).
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "risk_results_v1"
down_revision = "20230907_01_fusion_results"
branch_labels = None
depends_on = None


def _score_check(name):
    return sa.CheckConstraint(
        f"{name} >= 0.0 AND {name} <= 1.0", name=f"ck_risk_{name}_range"
    )


def upgrade():
    op.create_table(
        "risk_results",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "asset_id",
            sa.UUID(),
            sa.ForeignKey("assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("anomaly_score", sa.Float(), nullable=False),
        sa.Column("fusion_score", sa.Float(), nullable=False),
        sa.Column("smoothed_fusion_score", sa.Float(), nullable=False),
        sa.Column("persistence_score", sa.Float(), nullable=False),
        sa.Column("risk_score", sa.Float(), nullable=False),
        sa.Column("risk_level", sa.String(), nullable=False),
        sa.Column("model_version", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("asset_id", "day", name="uq_risk_asset_day"),
        _score_check("anomaly_score"),
        _score_check("fusion_score"),
        _score_check("smoothed_fusion_score"),
        _score_check("persistence_score"),
        _score_check("risk_score"),
    )
    op.create_index(
        "ix_risk_asset_day", "risk_results", ["asset_id", "day"], unique=False
    )


def downgrade():
    op.drop_index("ix_risk_asset_day", table_name="risk_results")
    op.drop_table("risk_results")
