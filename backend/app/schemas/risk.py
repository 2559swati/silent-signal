from datetime import date
from pydantic import BaseModel, ConfigDict, Field


class RiskResponse(BaseModel):
    """Phase 5 risk result for one asset (latest scored day)."""

    asset_id: str = Field(..., description="Asset UUID")
    asset_external_code: str = Field(..., description="Asset external code (e.g. SL-1042)")
    day: date = Field(..., description="Scored calendar day")
    anomaly_score: float = Field(..., ge=0.0, le=1.0, description="Phase 3 IsolationForest score")
    fusion_score: float = Field(..., ge=0.0, le=1.0, description="Phase 4 raw fusion score")
    smoothed_fusion_score: float = Field(..., ge=0.0, le=1.0, description="Phase 4 EMA-smoothed fusion")
    persistence_score: float = Field(..., ge=0.0, le=1.0, description="Sustained-abnormality score")
    risk_score: float = Field(..., ge=0.0, le=1.0, description="Phase 5 weighted risk score")
    risk_level: str = Field(..., description="LOW | MEDIUM | HIGH | CRITICAL")
    model_version: str = Field(..., description="Risk model version")

    model_config = ConfigDict(from_attributes=True)
