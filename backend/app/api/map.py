"""Fleet map projection API: GET /api/map.

Read-only aggregation over existing data: asset identity + grid-derived
coordinates (documented Phase 2 10x10 municipal grid in data.config) plus
the already calculated latest Phase 2/4/5 statuses. No new tables, no
writes, no anomaly/fusion/risk computation -- pure projection.
"""

import os
import sys

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.assets import Asset
from app.models.fusion_results import FusionResult
from app.models.risk_results import RiskResult
from app.schemas.map import MapAsset, MapResponse

# Make `data.*` importable (repo root = three levels above this file).
_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from data import config  # noqa: E402

router = APIRouter()


def grid_latlon(external_code: str):
    """Deterministic grid coordinates for an asset code (None if outside)."""
    try:
        idx = int(external_code.split("-")[1]) - config.FIRST_CODE
    except (IndexError, ValueError):
        return None, None
    if idx < 0 or idx >= config.GRID_ROWS * config.GRID_COLS:
        return None, None
    row, col = idx // config.GRID_COLS, idx % config.GRID_COLS
    return (
        config.BASE_LAT + row * config.GRID_STEP_LAT,
        config.BASE_LON + col * config.GRID_STEP_LON,
    )


@router.get("/map", response_model=MapResponse)
def get_map(db: Session = Depends(get_db)):
    assets = db.query(Asset).order_by(Asset.external_code).all()

    latest_fusion: dict[str, FusionResult] = {}
    for row in db.query(FusionResult).all():
        prev = latest_fusion.get(row.asset_id)
        if prev is None or row.day > prev.day:
            latest_fusion[row.asset_id] = row
    latest_risk: dict[str, RiskResult] = {}
    for row in db.query(RiskResult).all():
        prev = latest_risk.get(row.asset_id)
        if prev is None or row.day > prev.day:
            latest_risk[row.asset_id] = row

    items = []
    for asset in assets:
        # Registered map assets carry real coordinates; everything else
        # keeps the documented grid derivation (seeded/demo behavior intact).
        if asset.latitude is not None and asset.longitude is not None:
            lat, lon = asset.latitude, asset.longitude
        else:
            lat, lon = grid_latlon(asset.external_code)
        fusion = latest_fusion.get(asset.id)
        risk = latest_risk.get(asset.id)
        items.append(
            MapAsset(
                asset_id=str(asset.id),
                external_code=asset.external_code,
                latitude=lat,
                longitude=lon,
                status=asset.status,
                fusion_status=fusion.status if fusion else None,
                fusion_score=fusion.raw_score if fusion else None,
                risk_level=risk.risk_level if risk else None,
                risk_score=risk.risk_score if risk else None,
                infra_source=asset.infra_source,
            )
        )
    return MapResponse(assets=items, total=len(items))
