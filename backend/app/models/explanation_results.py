from sqlalchemy import Column, String, Float, Date, DateTime, Text, ForeignKey, UniqueConstraint, CheckConstraint, Index
import uuid
from datetime import datetime
from app.core.db import Base
from sqlalchemy.orm import relationship


class ExplanationResult(Base):
    """Phase 6 persisted result: one row per (asset_id, day).

    Rule-based interpretation of existing Phase 3/4/5 evidence. factors_json
    holds the deterministically ordered factor list; evidence_json holds the
    input evidence snapshot (including the temperature-proxy honesty note).
    Mirrors alembic revision explain_results_v1.
    """

    __tablename__ = 'explanation_results'

    __table_args__ = (
        UniqueConstraint('asset_id', 'day', name='uq_explain_asset_day'),
        CheckConstraint('risk_score >= 0.0 AND risk_score <= 1.0', name='ck_explain_risk_range'),
        Index('ix_explain_asset_day', 'asset_id', 'day'),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    asset_id = Column(String(36), ForeignKey('assets.id', ondelete='CASCADE'), nullable=False)
    day = Column(Date, nullable=False)
    risk_score = Column(Float, nullable=False)
    risk_level = Column(String, nullable=False)
    summary = Column(Text, nullable=False)
    factors_json = Column(Text, nullable=False)
    evidence_json = Column(Text, nullable=False)
    model_version = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    asset = relationship('Asset', back_populates='explanation_results')
