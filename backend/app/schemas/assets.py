from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict
from typing import Literal


AssetStatus = Literal['healthy', 'watch', 'emerging', 'critical']


class AssetBase(BaseModel):
    external_code: str = Field(..., min_length=1)
    criticality: int = Field(..., ge=1, le=5)
    public_exposure: int = Field(..., ge=1, le=5)
    status: AssetStatus


class AssetCreate(AssetBase):
    pass


class AssetRegister(BaseModel):
    """Register a public map infrastructure point as a SilentSignal asset.

    Only geographic provenance is supplied; the backend assigns identity
    (UUID + generated external code) and neutral defaults. No telemetry is
    created: analysis endpoints report missing evidence until readings exist.
    """

    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    infra_type: str = Field(..., min_length=1, max_length=120)
    infra_source: str = Field(..., min_length=1, max_length=120)


class AssetResponse(AssetBase):
    id: UUID
    # Optional geographic registration (None for seeded/demo assets).
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    infra_type: Optional[str] = None
    infra_source: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class PaginatedAssets(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[AssetResponse]
