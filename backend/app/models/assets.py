from sqlalchemy import Column, String, Integer, CheckConstraint, ForeignKey

from sqlalchemy.orm import relationship
import uuid
from app.core.db import Base


class Asset(Base):
    __tablename__ = 'assets'

    __table_args__ = (
        CheckConstraint('criticality >= 1 AND criticality <= 5', name='check_criticality_1_to_5'),
        CheckConstraint('public_exposure >= 1 AND public_exposure <= 5', name='check_public_exposure_1_to_5'),
        CheckConstraint("status IN ('healthy', 'watch', 'emerging', 'critical')", name='check_status'),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    external_code = Column(String, unique=True, nullable=False)
    criticality = Column(Integer, nullable=False)
    public_exposure = Column(Integer, nullable=False)
    status = Column(String, nullable=False)

    sensor_readings = relationship("SensorReading", back_populates="asset", cascade="all, delete-orphan")
    maintenance_records = relationship("MaintenanceRecord", back_populates="asset", cascade="all, delete-orphan")
    anomalies = relationship("Anomaly", back_populates="asset", cascade="all, delete-orphan")
    anomaly_results = relationship('AnomalyResult', back_populates='asset', cascade='all, delete-orphan')
    fusion_results = relationship('FusionResult', back_populates='asset', cascade='all, delete-orphan')
    risk_results = relationship('RiskResult', back_populates='asset', cascade='all, delete-orphan')
    explanation_results = relationship('ExplanationResult', back_populates='asset', cascade='all, delete-orphan')
    recommendation_results = relationship('RecommendationResult', back_populates='asset', cascade='all, delete-orphan')
    alert_results = relationship('AlertResult', back_populates='asset', cascade='all, delete-orphan')
