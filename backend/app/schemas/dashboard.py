from typing import Dict, Optional
from pydantic import BaseModel, ConfigDict, Field


class DashboardSummary(BaseModel):
    """Fleet-wide roll-up for GET /api/dashboard/summary.

    Read-only aggregation over already calculated state (assets +
    latest Phase 4/5/9 rows). Creates no intelligence, writes nothing;
    exists so the Phase 15 Docker smoke test can verify a working demo
    with a single non-empty response.
    """

    total_assets: int = Field(..., description="Number of assets in the database")
    assets_by_status: Dict[str, int] = Field(..., description="Seed status counts")
    latest_day: Optional[str] = Field(None, description="Latest pipeline day (ISO), if any evidence exists")
    total_alerts: int = Field(..., description="Alert rows on the latest day")
    alerts_by_severity: Dict[str, int] = Field(..., description="Latest-day alerts by severity")
    risk_by_level: Dict[str, int] = Field(..., description="Latest risk rows by level")
    fusion_by_status: Dict[str, int] = Field(..., description="Latest fusion rows by status")

    model_config = ConfigDict(from_attributes=True)
