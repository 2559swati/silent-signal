"""Phase 6 Explainability Engine: RISK -> EXPLANATION.

Phase 5 answers "how risky is this situation?". Phase 6 answers "WHY is
this situation considered risky?" as a deterministic, transparent,
reproducible interpretation of the ALREADY CALCULATED Phase 3/4/5
evidence. Rule-based only: no LLM, no GenAI, no chatbot, no RAG, no
external AI API, no randomness. Identical evidence always yields the
identical explanation. The same generic rules process every asset; no
asset is special-cased.

Temperature honesty: the MVP has NO physical temperature sensor. Phase 4
defines temperature_score = (power_score + brightness_score) / 2 as a
temperature BEHAVIOR PROXY, and every Phase 6 temperature reason states
that it is a proxy -- never a sensor reading.

Factor rules (all thresholds centralized below)
----------------------------------------------
- The highest-scoring signal ALWAYS gets a factor (severity low means
  "no major contribution" wording).
- Every other signal with score >= FACTOR_THRESHOLD (0.30) gets a factor.
- Persistence gets a factor iff persistence_score >= FACTOR_THRESHOLD.
- Overall risk ALWAYS gets the final factor.
- Ordering is deterministic: signal factors by (score desc, tie-break
  order asc: power, brightness, temperature, maintenance, neighbor),
  then persistence, then overall risk last.

Severity (reuses the Phase 5 risk threshold cut points -- no conflicting
thresholds): score < 0.30 low; 0.30-0.50 medium; 0.50-0.75 high; >= 0.75
critical.
"""

import json

from sqlalchemy.orm import Session

from app.models.assets import Asset
from app.models.explanation_results import ExplanationResult
from app.models.fusion_results import FusionResult
from app.models.risk_results import RiskResult
from app.services.risk_engine import (
    ELEVATED_STATUSES,
    RISK_THRESHOLDS,
    persistence_update,
)

EXPLAIN_MODEL_VERSION = "explain_v1"

# Severity reuses the Phase 5 cut points (0.30 / 0.50 / 0.75) so the two
# phases can never disagree on what "elevated" means.
SEVERITY_THRESHOLDS = RISK_THRESHOLDS

# A signal/persistence only earns its own factor at/above this score. The
# top contributor is always explained regardless (with "no major ..."
# wording when it is low).
FACTOR_THRESHOLD = 0.30

# Persistence scores at/above this add the sustained-behavior clause to the
# summary (streak of ~4+ elevated days).
PERSISTENCE_CLAUSE_THRESHOLD = 0.50

# Fixed deterministic tie-break order for equal signal scores.
SIGNAL_ORDER = ("power", "brightness", "temperature", "maintenance", "neighbor")

SEVERITIES = ("low", "medium", "high", "critical")

TEMPERATURE_PROXY_NOTE = (
    "Temperature-related behavior proxy only; no physical temperature sensor exists."
)

SIGNAL_REASONS = {
    "power": {
        "low": "Power draw is within the normal fleet range; no major power contribution.",
        "medium": "Power draw is moderately elevated relative to the fleet baseline.",
        "high": "Power draw is abnormally high relative to the fleet baseline.",
        "critical": "Power draw is severely abnormal relative to the fleet baseline.",
    },
    "brightness": {
        "low": "Light output is within the normal fleet range; no major brightness contribution.",
        "medium": "Light output is moderately dimmer than the fleet baseline.",
        "high": "Light output is abnormally dim relative to the fleet baseline.",
        "critical": "Light output is severely degraded relative to the fleet baseline.",
    },
    "temperature": {
        "low": "Temperature-related behavior proxy is normal; no major thermal contribution.",
        "medium": "Temperature-related behavior proxy is moderately elevated (derived from power draw and light output; no physical temperature sensor exists).",
        "high": "Temperature-related behavior proxy is elevated, consistent with excess power draw and dim output (proxy only; no physical temperature sensor exists).",
        "critical": "Temperature-related behavior proxy is severely elevated, consistent with excess power draw and dim output (proxy only; no physical temperature sensor exists).",
    },
    "maintenance": {
        "low": "Maintenance history is sparse; no major maintenance contribution.",
        "medium": "Maintenance frequency is moderately above the fleet baseline.",
        "high": "Frequent maintenance relative to the fleet baseline contributes to risk.",
        "critical": "Very frequent maintenance relative to the fleet baseline strongly contributes to risk.",
    },
    "neighbor": {
        "low": "Nearby street-segment assets behave normally; no correlated concern.",
        "medium": "Nearby street-segment assets show moderately abnormal behavior.",
        "high": "Correlated abnormal behavior detected among nearby street-segment assets.",
        "critical": "Strongly correlated abnormal behavior among nearby street-segment assets.",
    },
}

