from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Index

from sqlalchemy.orm import relationship
import uuid
from datetime import datetime
from app.core.db import Base


class SensorReading(Base):
    __tablename__ = 'sensor_readings'

    __table_args__ = (
        Index('ix_sensor_readings_asset_recorded', 'asset_id', 'recorded_at'),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    asset_id = Column(String(36), ForeignKey('assets.id', ondelete='CASCADE'), nullable=False)
    recorded_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    sensor_type = Column(String, nullable=False)
    value = Column(Float, nullable=False)

    asset = relationship("Asset", back_populates="sensor_readings")
