"""Phase 6 explanation API: GET /api/assets/{asset_id}/explanation.

{asset_id} accepts either the asset external code (e.g. SL-1042) or the
asset UUID. Returns the latest scored day with the deterministic
rule-based explanation (summary, prioritized factors, evidence snapshot).
"""

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.fusion import _resolve_asset
from app.core.db import get_db
from app.models.explanation_results import ExplanationResult
from app.schemas.explanation import ExplanationResponse

router = APIRouter()


@router.get("/assets/{asset_id}/explanation", response_model=ExplanationResponse)
def get_explanation(asset_id: str, db: Session = Depends(get_db)):
    asset = _resolve_asset(db, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    result = (
        db.query(ExplanationResult)
        .filter(ExplanationResult.asset_id == asset.id)
        .order_by(ExplanationResult.day.desc())
        .first()
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Explanation result not found for asset")
    return ExplanationResponse(
        asset_id=str(asset.id),
        asset_external_code=asset.external_code,
        day=result.day,
        risk_score=result.risk_score,
        risk_level=result.risk_level,
        summary=result.summary,
        factors=json.loads(result.factors_json),
        evidence=json.loads(result.evidence_json),
        model_version=result.model_version,
    )