SUMMARY_TEMPLATES = {
    "LOW": "Current evidence indicates low infrastructure risk.",
    "MEDIUM": "Multiple signals indicate moderate infrastructure risk.",
    "HIGH": "Multiple abnormal signals indicate elevated infrastructure risk.",
    "CRITICAL": "Multiple correlated signals and sustained abnormal behavior indicate critical infrastructure risk.",
}

PERSISTENCE_CLAUSE = " The condition has persisted over multiple days."


# ---------------------------------------------------------------------------
# Pure helpers (deterministic, no DB) -- directly unit tested.
# ---------------------------------------------------------------------------

def severity_for(score: float) -> str:
    """Map a [0, 1] score to low/medium/high/critical (Phase 5 cut points)."""
    if score >= SEVERITY_THRESHOLDS["CRITICAL"]:
        return "critical"
    if score >= SEVERITY_THRESHOLDS["HIGH"]:
        return "high"
    if score >= SEVERITY_THRESHOLDS["MEDIUM"]:
        return "medium"
    return "low"


def signal_reason(signal: str, severity: str) -> str:
    """Rule-based reason template for a signal/severity pair."""
    return SIGNAL_REASONS[signal][severity]


def persistence_reason(streak: int) -> str:
    """Rule-based reason for the persistence factor from the streak."""
    day_word = "day" if streak == 1 else "days"
    return (
        f"Abnormal behavior has persisted for {streak} consecutive elevated {day_word}."
    )


def build_summary(risk_level: str, persistence_score: float) -> str:
    """Deterministic level summary plus sustained-behavior clause when apt."""
    summary = SUMMARY_TEMPLATES[risk_level]
    if risk_level in ("HIGH", "CRITICAL") and persistence_score >= PERSISTENCE_CLAUSE_THRESHOLD:
        summary += PERSISTENCE_CLAUSE
    return summary


