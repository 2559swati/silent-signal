from sqlalchemy import Column, String, Float, ForeignKey, CheckConstraint

from sqlalchemy.orm import relationship
import uuid
from app.core.db import Base


class SignalContribution(Base):
    __tablename__ = 'signal_contributions'

    __table_args__ = (
        CheckConstraint('contribution_score >= 0.0 AND contribution_score <= 1.0', name='check_contribution_score_0_to_1'),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    anomaly_id = Column(String(36), ForeignKey('anomalies.id', ondelete='CASCADE'), nullable=False)
    sensor_type = Column(String, nullable=False)
    contribution_score = Column(Float, nullable=False)

    anomaly = relationship("Anomaly", back_populates="signal_contributions")
