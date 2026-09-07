"""Phase 9 alerts API.

GET /api/assets/{asset_id}/alerts -- latest actionable alerts for one asset
({asset_id} accepts the external code or UUID, per project convention).
GET /api/alerts -- current actionable alerts across the fleet.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.fusion import _resolve_asset
from app.core.db import get_db
from app.models.alert_results import AlertResult
from app.models.assets import Asset
from app.schemas.alert import AssetAlertsResponse, FleetAlertsResponse
from app.services.alert_engine import ALERT_MODEL_VERSION

router = APIRouter()

_SEVERITY_RANK = {"CRITICAL": 3, "HIGH": 2, "MEDIUM": 1, "LOW": 0}


def _to_item(row: AlertResult) -> dict:
    return {
        "day": row.day,
        "alert_type": row.alert_type,
        "severity": row.severity,
        "priority": row.priority,
        "title": row.title,
        "message": row.message,
        "risk_score": row.risk_score,
        "fusion_score": row.fusion_score,
        "anomaly_score": row.anomaly_score,
        "persistence_score": row.persistence_score,
        "persistence_streak": row.persistence_streak,
        "acknowledged": bool(row.acknowledged),
        "model_version": row.model_version,
    }


@router.get("/assets/{asset_id}/alerts", response_model=AssetAlertsResponse)
def get_asset_alerts(asset_id: str, db: Session = Depends(get_db)):
    asset = _resolve_asset(db, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    latest_day = (
        db.query(AlertResult.day)
        .filter(AlertResult.asset_id == asset.id)
        .order_by(AlertResult.day.desc())
        .first()
    )
    if latest_day is None:
        raise HTTPException(status_code=404, detail="Alert results not found for asset")
    day = latest_day[0]
    rows = (
        db.query(AlertResult)
        .filter(AlertResult.asset_id == asset.id, AlertResult.day == day)
        .order_by(AlertResult.alert_type)
        .all()
    )
    alerts = [_to_item(r) for r in rows]
    return AssetAlertsResponse(
        asset_id=str(asset.id),
        asset_external_code=asset.external_code,
        day=day,
        alerts=alerts,
        total_alerts=len(alerts),
        model_version=ALERT_MODEL_VERSION,
    )


@router.get("/alerts", response_model=FleetAlertsResponse)
def get_fleet_alerts(db: Session = Depends(get_db)):
    latest_day = (
        db.query(AlertResult.day).order_by(AlertResult.day.desc()).first()
    )
    if latest_day is None:
        raise HTTPException(status_code=404, detail="No alert results found")
    day = latest_day[0]
    rows = (
        db.query(AlertResult, Asset.external_code)
        .join(Asset, Asset.id == AlertResult.asset_id)
        .filter(AlertResult.day == day)
        .all()
    )
    alerts = [
        {"asset_id": str(r.asset_id), "asset_external_code": code, **_to_item(r)}
        for r, code in rows
    ]
    alerts.sort(
        key=lambda a: (
            _SEVERITY_RANK.get(a["severity"], -1),
            a["risk_score"],
            a["asset_external_code"],
        ),
        reverse=True,
    )
    return FleetAlertsResponse(
        day=day,
        alerts=alerts,
        total_alerts=len(alerts),
        model_version=ALERT_MODEL_VERSION,
    )
