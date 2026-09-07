"""Phase 9 Alert/Event Engine: evidence -> ACTIONABLE ALERTS.

Phase 7 answers "WHAT preventive action should the maintenance team take?".
Phase 9 answers "WHEN should SilentSignal generate an actionable alert?"
as a deterministic rule layer over the ALREADY CALCULATED Phase 3-7
evidence. No second anomaly model, no second risk engine, no duplicated
fusion/risk/explanation/recommendation logic, no LLM, no randomness.
Identical evidence always yields identical alerts. The same generic rules
process every asset; no asset is special-cased.

Evidence reuse (no duplicated logic): severity is the Phase 5 risk-level
mapping (determine_risk_level on the persisted risk score); the elevated
signal cut-off is the Phase 6 factor threshold; the sustained-behavior
cut-off is the Phase 6/7 persistence clause cut-off; streaks come from the
persisted Phase 6 explanation evidence (no recomputation).

Alert rules (all thresholds centralized below)
---------------------------------------------
- CRITICAL_RISK: risk_level == CRITICAL.
- SUSTAINED_RISK: persistence_score >= SUSTAINED_THRESHOLD (0.50, the
  established Phase 5/6/7 sustained condition) with the actual streak from
  Phase 6 evidence in the message.
- RISK_ESCALATION: today's persisted risk-level ordinal is strictly higher
  than yesterday's persisted risk-level ordinal (a material, persisted
  increase -- never a single unconfirmed observation). Day 0 has no
  previous day and never escalates.
- EMERGING_ANOMALY: fusion status in {EMERGING, CRITICAL} AND the evidence
  supports it (smoothed fusion >= 0.50, the EMERGING cut-off).
- SIGNAL_CONVERGENCE: at least CONVERGENCE_COUNT (3) of the 5 weak signals
  score >= the elevated cut-off (0.30).

Severity for every type is determine_risk_level(risk_score) -- the exact
Phase 5 thresholds, so an alert can never disagree with the risk engine
about severity. Priority derives from severity: CRITICAL -> URGENT,
HIGH -> HIGH, MEDIUM -> MEDIUM, LOW -> LOW.

Dedupe: one row per (asset_id, day, alert_type) via upsert; reruns with
identical evidence produce identical rows and never duplicate.
"""

import json

from sqlalchemy.orm import Session

from app.models.alert_results import AlertResult
from app.models.assets import Asset
from app.models.explanation_results import ExplanationResult
from app.models.fusion_results import FusionResult
from app.models.risk_results import RiskResult
from app.services.explain_engine import FACTOR_THRESHOLD, SIGNAL_ORDER
from app.services.risk_engine import RISK_LEVEL_ORDER, determine_risk_level

ALERT_MODEL_VERSION = "alert_v1"

# Alert types (stable strings persisted in alert_results.alert_type).
CRITICAL_RISK = "CRITICAL_RISK"
SUSTAINED_RISK = "SUSTAINED_RISK"
RISK_ESCALATION = "RISK_ESCALATION"
EMERGING_ANOMALY = "EMERGING_ANOMALY"
SIGNAL_CONVERGENCE = "SIGNAL_CONVERGENCE"

ALERT_TYPES = (
    CRITICAL_RISK,
    SUSTAINED_RISK,
    RISK_ESCALATION,
    EMERGING_ANOMALY,
    SIGNAL_CONVERGENCE,
)

# A weak signal counts as "contributing meaningful evidence" at/above this
# score (the shared Phase 6/7 elevated cut-off: one definition everywhere).
CONTRIBUTING_THRESHOLD = FACTOR_THRESHOLD

# Sustained abnormal behavior: the established Phase 5/6/7 condition
# (persistence streak saturates at 7 days; 0.50 ~= 4+ elevated days).
SUSTAINED_THRESHOLD = 0.50

# Smoothed fusion at/above this corroborates an emerging anomaly
# (the Phase 4 EMERGING cut-off).
EMERGING_EVIDENCE_THRESHOLD = 0.50

# Weak signals that must simultaneously contribute for convergence.
CONVERGENCE_COUNT = 3

ELEVATED_FUSION_STATUSES = frozenset({"EMERGING", "CRITICAL"})

# Priority derives from severity (exact strings).
PRIORITY_BY_SEVERITY = {
    "CRITICAL": "URGENT",
    "HIGH": "HIGH",
    "MEDIUM": "MEDIUM",
    "LOW": "LOW",
}


# ---------------------------------------------------------------------------
# Pure helpers (deterministic, no DB) -- directly unit tested.
# ---------------------------------------------------------------------------

def determine_severity(risk_score: float) -> str:
    """Severity is exactly the Phase 5 risk level for the score."""
    return determine_risk_level(risk_score)


def determine_priority(severity: str) -> str:
    """Priority derives from severity (CRITICAL -> URGENT, else identity)."""
    return PRIORITY_BY_SEVERITY[severity]


