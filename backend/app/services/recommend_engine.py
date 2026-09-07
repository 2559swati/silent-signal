"""Phase 7 Preventive Recommendations Engine: EXPLANATION -> PREVENTIVE ACTION.

Phase 6 answers "WHY is this situation considered risky?". Phase 7 answers
"WHAT preventive action should the maintenance team take for this asset?"
as a deterministic, rule-based interpretation of the ALREADY CALCULATED
Phase 4/5/6 evidence. No LLM, no GenAI, no chatbot, no randomness.
Identical evidence always yields identical recommendations. The same
generic rules process every asset; no asset is special-cased.

Evidence reuse (no duplicated logic): signal elevation cut-off and
tie-break order are imported from the Phase 6 engine; severity mapping is
imported from the Phase 6 engine (Phase 5 cut points); the daily evidence
timeline (with replayed persistence streaks) is loaded via the Phase 6
evidence loader.

Temperature honesty: the MVP has NO physical temperature sensor. The
temperature action/inspection wording always states it concerns abnormal
thermal BEHAVIOR around the power/lighting subsystem as indicated by the
behavior proxy -- never a sensor reading.

Recommendation rules (all thresholds centralized below)
-------------------------------------------------------
- Item 0 is ALWAYS the risk-level action (risk/urgency first):
    LOW      -> "Continue routine monitoring."
    MEDIUM   -> "Schedule a planned inspection."
    HIGH     -> "Prioritize a preventive inspection."
    CRITICAL -> "Perform an urgent preventive inspection."
- One action per elevated signal (score >= RECOMMEND_THRESHOLD 0.30):
    power       -> inspect power subsystem, wiring, driver, electrical supply.
    brightness  -> inspect lamp/LED output, driver, dimming, optical components.
    temperature -> inspect for abnormal thermal behavior around the
                   power/lighting subsystem (proxy only; no sensor exists).
    maintenance -> schedule preventive maintenance / service inspection.
    neighbor    -> inspect nearby/adjacent assets for a shared issue.
- Persistence item (last) iff persistence_score >= URGENCY_THRESHOLD
  (0.50): expedite planned actions, citing the ACTUAL streak length from
  Phase 5/6 evidence -- no invented durations.
- Priority is the risk-level mapping (exact strings below). Urgency is
  "escalated" iff persistence_score >= URGENCY_THRESHOLD else "normal".
- Ordering: risk action, then signal actions by (score desc, tie-break
  order asc: power, brightness, temperature, maintenance, neighbor),
  then persistence last. At most one item per signal: no duplicates.
"""

import json

from sqlalchemy.orm import Session

from app.models.assets import Asset
from app.models.recommendation_results import RecommendationResult
from app.services.explain_engine import (
    FACTOR_THRESHOLD,
    SIGNAL_ORDER,
    TEMPERATURE_PROXY_NOTE,
    load_daily_evidence,
    severity_for,
)

RECOMMEND_MODEL_VERSION = "recommendation_v1"

# A signal earns its own action at/above this score (Phase 6 factor cut-off:
# a single shared definition of "elevated" across Phases 6-7).
RECOMMEND_THRESHOLD = FACTOR_THRESHOLD

# Persistence at/above this escalates urgency and earns the expedite action
# (same cut-off as the Phase 6 sustained-behavior clause: ~4+ elevated days).
URGENCY_THRESHOLD = 0.50

# Priority is a pure mapping of the Phase 5 risk level (exact strings).
PRIORITY_BY_RISK_LEVEL = {
    "LOW": "routine monitoring",
    "MEDIUM": "planned inspection",
    "HIGH": "prioritize preventive inspection",
    "CRITICAL": "urgent preventive inspection",
}

RISK_ACTIONS = {
    "LOW": "Continue routine monitoring.",
    "MEDIUM": "Schedule a planned inspection.",
    "HIGH": "Prioritize a preventive inspection.",
    "CRITICAL": "Perform an urgent preventive inspection.",
}

SIGNAL_ACTIONS = {
    "power": "Inspect the power subsystem, wiring, driver and electrical supply.",
    "brightness": "Inspect lamp/LED output, driver, dimming behavior and optical components.",
    "temperature": (
        "Inspect for abnormal thermal behavior around the power/lighting "
        "subsystem (temperature behavior proxy only; no physical temperature sensor exists)."
    ),
    "maintenance": "Schedule a preventive maintenance / service inspection.",
    "neighbor": (
        "Inspect nearby/adjacent street-segment assets for a shared "
        "environmental, electrical or infrastructure issue."
    ),
}

SIGNAL_REASON_TEMPLATES = {
    "power": "Power behavior evidence is {severity} (score {score:.2f}).",
    "brightness": "Brightness behavior evidence is {severity} (score {score:.2f}).",
    "temperature": "Temperature-related behavior proxy evidence is {severity} (score {score:.2f}).",
    "maintenance": "Maintenance frequency evidence is {severity} (score {score:.2f}).",
    "neighbor": "Neighbor-correlation evidence is {severity} (score {score:.2f}).",
}


# ---------------------------------------------------------------------------
# Pure helpers (deterministic, no DB) -- directly unit tested.
# ---------------------------------------------------------------------------

def priority_for(risk_level: str) -> str:
    """Map a Phase 5 risk level to the preventive-maintenance priority."""
    return PRIORITY_BY_RISK_LEVEL[risk_level]


