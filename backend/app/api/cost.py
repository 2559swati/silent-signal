from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.api.fusion import _resolve_asset
from app.services.cost_engine import compute_asset_cost
from app.schemas.cost import CostResponse, CostUnavailable

router = APIRouter()

@router.get("/assets/{asset_id}/cost", response_model=CostResponse, responses={404: {"model": CostUnavailable}})
def get_cost(asset_id: str, db: Session = Depends(get_db)):
    """Return cost‑aware recommendation for an asset.
    Uses existing cost_engine; if risk or cost data missing, returns 404 with CostUnavailable.
    """
    asset = _resolve_asset(db, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    try:
        result = compute_asset_cost(db, str(asset.id))
    except LookupError as e:
        # Translate missing data to a 404 with the appropriate detail.
        raise HTTPException(status_code=404, detail=str(e))
    # result already matches CostResponse schema.
    return CostResponse(**result)
