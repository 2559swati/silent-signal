from sqlalchemy import Column, String, DateTime, ForeignKey, CheckConstraint

from sqlalchemy.orm import relationship
import uuid
from datetime import datetime
from app.core.db import Base


class TEEAnalysis(Base):
    __tablename__ = 'tee_analysis'

    __table_args__ = (
        CheckConstraint("mode IN ('demo', 'nitro')", name='check_tee_mode'),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    anomaly_id = Column(String(36), ForeignKey('anomalies.id', ondelete='CASCADE'), nullable=False)
    mode = Column(String, nullable=False)
    analyzed_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    result_summary = Column(String, nullable=False)

    anomaly = relationship("Anomaly", back_populates="tee_analyses")
