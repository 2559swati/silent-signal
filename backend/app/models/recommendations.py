from sqlalchemy import Column, String, ForeignKey

from sqlalchemy.orm import relationship
import uuid
from app.core.db import Base


class Recommendation(Base):
    __tablename__ = 'recommendations'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    anomaly_id = Column(String(36), ForeignKey('anomalies.id', ondelete='CASCADE'), nullable=False)
    action_type = Column(String, nullable=False)
    description = Column(String, nullable=False)

    anomaly = relationship("Anomaly", back_populates="recommendations")
