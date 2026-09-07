from sqlalchemy import Column, String, DateTime, ForeignKey

from sqlalchemy.orm import relationship
import uuid
from datetime import datetime
from app.core.db import Base


class MaintenanceRecord(Base):
    __tablename__ = 'maintenance_records'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    asset_id = Column(String(36), ForeignKey('assets.id', ondelete='CASCADE'), nullable=False)
    performed_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    description = Column(String, nullable=False)

    asset = relationship("Asset", back_populates="maintenance_records")
