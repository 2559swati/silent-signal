"""Alembic migration: create explanation_results table for Phase 6 Explainability.

Revision ID: explain_results_v1
Revises: risk_results_v1

One row per (asset_id, day) holding the deterministic rule-based
explanation of existing Phase 3/4/5 evidence. No existing tables are
modified; no data is touched. asset_id uses sa.UUID() to match the frozen
Phase 1 assets.id type (same pattern as the fusion/risk migrations).
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "explain_results_v1"
down_revision = "risk_results_v1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "explanation_results",
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
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("factors_json", sa.Text(), nullable=False),
        sa.Column("evidence_json", sa.Text(), nullable=False),
        sa.Column("model_version", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("asset_id", "day", name="uq_explain_asset_day"),
        sa.CheckConstraint(
            "risk_score >= 0.0 AND risk_score <= 1.0",
            name="ck_explain_risk_range",
        ),
    )
    op.create_index(
        "ix_explain_asset_day", "explanation_results", ["asset_id", "day"], unique=False
    )


def downgrade():
    op.drop_index("ix_explain_asset_day", table_name="explanation_results")
    op.drop_table("explanation_results")