def urgency_for(persistence_score: float,
                threshold: float = URGENCY_THRESHOLD) -> str:
    """Escalate urgency only on sustained abnormal behavior (real evidence)."""
    return "escalated" if persistence_score >= threshold else "normal"


def build_recommendations(evidence: dict) -> dict:
    """Build {priority, urgency, recommendations, evidence} from evidence.

    evidence keys: anomaly_score, *_score signals, raw/smoothed fusion,
    fusion_status, persistence_score, streak_days, risk_score, risk_level.
    No DB access; fully deterministic.
    """
    risk_level = evidence["risk_level"]
    risk_score = float(evidence["risk_score"])
    persistence = float(evidence["persistence_score"])
    streak = int(evidence["streak_days"])
    signals = {name: float(evidence[f"{name}_score"]) for name in SIGNAL_ORDER}

    recommendations = [
        {
            "action": RISK_ACTIONS[risk_level],
            "reason": f"Infrastructure risk is {risk_level} (score {risk_score:.2f}).",
            "evidence": {"signal": "risk", "score": risk_score,
                         "severity": risk_level.lower()},
        }
    ]

    ranked = sorted(signals.items(), key=lambda kv: (-kv[1], SIGNAL_ORDER.index(kv[0])))
    for name, score in ranked:
        if score < RECOMMEND_THRESHOLD:
            continue
        severity = severity_for(score)
        recommendations.append(
            {
                "action": SIGNAL_ACTIONS[name],
                "reason": SIGNAL_REASON_TEMPLATES[name].format(
                    severity=severity, score=score),
                "evidence": {"signal": name, "score": score, "severity": severity},
            }
        )

    if persistence >= URGENCY_THRESHOLD:
        day_word = "day" if streak == 1 else "days"
        recommendations.append(
            {
                "action": "Expedite the planned preventive actions.",
                "reason": (
                    f"Abnormal behavior has persisted for {streak} consecutive "
                    f"elevated {day_word} (persistence score {persistence:.2f})."
                ),
                "evidence": {"signal": "persistence", "score": persistence,
                             "severity": severity_for(persistence),
                             "streak_days": streak},
            }
        )

    snapshot = {
        "anomaly_score": float(evidence["anomaly_score"]),
        "power_score": signals["power"],
        "brightness_score": signals["brightness"],
        "temperature_score": signals["temperature"],
        "temperature_proxy_note": TEMPERATURE_PROXY_NOTE,
        "maintenance_score": signals["maintenance"],
        "neighbor_score": signals["neighbor"],
        "raw_fusion_score": float(evidence["raw_fusion_score"]),
        "smoothed_fusion_score": float(evidence["smoothed_fusion_score"]),
        "fusion_status": evidence["fusion_status"],
        "persistence_score": persistence,
        "elevated_streak_days": streak,
        "risk_score": risk_score,
        "risk_level": risk_level,
    }
    return {
        "priority": priority_for(risk_level),
        "urgency": urgency_for(persistence),
        "recommendations": recommendations,
        "evidence": snapshot,
    }


# ---------------------------------------------------------------------------
# Persistence (upsert / idempotent).
# ---------------------------------------------------------------------------

def _upsert_recommendation(db: Session, item: dict, built: dict):
    payload_recs = json.dumps(built["recommendations"])
    payload_evidence = json.dumps(built["evidence"])
    row = (
        db.query(RecommendationResult)
        .filter(
            RecommendationResult.asset_id == item["asset_id"],
            RecommendationResult.day == item["day"],
        )
        .one_or_none()
    )
    if row is None:
        row = RecommendationResult(
            asset_id=item["asset_id"],
            day=item["day"],
            risk_score=item["risk_score"],
            risk_level=item["risk_level"],
            priority=built["priority"],
            urgency=built["urgency"],
            recommendations_json=payload_recs,
            evidence_json=payload_evidence,
            model_version=RECOMMEND_MODEL_VERSION,
        )
        db.add(row)
    else:
        row.risk_score = item["risk_score"]
        row.risk_level = item["risk_level"]
        row.priority = built["priority"]
        row.urgency = built["urgency"]
        row.recommendations_json = payload_recs
        row.evidence_json = payload_evidence
        row.model_version = RECOMMEND_MODEL_VERSION
    return row


def compute_all_recommendations(db: Session):
    """Run the full Phase 7 pipeline: evidence -> rules -> recommendations.

    One recommendation row per (asset_id, day), upserted idempotently.
    Never writes to Phase 0-6 state.
    """
    timeline = load_daily_evidence(db)
    n = 0
    for asset_id in sorted(timeline):
        for item in timeline[asset_id]:
            _upsert_recommendation(db, item, build_recommendations(item))
            n += 1
    db.commit()
    return {"assets": len(timeline), "recommendations": n}


def compute_asset_recommendations(asset_id: str, db: Session):
    """Recompute (and persist) the daily recommendation timeline for one asset.

    Identical deterministic rules as compute_all_recommendations, scoped to
    a single asset. Returns the latest day's full recommendation dict.
    """
    asset = db.query(Asset).filter(Asset.id == asset_id).one_or_none()
    if asset is None:
        raise ValueError(f"unknown asset_id {asset_id}")
    timeline = load_daily_evidence(db)
    if asset_id not in timeline:
        raise RuntimeError("No Phase 4/5 evidence found for asset")
    latest = None
    for item in timeline[asset_id]:
        built = build_recommendations(item)
        _upsert_recommendation(db, item, built)
        latest = {"asset_id": asset_id, "day": item["day"], **built}
    db.commit()
    return latest