def determine_alert_types(item: dict, previous_risk_level: str | None) -> list[str]:
    """Rule evaluation for one asset-day evidence item (pure).

    item keys: the five *_score signals, fusion_status, smoothed_fusion,
    risk_score, risk_level, persistence_score, streak_days.
    previous_risk_level: yesterday's persisted risk level (None on day 0).
    Returns the triggered alert types in ALERT_TYPES order (deterministic).
    """
    triggered: list[str] = []
    risk_level = item["risk_level"]
    signals = {name: float(item[f"{name}_score"]) for name in SIGNAL_ORDER}

    if risk_level == "CRITICAL":
        triggered.append(CRITICAL_RISK)

    if float(item["persistence_score"]) >= SUSTAINED_THRESHOLD:
        triggered.append(SUSTAINED_RISK)

    if (
        previous_risk_level is not None
        and RISK_LEVEL_ORDER[risk_level] > RISK_LEVEL_ORDER[previous_risk_level]
    ):
        triggered.append(RISK_ESCALATION)

    if (
        item["fusion_status"] in ELEVATED_FUSION_STATUSES
        and float(item["smoothed_fusion"]) >= EMERGING_EVIDENCE_THRESHOLD
    ):
        triggered.append(EMERGING_ANOMALY)

    contributing = sorted(
        name for name, score in signals.items() if score >= CONTRIBUTING_THRESHOLD
    )
    if len(contributing) >= CONVERGENCE_COUNT:
        triggered.append(SIGNAL_CONVERGENCE)

    return [t for t in ALERT_TYPES if t in triggered]


def build_alert(alert_type: str, item: dict, previous_risk_level: str | None) -> dict:
    """Build the persisted alert payload (title/message/evidence) -- pure."""
    risk_score = float(item["risk_score"])
    severity = determine_severity(risk_score)
    signals = {name: float(item[f"{name}_score"]) for name in SIGNAL_ORDER}
    contributing = sorted(
        name for name, score in signals.items() if score >= CONTRIBUTING_THRESHOLD
    )
    streak = int(item["streak_days"])
    day_word = "day" if streak == 1 else "days"

    if alert_type == CRITICAL_RISK:
        title = "Critical infrastructure risk detected"
        message = (
            f"Critical infrastructure risk detected (risk score {risk_score:.2f}). "
            "Immediate preventive inspection is recommended."
        )
    elif alert_type == SUSTAINED_RISK:
        title = "Elevated risk sustained over multiple days"
        message = (
            f"Elevated risk has persisted for {streak} consecutive {day_word} "
            f"(persistence score {float(item['persistence_score']):.2f}). "
            "Expedite the planned preventive actions."
        )
    elif alert_type == RISK_ESCALATION:
        title = f"Risk escalated from {previous_risk_level} to {item['risk_level']}"
        message = (
            f"Risk level escalated from {previous_risk_level} to {item['risk_level']} "
            f"(risk score {risk_score:.2f}). Review the contributing evidence and "
            "bring forward the preventive inspection."
        )
    elif alert_type == EMERGING_ANOMALY:
        title = "Emerging abnormal behavior detected"
        message = (
            "Multiple infrastructure signals indicate emerging abnormal behavior "
            f"(fusion status {item['fusion_status']}, smoothed fusion "
            f"{float(item['smoothed_fusion']):.2f}). Schedule a preventive inspection."
        )
    else:  # SIGNAL_CONVERGENCE
        title = "Multiple weak signals converging on risk"
        message = (
            f"Multiple weak signals ({len(contributing)} of 5) are contributing to "
            f"the current risk condition: {', '.join(contributing)}. Inspect the "
            "indicated subsystems before the condition worsens."
        )

    return {
        "alert_type": alert_type,
        "severity": severity,
        "priority": determine_priority(severity),
        "title": title,
        "message": message,
        "risk_score": risk_score,
        "fusion_score": float(item["raw_fusion"]),
        "anomaly_score": float(item["anomaly_score"]),
        "persistence_score": float(item["persistence_score"]),
        "persistence_streak": streak,
    }


# ---------------------------------------------------------------------------
# Evidence loading (deterministic reads; never writes Phase 0-7 state).
# ---------------------------------------------------------------------------

