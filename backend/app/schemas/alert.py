from datetime import date
from typing import List
from pydantic import BaseModel, ConfigDict, Field


class AlertItem(BaseModel):
    day: date = Field(..., description="Alert calendar day")
    alert_type: str = Field(..., description="CRITICAL_RISK | SUSTAINED_RISK | RISK_ESCALATION | EMERGING_ANOMALY | SIGNAL_CONVERGENCE")
    severity: str = Field(..., description="LOW | MEDIUM | HIGH | CRITICAL (Phase 5 thresholds)")
    priority: str = Field(..., description="LOW | MEDIUM | HIGH | URGENT")
    title: str = Field(..., description="Short deterministic alert title")
    message: str = Field(..., description="Evidence-based alert message")
    risk_score: float = Field(..., ge=0.0, le=1.0)
    fusion_score: float = Field(..., ge=0.0, le=1.0)
    anomaly_score: float = Field(..., ge=0.0, le=1.0)
    persistence_score: float = Field(..., ge=0.0, le=1.0)
    persistence_streak: int = Field(..., ge=0, description="Consecutive elevated days from Phase 6 evidence")
    acknowledged: bool = Field(..., description="Whether the alert was acknowledged")
    model_version: str = Field(..., description="Alert model version")

    model_config = ConfigDict(from_attributes=True)


class AssetAlertsResponse(BaseModel):
    """Phase 9 alerts for one asset (latest actionable day)."""

    asset_id: str = Field(..., description="Asset UUID")
    asset_external_code: str = Field(..., description="Asset external code (e.g. SL-1042)")
    day: date = Field(..., description="Latest alert calendar day")
    alerts: List[AlertItem] = Field(..., description="Alerts for the latest day with alerts")
    total_alerts: int = Field(..., description="Number of alerts on the latest alert day")
    model_version: str = Field(..., description="Alert model version")

    model_config = ConfigDict(from_attributes=True)


class FleetAlertItem(AlertItem):
    asset_id: str = Field(..., description="Asset UUID")
    asset_external_code: str = Field(..., description="Asset external code")

    model_config = ConfigDict(from_attributes=True)


class FleetAlertsResponse(BaseModel):
    """Current actionable alerts across the fleet (latest alert day)."""

    day: date = Field(..., description="Latest calendar day with alerts")
    alerts: List[FleetAlertItem] = Field(..., description="Alerts ordered by severity, risk score")
    total_alerts: int = Field(..., description="Number of current actionable alerts")
    model_version: str = Field(..., description="Alert model version")

    model_config = ConfigDict(from_attributes=True)
