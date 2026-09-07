from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

class AnomalyResultResponse(BaseModel):
    """Pydantic response model for an anomaly result.

    Includes the asset identifier, timestamp, score and model version.
    """

    id: UUID = Field(..., description="Unique identifier for the anomaly result")
    asset_id: UUID = Field(..., description="Identifier of the associated asset")
    scored_at: datetime = Field(..., description="Timestamp when the score was computed")
    score: float = Field(..., ge=0.0, le=1.0, description="Normalized anomaly score (0 = normal, 1 = extreme)")
    model_version: str = Field(..., description="Version of the model that generated the score")

    model_config = ConfigDict(from_attributes=True)