def load_alert_evidence(db: Session):
    """Join fusion + risk + explanation rows per asset chronologically.

    Returns {asset_id: [item-dict]} where each item carries the signals,
    scores, statuses, persisted risk levels and the Phase 6 streak.
    Raises if upstream evidence is missing (pipeline order guarantees it).
    """
    fusion_rows = (
        db.query(FusionResult)
        .order_by(FusionResult.asset_id, FusionResult.day)
        .all()
    )
    if not fusion_rows:
        raise RuntimeError("No Phase 4 fusion results found; run the fusion pipeline first")
    risk_by_key = {(r.asset_id, r.day): r for r in db.query(RiskResult).all()}
    if not risk_by_key:
        raise RuntimeError("No Phase 5 risk results found; run the risk pipeline first")
    explanation_by_key = {(e.asset_id, e.day): e for e in db.query(ExplanationResult).all()}
    if not explanation_by_key:
        raise RuntimeError("No Phase 6 explanation results found; run the explanation pipeline first")
    timeline: dict[str, list[dict]] = {}
    for f in fusion_rows:
        key = (f.asset_id, f.day)
        if key not in risk_by_key:
            raise RuntimeError(f"Missing Phase 5 risk row for asset/day {key}")
        if key not in explanation_by_key:
            raise RuntimeError(f"Missing Phase 6 explanation row for asset/day {key}")
        r = risk_by_key[key]
        streak = int(json.loads(explanation_by_key[key].evidence_json)["elevated_streak_days"])
        timeline.setdefault(f.asset_id, []).append(
            {
                "asset_id": f.asset_id,
                "day": f.day,
                "anomaly_score": r.anomaly_score,
                "power_score": f.power_score,
                "brightness_score": f.brightness_score,
                "temperature_score": f.temperature_score,
                "maintenance_score": f.maintenance_score,
                "neighbor_score": f.neighbor_score,
                "raw_fusion": f.raw_score,
                "smoothed_fusion": f.smoothed_score,
                "fusion_status": f.status,
                "persistence_score": r.persistence_score,
                "streak_days": streak,
                "risk_score": r.risk_score,
                "risk_level": r.risk_level,
            }
        )
    return timeline


# ---------------------------------------------------------------------------
# Persistence (upsert / idempotent).
# ---------------------------------------------------------------------------

def _upsert_alert(db: Session, item: dict, built: dict):
    row = (
        db.query(AlertResult)
        .filter(
            AlertResult.asset_id == item["asset_id"],
            AlertResult.day == item["day"],
            AlertResult.alert_type == built["alert_type"],
        )
        .one_or_none()
    )
    if row is None:
        row = AlertResult(
            asset_id=item["asset_id"],
            day=item["day"],
            alert_type=built["alert_type"],
            severity=built["severity"],
            priority=built["priority"],
            title=built["title"],
            message=built["message"],
            risk_score=built["risk_score"],
            fusion_score=built["fusion_score"],
            anomaly_score=built["anomaly_score"],
            persistence_score=built["persistence_score"],
            persistence_streak=built["persistence_streak"],
            acknowledged=False,
            model_version=ALERT_MODEL_VERSION,
        )
        db.add(row)
    else:
        row.severity = built["severity"]
        row.priority = built["priority"]
        row.title = built["title"]
        row.message = built["message"]
        row.risk_score = built["risk_score"]
        row.fusion_score = built["fusion_score"]
        row.anomaly_score = built["anomaly_score"]
        row.persistence_score = built["persistence_score"]
        row.persistence_streak = built["persistence_streak"]
        row.model_version = ALERT_MODEL_VERSION
    return row


def compute_all_alerts(db: Session):
    """Run the full Phase 9 pipeline: evidence -> rules -> alerts.

    Walks each asset's timeline chronologically (previous persisted risk
    level feeds escalation detection). Upserts one row per
    (asset_id, day, alert_type): reruns are idempotent and never duplicate.
    Never writes to Phase 0-7 state.
    """
    timeline = load_alert_evidence(db)
    counts = {t: 0 for t in ALERT_TYPES}
    for asset_id in sorted(timeline):
        previous_level: str | None = None
        for item in timeline[asset_id]:
            for alert_type in determine_alert_types(item, previous_level):
                _upsert_alert(db, item, build_alert(alert_type, item, previous_level))
                counts[alert_type] += 1
            previous_level = item["risk_level"]
    db.commit()
    total = sum(counts.values())
    return {"assets": len(timeline), "alerts": total, **{f"{t.lower()}": c for t, c in counts.items()}}


def compute_asset_alerts(asset_id: str, db: Session):
    """Recompute (and persist) the daily alert timeline for one asset.

    Identical deterministic rules as compute_all_alerts, scoped to a single
    asset. Returns the latest day's alerts.
    """
    asset = db.query(Asset).filter(Asset.id == asset_id).one_or_none()
    if asset is None:
        raise ValueError(f"unknown asset_id {asset_id}")
    timeline = load_alert_evidence(db)
    if asset_id not in timeline:
        raise RuntimeError("No Phase 4/5/6 evidence found for asset")
    previous_level: str | None = None
    latest: list[dict] = []
    for item in timeline[asset_id]:
        latest = []
        for alert_type in determine_alert_types(item, previous_level):
            built = build_alert(alert_type, item, previous_level)
            _upsert_alert(db, item, built)
            latest.append({"asset_id": asset_id, "day": item["day"], **built})
        previous_level = item["risk_level"]
    db.commit()
    return latest
