from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class MapAsset(BaseModel):
    """One fleet asset projected for the geographical map.

    Coordinates reuse the documented Phase 2 10x10 municipal grid
    (data.config BASE_LAT/BASE_LON + steps, row-major SL-1001..SL-1100);
    no GPS hardware or new sensors are involved. Statuses are the already
    calculated Phase 2/4/5 values -- this endpoint creates no intelligence.
    """

    asset_id: str = Field(..., description="Asset UUID")
    external_code: str = Field(..., description="Asset external code (e.g. SL-1042)")
    latitude: Optional[float] = Field(None, description="Grid-derived latitude (None if code is outside the grid)")
    longitude: Optional[float] = Field(None, description="Grid-derived longitude (None if code is outside the grid)")
    status: str = Field(..., description="Phase 2 asset status: healthy | watch | emerging | critical")
    fusion_status: Optional[str] = Field(None, description="Latest Phase 4 status: NORMAL | WATCH | EMERGING | CRITICAL")
    fusion_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    risk_level: Optional[str] = Field(None, description="Latest Phase 5 risk level")
    risk_score: Optional[float] = Field(None, ge=0.0, le=1.0)

    model_config = ConfigDict(from_attributes=True)


class MapResponse(BaseModel):
    """Full fleet projection for GET /api/map."""

    assets: List[MapAsset] = Field(..., description="All assets with grid coordinates where derivable")
    total: int = Field(..., description="Number of assets returned")

    model_config = ConfigDict(from_attributes=True)
