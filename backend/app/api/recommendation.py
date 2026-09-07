"""Phase 7 recommendations API: GET /api/assets/{asset_id}/recommendations.

{asset_id} accepts either the asset external code (e.g. SL-1042) or the
asset UUID. Returns the latest scored day with the deterministic
rule-based preventive recommendations (ordered actions, evidence refs).
"""

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.fusion import _resolve_asset
from app.core.db import get_db
from app.models.recommendation_results import RecommendationResult
from app.schemas.recommendation import RecommendationResponse

router = APIRouter()


@router.get("/assets/{asset_id}/recommendations", response_model=RecommendationResponse)
def get_recommendations(asset_id: str, db: Session = Depends(get_db)):
    asset = _resolve_asset(db, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    result = (
        db.query(RecommendationResult)
        .filter(RecommendationResult.asset_id == asset.id)
        .order_by(RecommendationResult.day.desc())
        .first()
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Recommendation result not found for asset")
    return RecommendationResponse(
        asset_id=str(asset.id),
        asset_external_code=asset.external_code,
        day=result.day,
        risk_score=result.risk_score,
        risk_level=result.risk_level,
        priority=result.priority,
        urgency=result.urgency,
        recommendations=json.loads(result.recommendations_json),
        evidence=json.loads(result.evidence_json),
        model_version=result.model_version,
    )
