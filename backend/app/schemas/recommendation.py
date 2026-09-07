from datetime import date
from typing import Any, Dict, List
from pydantic import BaseModel, ConfigDict, Field


class RecommendationItem(BaseModel):
    action: str = Field(..., description="Concise actionable preventive step")
    reason: str = Field(..., description="Human-readable rule-based reason")
    evidence: Dict[str, Any] = Field(..., description="Evidence reference: signal, score, severity")

    model_config = ConfigDict(from_attributes=True)


class RecommendationResponse(BaseModel):
    """Phase 7 preventive recommendations for one asset (latest scored day)."""

    asset_id: str = Field(..., description="Asset UUID")
    asset_external_code: str = Field(..., description="Asset external code (e.g. SL-1042)")
    day: date = Field(..., description="Scored calendar day")
    risk_score: float = Field(..., ge=0.0, le=1.0)
    risk_level: str = Field(..., description="LOW | MEDIUM | HIGH | CRITICAL")
    priority: str = Field(..., description="Preventive-maintenance priority")
    urgency: str = Field(..., description="normal | escalated")
    recommendations: List[RecommendationItem] = Field(..., description="Ordered preventive actions")
    evidence: Dict[str, Any] = Field(..., description="Input evidence snapshot incl. temperature-proxy note")
    model_version: str = Field(..., description="Recommendation model version")

    model_config = ConfigDict(from_attributes=True)
