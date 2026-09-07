from sqlalchemy import Column, String, Float, Date, DateTime, ForeignKey, UniqueConstraint, CheckConstraint, Index
import uuid
from datetime import datetime
from app.core.db import Base
from sqlalchemy.orm import relationship


def _score_check(name):
    return CheckConstraint(f"{name} >= 0.0 AND {name} <= 1.0", name=f"ck_risk_{name}_range")


class RiskResult(Base):
    """Phase 5 persisted result: one row per (asset_id, day).

    Derives risk from existing Phase 3/4 evidence: the Phase 3 anomaly
    score, Phase 4 raw + smoothed fusion, and a deterministic persistence
    score computed from the Phase 4 confirmed-status timeline.
    Mirrors alembic revision risk_results_v1.
    """

    __tablename__ = 'risk_results'

    __table_args__ = (
        UniqueConstraint('asset_id', 'day', name='uq_risk_asset_day'),
        _score_check('anomaly_score'),
        _score_check('fusion_score'),
        _score_check('smoothed_fusion_score'),
        _score_check('persistence_score'),
        _score_check('risk_score'),
        Index('ix_risk_asset_day', 'asset_id', 'day'),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    asset_id = Column(String(36), ForeignKey('assets.id', ondelete='CASCADE'), nullable=False)
    day = Column(Date, nullable=False)
    anomaly_score = Column(Float, nullable=False)
    fusion_score = Column(Float, nullable=False)
    smoothed_fusion_score = Column(Float, nullable=False)
    persistence_score = Column(Float, nullable=False)
    risk_score = Column(Float, nullable=False)
    risk_level = Column(String, nullable=False)
    model_version = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    asset = relationship('Asset', back_populates='risk_results')
