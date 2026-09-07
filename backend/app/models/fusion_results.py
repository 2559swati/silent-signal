from sqlalchemy import Column, String, Float, Date, DateTime, ForeignKey, UniqueConstraint, CheckConstraint, Index
import uuid
from datetime import datetime
from app.core.db import Base
from sqlalchemy.orm import relationship


def _score_check(name):
    return CheckConstraint(f"{name} >= 0.0 AND {name} <= 1.0", name=f"ck_fusion_{name}_range")


class FusionResult(Base):
    """Phase 4 persisted result: one row per (asset_id, day).

    Holds the five normalized weak-signal scores plus the fused raw and
    EMA-smoothed scores, the confirmed status and the model version.
    Mirrors alembic revision 20230907_01_fusion_results.
    """

    __tablename__ = 'fusion_results'

    __table_args__ = (
        UniqueConstraint('asset_id', 'day', name='uq_fusion_asset_day'),
        _score_check('power_score'),
        _score_check('brightness_score'),
        _score_check('temperature_score'),
        _score_check('maintenance_score'),
        _score_check('neighbor_score'),
        CheckConstraint('raw_score >= 0.0 AND raw_score <= 1.0', name='ck_raw_score_range'),
        CheckConstraint('smoothed_score >= 0.0 AND smoothed_score <= 1.0', name='ck_smoothed_score_range'),
        Index('ix_fusion_asset_day', 'asset_id', 'day'),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    asset_id = Column(String(36), ForeignKey('assets.id', ondelete='CASCADE'), nullable=False)
    day = Column(Date, nullable=False)
    power_score = Column(Float, nullable=False)
    brightness_score = Column(Float, nullable=False)
    temperature_score = Column(Float, nullable=False)
    maintenance_score = Column(Float, nullable=False)
    neighbor_score = Column(Float, nullable=False)
    raw_score = Column(Float, nullable=False)
    smoothed_score = Column(Float, nullable=False)
    status = Column(String, nullable=False)
    model_version = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    asset = relationship('Asset', back_populates='fusion_results')