def build_explanation(evidence: dict) -> dict:
    """Build {summary, factors, evidence} purely from an evidence dict.

    evidence keys: anomaly_score, power_score, brightness_score,
    temperature_score, maintenance_score, neighbor_score, raw_fusion_score,
    smoothed_fusion_score, fusion_status, persistence_score, streak_days,
    risk_score, risk_level. No DB access; fully deterministic.
    """
    signals = {name: float(evidence[f"{name}_score"]) for name in SIGNAL_ORDER}
    persistence = float(evidence["persistence_score"])
    risk_score = float(evidence["risk_score"])
    risk_level = evidence["risk_level"]
    streak = int(evidence["streak_days"])

    # Signal factors: top contributor always; others iff >= threshold.
    ranked = sorted(signals.items(), key=lambda kv: (-kv[1], SIGNAL_ORDER.index(kv[0])))
    factors = []
    for position, (name, score) in enumerate(ranked):
        if position > 0 and score < FACTOR_THRESHOLD:
            continue
        severity = severity_for(score)
        factors.append(
            {
                "signal": name,
                "score": score,
                "severity": severity,
                "reason": signal_reason(name, severity),
            }
        )

    # Persistence factor (elevated only).
    if persistence >= FACTOR_THRESHOLD:
        factors.append(
            {
                "signal": "persistence",
                "score": persistence,
                "severity": severity_for(persistence),
                "reason": persistence_reason(streak),
            }
        )

    # Overall risk factor (always, last).
    factors.append(
        {
            "signal": "risk",
            "score": risk_score,
            "severity": risk_level.lower(),
            "reason": f"Overall infrastructure risk is {risk_level} (score {risk_score:.2f}).",
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
        "summary": build_summary(risk_level, persistence),
        "factors": factors,
        "evidence": snapshot,
    }


# ---------------------------------------------------------------------------
# Evidence loading (deterministic reads; never writes Phase 3/4/5 state).
# ---------------------------------------------------------------------------

def load_daily_evidence(db: Session):
    """Join fusion + risk rows per asset in chronological order.

    Returns {asset_id: [evidence-dict]} with streak_days replayed from the
    Phase 4 confirmed-status timeline using the Phase 5 streak rule
    (no duplicated logic). Raises if upstream evidence is missing.
    """
    fusion_rows = (
        db.query(FusionResult)
        .order_by(FusionResult.asset_id, FusionResult.day)
        .all()
    )
    if not fusion_rows:
        raise RuntimeError("No Phase 4 fusion results found; run the fusion pipeline first")
    risk_by_key = {
        (r.asset_id, r.day): r for r in db.query(RiskResult).all()
    }
    if not risk_by_key:
        raise RuntimeError("No Phase 5 risk results found; run the risk pipeline first")
    timeline = {}
    for f in fusion_rows:
        key = (f.asset_id, f.day)
        if key not in risk_by_key:
            raise RuntimeError(f"Missing Phase 5 risk row for asset/day {key}")
        r = risk_by_key[key]
        days = timeline.setdefault(f.asset_id, [])
        streak = persistence_update(
            days[-1]["streak_days"] if days else 0,
            f.status in ELEVATED_STATUSES,
        )
        days.append(
            {
                "asset_id": f.asset_id,
                "day": f.day,
                "anomaly_score": r.anomaly_score,
                "power_score": f.power_score,
                "brightness_score": f.brightness_score,
                "temperature_score": f.temperature_score,
                "maintenance_score": f.maintenance_score,
                "neighbor_score": f.neighbor_score,
                "raw_fusion_score": f.raw_score,
                "smoothed_fusion_score": f.smoothed_score,
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

def _upsert_explanation(db: Session, item: dict, built: dict):
    payload_factors = json.dumps(built["factors"])
    payload_evidence = json.dumps(built["evidence"])
    row = (
        db.query(ExplanationResult)
        .filter(
            ExplanationResult.asset_id == item["asset_id"],
            ExplanationResult.day == item["day"],
        )
        .one_or_none()
    )
    if row is None:
        row = ExplanationResult(
            asset_id=item["asset_id"],
            day=item["day"],
            risk_score=item["risk_score"],
            risk_level=item["risk_level"],
            summary=built["summary"],
            factors_json=payload_factors,
            evidence_json=payload_evidence,
            model_version=EXPLAIN_MODEL_VERSION,
        )
        db.add(row)
    else:
        row.risk_score = item["risk_score"]
        row.risk_level = item["risk_level"]
        row.summary = built["summary"]
        row.factors_json = payload_factors
        row.evidence_json = payload_evidence
        row.model_version = EXPLAIN_MODEL_VERSION
    return row


def compute_all_explanations(db: Session):
    """Run the full Phase 6 pipeline: evidence -> rules -> explanations.

    One explanation row per (asset_id, day), upserted idempotently.
    Never writes to Phase 3/4/5 state.
    """
    timeline = load_daily_evidence(db)
    n = 0
    for asset_id in sorted(timeline):
        for item in timeline[asset_id]:
            _upsert_explanation(db, item, build_explanation(item))
            n += 1
    db.commit()
    return {"assets": len(timeline), "explanations": n}


def compute_asset_explanation(asset_id: str, db: Session):
    """Recompute (and persist) the daily explanation timeline for one asset.

    Identical deterministic rules as compute_all_explanations, scoped to a
    single asset. Returns the latest day's full explanation dict.
    """
    asset = db.query(Asset).filter(Asset.id == asset_id).one_or_none()
    if asset is None:
        raise ValueError(f"unknown asset_id {asset_id}")
    timeline = load_daily_evidence(db)
    if asset_id not in timeline:
        raise RuntimeError("No Phase 4/5 evidence found for asset")
    latest = None
    for item in timeline[asset_id]:
        built = build_explanation(item)
        _upsert_explanation(db, item, built)
        latest = {"asset_id": asset_id, "day": item["day"], **built}
    db.commit()
    return latest
