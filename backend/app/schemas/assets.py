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


class AssetResponse(AssetBase):
    id: UUID

    model_config = ConfigDict(from_attributes=True)


class PaginatedAssets(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[AssetResponse]
