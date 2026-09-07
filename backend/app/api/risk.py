"""Phase 5 risk API: GET /api/assets/{asset_id}/risk.

{asset_id} accepts either the asset external code (e.g. SL-1042) or the
asset UUID. Returns the latest scored day with the Phase 3/4 evidence,
the persistence score, the calculated risk score/level and model version.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.fusion import _resolve_asset
from app.core.db import get_db
from app.models.risk_results import RiskResult
from app.schemas.risk import RiskResponse

router = APIRouter()


@router.get("/assets/{asset_id}/risk", response_model=RiskResponse)
def get_risk(asset_id: str, db: Session = Depends(get_db)):
    asset = _resolve_asset(db, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    result = (
        db.query(RiskResult)
        .filter(RiskResult.asset_id == asset.id)
        .order_by(RiskResult.day.desc())
        .first()
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Risk result not found for asset")
    return RiskResponse(
        asset_id=str(asset.id),
        asset_external_code=asset.external_code,
        day=result.day,
        anomaly_score=result.anomaly_score,
        fusion_score=result.fusion_score,
        smoothed_fusion_score=result.smoothed_fusion_score,
        persistence_score=result.persistence_score,
        risk_score=result.risk_score,
        risk_level=result.risk_level,
        model_version=result.model_version,
    )
