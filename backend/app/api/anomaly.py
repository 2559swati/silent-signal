from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID

from app.core.db import get_db
from app.models.anomalies import AnomalyResult
from app.schemas.anomalies import AnomalyResultResponse

router = APIRouter(tags=["anomaly"])

@router.get("/assets/{asset_id}/anomaly", response_model=AnomalyResultResponse)
def get_anomaly(asset_id: UUID, db: Session = Depends(get_db)):
    """Return the latest anomaly result for a given asset.

    Args:
        asset_id: UUID of the asset.
        db: Database session.
    Returns:
        AnomalyResultResponse with latest scored_at.
    Raises:
        HTTPException 404 if no result found.
    """
    result = (
        db.query(AnomalyResult)
        .filter(AnomalyResult.asset_id == str(asset_id))
        .order_by(AnomalyResult.scored_at.desc())
        .first()
    )
    if not result:
        raise HTTPException(status_code=404, detail="Anomaly result not found for asset")
    return result
