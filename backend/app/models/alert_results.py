from sqlalchemy import Column, String, Float, Integer, Date, DateTime, Boolean, Text, ForeignKey, UniqueConstraint, CheckConstraint, Index
import uuid
from datetime import datetime
from app.core.db import Base
from sqlalchemy.orm import relationship


class AlertResult(Base):
    """Phase 9 persisted alert: one row per (asset_id, day, alert_type).

    Deterministic actionable alerts derived from existing Phase 3-7
    evidence. Mirrors alembic revision alert_results_v1.
    """

    __tablename__ = 'alert_results'

    __table_args__ = (
        UniqueConstraint('asset_id', 'day', 'alert_type', name='uq_alert_asset_day_type'),
        CheckConstraint('risk_score >= 0.0 AND risk_score <= 1.0', name='ck_alert_risk_range'),
        CheckConstraint('fusion_score >= 0.0 AND fusion_score <= 1.0', name='ck_alert_fusion_range'),
        CheckConstraint('anomaly_score >= 0.0 AND anomaly_score <= 1.0', name='ck_alert_anomaly_range'),
        CheckConstraint('persistence_score >= 0.0 AND persistence_score <= 1.0', name='ck_alert_persist_range'),
        Index('ix_alert_asset_day', 'asset_id', 'day'),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    asset_id = Column(String(36), ForeignKey('assets.id', ondelete='CASCADE'), nullable=False)
    day = Column(Date, nullable=False)
    alert_type = Column(String, nullable=False)
    severity = Column(String, nullable=False)
    priority = Column(String, nullable=False)
    title = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    risk_score = Column(Float, nullable=False)
    fusion_score = Column(Float, nullable=False)
    anomaly_score = Column(Float, nullable=False)
    persistence_score = Column(Float, nullable=False)
    persistence_streak = Column(Integer, nullable=False)
    acknowledged = Column(Boolean, nullable=False, default=False)
    model_version = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    asset = relationship('Asset', back_populates='alert_results')
