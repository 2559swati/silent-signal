from sqlalchemy import Column, String, Float, DateTime, ForeignKey, CheckConstraint, UniqueConstraint
import uuid
from datetime import datetime
from app.core.db import Base
from sqlalchemy.orm import relationship


class Anomaly(Base):
    __tablename__ = 'anomalies'

    __table_args__ = (
        CheckConstraint("status IN ('NORMAL', 'WATCH', 'EMERGING', 'CRITICAL')", name='check_anomaly_status'),
        CheckConstraint("priority IN ('P1', 'P2', 'P3', 'P4')", name='check_anomaly_priority'),
        CheckConstraint('score >= 0.0 AND score <= 1.0', name='check_anomaly_score_0_to_1'),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    asset_id = Column(String(36), ForeignKey('assets.id', ondelete='CASCADE'), nullable=False)
    detected_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    status = Column(String, nullable=False)
    priority = Column(String, nullable=False)
    score = Column(Float, nullable=False)

    asset = relationship("Asset", back_populates="anomalies")
    signal_contributions = relationship("SignalContribution", back_populates="anomaly", cascade="all, delete-orphan")
    recommendations = relationship("Recommendation", back_populates="anomaly", cascade="all, delete-orphan")
    tee_analyses = relationship("TEEAnalysis", back_populates="anomaly", cascade="all, delete-orphan")

class AnomalyResult(Base):
    __tablename__ = 'anomaly_results'

    __table_args__ = (
        UniqueConstraint('asset_id', 'scored_at', name='uq_asset_scored_at'),
        CheckConstraint('score >= 0.0 AND score <= 1.0', name='check_score_range'),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    asset_id = Column(String(36), ForeignKey('assets.id', ondelete='CASCADE'), nullable=False)
    scored_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    score = Column(Float, nullable=False)
    model_version = Column(String, nullable=False)

    asset = relationship('Asset', back_populates='anomaly_results')
