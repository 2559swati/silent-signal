"""Alembic migration: create alert_results table for Phase 9 Alert Engine.

Revision ID: alert_results_v1
Revises: recommendation_results_v1

One row per (asset_id, day, alert_type) holding deterministic actionable
alerts over existing Phase 3-7 evidence. No existing tables are modified;
no data is touched. asset_id uses sa.UUID() to match the frozen Phase 1
assets.id type (same pattern as the fusion/risk/explanation/
recommendation migrations).
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "alert_results_v1"
down_revision = "recommendation_results_v1"
branch_labels = None
depends_on = None


def _score_check(name):
    return sa.CheckConstraint(
        f"{name} >= 0.0 AND {name} <= 1.0", name=f"ck_alert_{name}_range"
    )


def upgrade():
    op.create_table(
        "alert_results",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "asset_id",
            sa.UUID(),
            sa.ForeignKey("assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("alert_type", sa.String(), nullable=False),
        sa.Column("severity", sa.String(), nullable=False),
        sa.Column("priority", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("risk_score", sa.Float(), nullable=False),
        sa.Column("fusion_score", sa.Float(), nullable=False),
        sa.Column("anomaly_score", sa.Float(), nullable=False),
        sa.Column("persistence_score", sa.Float(), nullable=False),
        sa.Column("persistence_streak", sa.Integer(), nullable=False),
        sa.Column("acknowledged", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("model_version", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("asset_id", "day", "alert_type", name="uq_alert_asset_day_type"),
        _score_check("risk_score"),
        _score_check("fusion_score"),
        _score_check("anomaly_score"),
        _score_check("persistence_score"),
    )
    op.create_index(
        "ix_alert_asset_day", "alert_results", ["asset_id", "day"], unique=False
    )


def downgrade():
    op.drop_index("ix_alert_asset_day", table_name="alert_results")
    op.drop_table("alert_results")
