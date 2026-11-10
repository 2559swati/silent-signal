"""Cost-aware maintenance decision (Phase 13).

Reuses the EXISTING Phase 5 risk evidence as the single source of truth:
no second prediction system, no duplicated risk logic.

Concept:
    Cost Now = Inspection Cost + Planned Repair Cost
    Expected Cost of Waiting = Failure Probability x Failure Consequence Cost
    Expected Saving = Expected Cost of Waiting - Cost Now

    If Cost Now < Expected Cost of Waiting: ACT NOW, else MONITOR.

Demo cost values are planning assumptions only (INR), never presented as
actual municipal costs. Failure probability is the latest Phase 5
risk_score (an honest "elevated predicted failure risk", never certainty).
If no risk evidence exists for an asset, cost data is reported unavailable.
"""

from sqlalchemy.orm import Session

from app.models.assets import Asset
from app.models.risk_results import RiskResult

COST_MODEL_VERSION = "cost_v1"

# Demo planning assumptions (INR). Documented as assumptions everywhere
# they are displayed; do not present as municipal figures.
INSPECTION_COST = 500.0
PLANNED_REPAIR_COST = 1000.0
FAILURE_CONSEQUENCE_COST = 6000.0

COST_NOW = INSPECTION_COST + PLANNED_REPAIR_COST  # 1500

COST_ASSUMPTION_NOTE = (
    "Demo planning assumptions only (INR); not actual municipal costs."
)


def cost_decision_for_risk(risk_score: float) -> dict:
    """Pure cost-aware decision for a risk score in [0, 1]."""
    score = max(0.0, min(1.0, float(risk_score)))
    cost_now = COST_NOW
    expected_waiting = round(score * FAILURE_CONSEQUENCE_COST, 2)
    expected_saving = round(expected_waiting - cost_now, 2)
    decision = "ACT NOW" if cost_now < expected_waiting else "MONITOR"
    return {
        "cost_now": cost_now,
        "inspection_cost": INSPECTION_COST,
        "planned_repair_cost": PLANNED_REPAIR_COST,
        "failure_consequence_cost": FAILURE_CONSEQUENCE_COST,
        "expected_waiting_cost": expected_waiting,
        "expected_saving": expected_saving,
        "decision": decision,
        "model_version": COST_MODEL_VERSION,
        "assumption_note": COST_ASSUMPTION_NOTE,
    }


def compute_asset_cost(db: Session, asset_id: str) -> dict:
    """Load latest Phase 5 risk for an asset and apply cost decision.

    Raises LookupError("asset") if the asset does not exist,
    LookupError("risk") if no risk evidence exists (caller maps to
    COST DATA UNAVAILABLE / 404 without inventing a score).
    """
    asset = db.query(Asset).filter(Asset.id == asset_id).one_or_none()
    if asset is None:
        raise LookupError("asset")
    risk = (
        db.query(RiskResult)
        .filter(RiskResult.asset_id == asset.id)
        .order_by(RiskResult.day.desc())
        .first()
    )
    if risk is None:
        raise LookupError("risk")
    decided = cost_decision_for_risk(float(risk.risk_score))
    return {
        "asset_id": str(asset.id),
        "asset_external_code": asset.external_code,
        "day": risk.day,
        "risk_score": float(risk.risk_score),
        "risk_level": risk.risk_level,
        **decided,
    }
