"""Alembic migration: create recommendation_results table for Phase 7.

Revision ID: recommendation_results_v1
Revises: explain_results_v1

One row per (asset_id, day) holding deterministic rule-based preventive
recommendations over existing Phase 4/5/6 evidence. No existing tables are
modified; no data is touched.

Why a new table instead of reusing recommendations: the Phase 1
recommendations table is FK-bound to anomalies.id (one row per contributing
action of a single anomaly event). Phase 7 needs one row per asset per day
independent of anomaly events -- fabricating daily anomaly rows to reuse
that table would corrupt Phase 1 semantics. Same rationale as the
fusion/risk/explanation tables. asset_id uses sa.UUID() to match the
frozen Phase 1 assets.id type.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "recommendation_results_v1"
down_revision = "explain_results_v1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "recommendation_results",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "asset_id",
            sa.UUID(),
            sa.ForeignKey("assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("risk_score", sa.Float(), nullable=False),
        sa.Column("risk_level", sa.String(), nullable=False),
        sa.Column("priority", sa.String(), nullable=False),
        sa.Column("urgency", sa.String(), nullable=False),
        sa.Column("recommendations_json", sa.Text(), nullable=False),
        sa.Column("evidence_json", sa.Text(), nullable=False),
        sa.Column("model_version", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("asset_id", "day", name="uq_recommend_asset_day"),
        sa.CheckConstraint(
            "risk_score >= 0.0 AND risk_score <= 1.0",
            name="ck_recommend_risk_range",
        ),
    )
    op.create_index(
        "ix_recommend_asset_day", "recommendation_results", ["asset_id", "day"], unique=False
    )


def downgrade():
    op.drop_index("ix_recommend_asset_day", table_name="recommendation_results")
    op.drop_table("recommendation_results")
