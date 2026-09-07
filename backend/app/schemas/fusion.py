from datetime import date
from pydantic import BaseModel, ConfigDict, Field


class FusionResponse(BaseModel):
    """Phase 4 fusion result for one asset (latest scored day)."""

    asset_id: str = Field(..., description="Asset UUID")
    asset_external_code: str = Field(..., description="Asset external code (e.g. SL-1042)")
    day: date = Field(..., description="Scored calendar day")
    power_score: float = Field(..., ge=0.0, le=1.0)
    brightness_score: float = Field(..., ge=0.0, le=1.0)
    temperature_score: float = Field(
        ..., ge=0.0, le=1.0,
        description="Temperature-BEHAVIOR PROXY (no temperature sensor exists in Phase 2)",
    )
    maintenance_score: float = Field(..., ge=0.0, le=1.0)
    neighbor_score: float = Field(..., ge=0.0, le=1.0)
    fusion_score: float = Field(..., ge=0.0, le=1.0, description="Raw weighted fusion score")
    smoothed_fusion_score: float = Field(..., ge=0.0, le=1.0, description="EMA-smoothed fusion (alpha=0.3)")
    status: str = Field(..., description="NORMAL | WATCH | EMERGING | CRITICAL")
    model_version: str = Field(..., description="Fusion model version")

    model_config = ConfigDict(from_attributes=True)
