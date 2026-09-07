"""Phase 4 fusion API: GET /api/assets/{asset_id}/fusion.

{asset_id} accepts either the asset external code (e.g. SL-1042) or the
asset UUID. Returns the latest scored day with all five weak-signal
scores, raw + smoothed fusion, confirmed status and model version.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID

from app.core.db import get_db
from app.models.assets import Asset
from app.models.fusion_results import FusionResult
from app.schemas.fusion import FusionResponse

router = APIRouter()


def _resolve_asset(db: Session, key: str):
    asset = db.query(Asset).filter(Asset.external_code == key).one_or_none()
    if asset is None:
        # Live PostgreSQL stores assets.id as UUID: only attempt the id
        # lookup for well-formed UUIDs so unknown codes yield 404, not a
        # database type error.
        try:
            UUID(str(key))
        except (ValueError, AttributeError, TypeError):
            return None
        asset = db.query(Asset).filter(Asset.id == key).one_or_none()
    return asset


@router.get("/assets/{asset_id}/fusion", response_model=FusionResponse)
def get_fusion(asset_id: str, db: Session = Depends(get_db)):
    asset = _resolve_asset(db, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    result = (
        db.query(FusionResult)
        .filter(FusionResult.asset_id == asset.id)
        .order_by(FusionResult.day.desc())
        .first()
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Fusion result not found for asset")
    return FusionResponse(
        asset_id=str(asset.id),
        asset_external_code=asset.external_code,
        day=result.day,
        power_score=result.power_score,
        brightness_score=result.brightness_score,
        temperature_score=result.temperature_score,
        maintenance_score=result.maintenance_score,
        neighbor_score=result.neighbor_score,
        fusion_score=result.raw_score,
        smoothed_fusion_score=result.smoothed_score,
        status=result.status,
        model_version=result.model_version,
    )
