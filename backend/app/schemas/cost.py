from datetime import date
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class CostResponse(BaseModel):
    """Cost-aware maintenance decision for one asset.

    Derived live from the latest Phase 5 risk score; demo INR assumptions
    are documented, never municipal figures.
    """

    asset_id: str = Field(...)
    asset_external_code: str = Field(...)
    day: date = Field(...)
    risk_score: float = Field(..., ge=0.0, le=1.0)
    risk_level: str = Field(...)
    cost_now: float = Field(...)
    inspection_cost: float = Field(...)
    planned_repair_cost: float = Field(...)
    failure_consequence_cost: float = Field(...)
    expected_waiting_cost: float = Field(...)
    expected_saving: float = Field(...)
    decision: str = Field(..., description="ACT NOW | MONITOR")
    model_version: str = Field(...)
    assumption_note: str = Field(...)
    cost_data_available: bool = Field(True)

    model_config = ConfigDict(from_attributes=True)


class CostUnavailable(BaseModel):
    asset_id: str
    asset_external_code: str
    cost_data_available: bool = False
    detail: str = "COST DATA UNAVAILABLE"
    assumption_note: str = "Demo planning assumptions only (INR); not actual municipal costs."
