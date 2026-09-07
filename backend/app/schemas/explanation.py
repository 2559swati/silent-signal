from datetime import date
from typing import Any, Dict, List
from pydantic import BaseModel, ConfigDict, Field


class ExplanationFactor(BaseModel):
    signal: str = Field(..., description="power | brightness | temperature | maintenance | neighbor | persistence | risk")
    score: float = Field(..., ge=0.0, le=1.0)
    severity: str = Field(..., description="low | medium | high | critical")
    reason: str = Field(..., description="Human-readable rule-based reason")

    model_config = ConfigDict(from_attributes=True)


class ExplanationResponse(BaseModel):
    """Phase 6 explanation for one asset (latest scored day)."""

    asset_id: str = Field(..., description="Asset UUID")
    asset_external_code: str = Field(..., description="Asset external code (e.g. SL-1042)")
    day: date = Field(..., description="Scored calendar day")
    risk_score: float = Field(..., ge=0.0, le=1.0)
    risk_level: str = Field(..., description="LOW | MEDIUM | HIGH | CRITICAL")
    summary: str = Field(..., description="Deterministic rule-based summary")
    factors: List[ExplanationFactor] = Field(..., description="Prioritized contributing factors")
    evidence: Dict[str, Any] = Field(..., description="Input evidence snapshot incl. temperature-proxy note")
    model_version: str = Field(..., description="Explanation model version")

    model_config = ConfigDict(from_attributes=True)
