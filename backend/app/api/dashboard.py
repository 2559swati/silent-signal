"""Dashboard summary API: GET /api/dashboard/summary.

Read-only aggregation over existing data: asset counts by seed status plus
the already calculated latest Phase 4 (fusion) / Phase 5 (risk) / Phase 9
(alert) rows. No new tables, no writes, no computation -- pure projection
for the fleet dashboard and the Phase 15 Docker smoke test.
"""

from collections import Counter

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.alert_results import AlertResult
from app.models.assets import Asset
from app.models.fusion_results import FusionResult
from app.models.risk_results import RiskResult
from app.schemas.dashboard import DashboardSummary

router = APIRouter()


def _latest_per_asset(rows, key=lambda r: r.day):
    latest = {}
    for row in rows:
        prev = latest.get(row.asset_id)
        if prev is None or key(row) > key(prev):
            latest[row.asset_id] = row
    return latest


@router.get("/dashboard/summary", response_model=DashboardSummary)
def get_dashboard_summary(db: Session = Depends(get_db)):
    assets = db.query(Asset).all()
    fusion = _latest_per_asset(db.query(FusionResult).all())
    risk = _latest_per_asset(db.query(RiskResult).all())

    latest_day = None
    day_rows = db.query(AlertResult.day).order_by(AlertResult.day.desc()).first()
    if day_rows is not None:
        latest_day = day_rows[0]
        latest_iso = latest_day.isoformat()
        alerts = db.query(AlertResult).filter(AlertResult.day == latest_day).all()
    else:
        latest_iso = None
        alerts = []

    return DashboardSummary(
        total_assets=len(assets),
        assets_by_status=dict(Counter(a.status for a in assets)),
        latest_day=latest_iso,
        total_alerts=len(alerts),
        alerts_by_severity=dict(Counter(a.severity for a in alerts)),
        risk_by_level=dict(Counter(r.risk_level for r in risk.values())),
        fusion_by_status=dict(Counter(f.status for f in fusion.values())),
    )
