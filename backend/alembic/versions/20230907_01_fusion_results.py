"""Alembic migration: create fusion_results table for Phase 4 Weak Signal Fusion.

Revision ID: 20230907_01_fusion_results
Revises: edf169b872cd

NOTE (Phase 4 correction, documented): this migration never applied
successfully anywhere before Phase 4 (it shipped with an IndentationError
and, more importantly, declared asset_id as String(36) while the frozen
Phase 1 migration creates assets.id as UUID, so PostgreSQL rejected the
foreign key). It is rewritten here -- before any successful application --
to (a) use sa.UUID() for asset_id so the FK matches the frozen Phase 1
assets.id type, and (b) persist the five per-day weak-signal scores plus
the model version alongside the fusion scores. No live data is affected:
no database ever contained fusion_results before this revision applies.

Why per-signal columns on fusion_results instead of reusing
signal_contributions: signal_contributions is FK-bound to anomalies.id
(the Phase 1 anomaly-event table) and stores one row per contributing
sensor of a single anomaly event. Phase 4 needs one row per asset per
DAY holding five signal scores plus raw/smoothed fusion -- fabricating a
daily anomaly row per asset just to reuse that table would corrupt the
Phase 1 anomaly semantics. A dedicated fusion_results row per
(asset_id, day) is the correct grain, hence this table.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20230907_01_fusion_results"
down_revision = "edf169b872cd"
branch_labels = None
depends_on = None


def _score_check(name):
    return sa.CheckConstraint(
        f"{name} >= 0.0 AND {name} <= 1.0", name=f"ck_fusion_{name}_range"
    )


def upgrade():
    op.create_table(
        "fusion_results",
        sa.Column("id", sa.String(length=36), primary_key=True),
        # UUID to match frozen Phase 1 assets.id (see module docstring).
        sa.Column(
            "asset_id",
            sa.UUID(),
            sa.ForeignKey("assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("power_score", sa.Float(), nullable=False),
        sa.Column("brightness_score", sa.Float(), nullable=False),
        sa.Column("temperature_score", sa.Float(), nullable=False),
        sa.Column("maintenance_score", sa.Float(), nullable=False),
        sa.Column("neighbor_score", sa.Float(), nullable=False),
        sa.Column("raw_score", sa.Float(), nullable=False),
        sa.Column("smoothed_score", sa.Float(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("model_version", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("asset_id", "day", name="uq_fusion_asset_day"),
        _score_check("power_score"),
        _score_check("brightness_score"),
        _score_check("temperature_score"),
        _score_check("maintenance_score"),
        _score_check("neighbor_score"),
        sa.CheckConstraint(
            "raw_score >= 0.0 AND raw_score <= 1.0", name="ck_raw_score_range"
        ),
        sa.CheckConstraint(
            "smoothed_score >= 0.0 AND smoothed_score <= 1.0",
            name="ck_smoothed_score_range",
        ),
    )
    op.create_index(
        "ix_fusion_asset_day", "fusion_results", ["asset_id", "day"], unique=False
    )


def downgrade():
    op.drop_index("ix_fusion_asset_day", table_name="fusion_results")
    op.drop_table("fusion_results")
