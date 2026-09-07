"""Phase 2 demo/reset endpoint: POST /api/demo/reset.

Single-transaction deterministic reset + regeneration. No table drops,
no whole-database destructive commands. Returns a concise summary.
"""

import os
import sys

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db

# Make `data.*` importable (repo root = three levels above this file).
_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from data.generate_dataset import reset_and_generate  # noqa: E402

router = APIRouter()


@router.post("/demo/reset")
def reset_demo(db: Session = Depends(get_db)):
    try:
        n_assets, n_readings, n_maint = reset_and_generate(db)
        # Run Phase 4 fusion pipeline on the freshly generated dataset,
        # then Phase 5 risk, Phase 6 explanation, Phase 7 recommendations
        # and Phase 9 alerts on the fresh evidence (strict pipeline order).
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

    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {
        "status": "ok",
        "assets": n_assets,
        "sensor_readings": n_readings,
        "maintenance_records": n_maint,
    }
