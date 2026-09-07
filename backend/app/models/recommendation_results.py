from sqlalchemy import Column, String, Float, Date, DateTime, Text, ForeignKey, UniqueConstraint, CheckConstraint, Index
import uuid
from datetime import datetime
from app.core.db import Base
from sqlalchemy.orm import relationship


class RecommendationResult(Base):
    """Phase 7 persisted result: one row per (asset_id, day).

    Deterministic rule-based preventive recommendations derived from
    existing Phase 4/5/6 evidence. recommendations_json holds the ordered
    action list; evidence_json holds the input evidence snapshot.
    Mirrors alembic revision recommendation_results_v1.
    """

    __tablename__ = 'recommendation_results'

    __table_args__ = (
        UniqueConstraint('asset_id', 'day', name='uq_recommend_asset_day'),
        CheckConstraint('risk_score >= 0.0 AND risk_score <= 1.0', name='ck_recommend_risk_range'),
        Index('ix_recommend_asset_day', 'asset_id', 'day'),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    asset_id = Column(String(36), ForeignKey('assets.id', ondelete='CASCADE'), nullable=False)
    day = Column(Date, nullable=False)
    risk_score = Column(Float, nullable=False)
    risk_level = Column(String, nullable=False)
    priority = Column(String, nullable=False)
    urgency = Column(String, nullable=False)
    recommendations_json = Column(Text, nullable=False)
    evidence_json = Column(Text, nullable=False)
    model_version = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    asset = relationship('Asset', back_populates='recommendation_results')
