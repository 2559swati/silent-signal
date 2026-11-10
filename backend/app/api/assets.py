from typing import Literal, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.api.fusion import _resolve_asset
from app.core.db import get_db
from app.models.assets import Asset
from app.schemas.assets import PaginatedAssets, AssetRegister, AssetResponse
from app.services.demo_telemetry import MODES, SIMULATED_WARNING, write_demo_readings

router = APIRouter(prefix="/assets", tags=["assets"])


@router.get("", response_model=PaginatedAssets)
def list_assets(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None, pattern="^(healthy|watch|emerging|critical)$"),
    db: Session = Depends(get_db),
):
    query = db.query(Asset)
    if status:
        query = query.filter(Asset.status == status)

    total = query.count()
    items = (
        query.order_by(Asset.external_code)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return PaginatedAssets(total=total, page=page, page_size=page_size, items=items)


def _code_for_source(infra_source: str) -> str:
    """Deterministic external code from provenance (e.g. 'osm:123' -> 'SL-EXT-123')."""
    slug = ''.join(ch if ch.isalnum() else '-' for ch in infra_source).strip('-').upper()
    return f"SL-EXT-{slug}"[:64]


@router.post("/register", response_model=AssetResponse, status_code=status.HTTP_201_CREATED)
def register_asset(payload: AssetRegister, db: Session = Depends(get_db)):
    """Register a public map infrastructure point as a SilentSignal asset.

    Additive endpoint: creates one Asset row with real coordinates and
    provenance. Neutral defaults (criticality/exposure 3, status 'watch':
    needs observation, claims nothing). No telemetry is fabricated, so
    fusion/risk/explain/recommend endpoints report missing evidence until
    readings exist. Re-registering the same infra_source returns 409.
    """
    existing = db.query(Asset).filter(Asset.infra_source == payload.infra_source).one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="Infrastructure point already registered")
    asset = Asset(
        external_code=_code_for_source(payload.infra_source),
        criticality=3,
        public_exposure=3,
        status="watch",
        latitude=payload.latitude,
        longitude=payload.longitude,
        infra_type=payload.infra_type,
        infra_source=payload.infra_source,
    )
    db.add(asset)
    try:
        db.commit()
    except Exception:
        db.rollback()
        # Unique-constraint race on external_code/infra_source.
        raise HTTPException(status_code=409, detail="Infrastructure point already registered")
    db.refresh(asset)
    return asset


class DemoTelemetryRequest(BaseModel):
    mode: Literal["normal", "anomalous"]


@router.post("/{asset_id}/demo-telemetry")
def enable_demo_telemetry(asset_id: str, payload: DemoTelemetryRequest, db: Session = Depends(get_db)):
    """Write deterministic SIMULATED readings for a map-registered asset and
    run the EXISTING full pipeline over them (same compute_all_* calls as
    POST /api/demo/reset). Seeded assets are rejected (400): their frozen
    dataset must not be disturbed. Response always carries simulated=true.
    """
    asset = _resolve_asset(db, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    if not asset.infra_source:
        raise HTTPException(
            status_code=400,
            detail="Demo telemetry is only available for map-registered assets",
        )
    count = write_demo_readings(db, asset, payload.mode)
    # Existing pipeline entry points (identical to /api/demo/reset).
    from app.services.fusion_engine import compute_all_days
    compute_all_days(db)
    from app.services.risk_engine import compute_all_risks
    compute_all_risks(db)
    from app.services.explain_engine import compute_all_explanations
    compute_all_explanations(db)
    from app.services.recommend_engine import compute_all_recommendations
    compute_all_recommendations(db)
    from app.services.alert_engine import compute_all_alerts
    compute_all_alerts(db)
    return {
        "status": "ok",
        "asset_external_code": asset.external_code,
        "mode": payload.mode,
        "readings_written": count,
        "simulated": True,
        "warning": SIMULATED_WARNING,
    }
