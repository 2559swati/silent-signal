"""Phase 5 Risk Engine: EMERGING ANOMALY -> RISK.

Phase 4 answers "are multiple weak signals agreeing this asset behaves
abnormally?". Phase 5 answers "how risky is this situation?" by combining
the ALREADY CALCULATED Phase 3/4 evidence -- no new sensors, no new ML
model, no randomness, no LLM. The same generic algorithm processes every
asset; no asset is special-cased.

Inputs (per asset, per day; all in [0, 1])
-----------------------------------------
anomaly_score          Phase 3 IsolationForest fleet-normalized score. It is
                       window-level evidence (one value per asset for the
                       frozen dataset), recomputed read-only through the
                       existing build_features + _train_and_score code path
                       -- deterministic on identical data -- and persisted on
                       each risk row for auditability. Phase 3 logic itself
                       is never modified.
raw_fusion_score       Phase 4 raw fusion (fusion_results.raw_score).
smoothed_fusion_score  Phase 4 EMA-smoothed fusion (fusion_results.smoothed_score).
persistence_score      Sustained-abnormality amplifier in [0, 1], computed
                       from the existing Phase 4 confirmed-status timeline
                       (see below).

Risk formula (exact, weights sum to 1.0)
----------------------------------------
risk_score = 0.30 * anomaly_score
           + 0.25 * raw_fusion_score
           + 0.30 * smoothed_fusion_score
           + 0.15 * persistence_score
clamped to [0, 1].

Persistence (deterministic)
---------------------------
Elevated day  = Phase 4 confirmed status in {EMERGING, CRITICAL}.
streak(D)     = number of consecutive elevated days ending on day D
                (inclusive); a non-elevated day resets the streak to 0.
persistence_score(D) = min(1.0, streak(D) / 7).
A single isolated spike therefore scores at most 1/7 (~0.143), while an
abnormal condition sustained 7+ days scores 1.0. Day 0 has no history, so
its streak is 1 if elevated else 0.

Risk levels (deterministic constants)
-------------------------------------
risk_score < 0.30                 LOW
0.30 <= risk_score < 0.50         MEDIUM
0.50 <= risk_score < 0.75         HIGH
risk_score >= 0.75                CRITICAL

Risk is CALCULATED from underlying evidence: it is never a copy of the
Phase 4 status. Two assets sharing a fusion status routinely receive
different risk scores/levels (and vice versa) because the anomaly score,
the raw-vs-smoothed gap and persistence all contribute independently.
"""

from sqlalchemy.orm import Session

from app.models.assets import Asset
from app.models.fusion_results import FusionResult
from app.models.risk_results import RiskResult
from ml.anomaly import _train_and_score
from ml.features import build_features

# Exact Phase 5 weights. Fixed constants -- never learned, never changed
# dynamically. Sum = 1.0.
RISK_WEIGHTS = {
    "anomaly": 0.30,
    "raw_fusion": 0.25,
    "smoothed_fusion": 0.30,
    "persistence": 0.15,
}

RISK_MODEL_VERSION = "risk_v1"

RISK_LEVEL_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
RISK_THRESHOLDS = {
    "LOW": 0.0,
    "MEDIUM": 0.30,
    "HIGH": 0.50,
    "CRITICAL": 0.75,
}

# A Phase 4 day counts as elevated for persistence purposes.
ELEVATED_STATUSES = frozenset({"EMERGING", "CRITICAL"})
# Consecutive elevated days that saturate persistence_score at 1.0.
PERSISTENCE_SATURATION_DAYS = 7


# ---------------------------------------------------------------------------
# Pure helpers (deterministic, no DB) -- directly unit tested.
# ---------------------------------------------------------------------------

def determine_risk_level(risk_score: float) -> str:
    """Map a risk score to a level using fixed thresholds."""
    if risk_score >= RISK_THRESHOLDS["CRITICAL"]:
        return "CRITICAL"
    if risk_score >= RISK_THRESHOLDS["HIGH"]:
        return "HIGH"
    if risk_score >= RISK_THRESHOLDS["MEDIUM"]:
        return "MEDIUM"
    return "LOW"


def persistence_update(previous_streak: int, status_elevated_today: bool) -> int:
    """Advance the consecutive-elevated-day streak (pure, deterministic)."""
    if status_elevated_today:
        return previous_streak + 1
    return 0


def persistence_score(streak: int,
                      saturation_days: int = PERSISTENCE_SATURATION_DAYS) -> float:
    """Map a streak to [0, 1]: min(1, streak / saturation_days)."""
    if saturation_days <= 0:
        return 0.0
    return min(1.0, max(0.0, streak / saturation_days))


def calculate_risk(anomaly_score: float, raw_fusion: float,
                   smoothed_fusion: float, persistence: float) -> float:
    """Exact weighted risk. Inputs in [0, 1]; weights sum to 1.0."""
    risk = (
        RISK_WEIGHTS["anomaly"] * anomaly_score
        + RISK_WEIGHTS["raw_fusion"] * raw_fusion
        + RISK_WEIGHTS["smoothed_fusion"] * smoothed_fusion
        + RISK_WEIGHTS["persistence"] * persistence
    )
    return min(1.0, max(0.0, risk))


# ---------------------------------------------------------------------------
# Evidence loading (deterministic reads; no writes to Phase 3/4 state).
# ---------------------------------------------------------------------------

def load_anomaly_scores(db: Session):
    """Phase 3 anomaly score per asset_id via the existing read-only path."""
    features = build_features(db)
    scores_df = _train_and_score(features)
    return {row["asset_id"]: float(row["score"]) for _, row in scores_df.iterrows()}


def load_fusion_timeline(db: Session):
    """Phase 4 rows per asset ordered chronologically: {aid: [FusionResult]}."""
    rows = (
        db.query(FusionResult)
        .order_by(FusionResult.asset_id, FusionResult.day)
        .all()
    )
    if not rows:
        raise RuntimeError("No Phase 4 fusion results found; run the fusion pipeline first")
    timeline = {}
    for row in rows:
        timeline.setdefault(row.asset_id, []).append(row)
    return timeline


# ---------------------------------------------------------------------------
# Persistence (upsert / idempotent).
# ---------------------------------------------------------------------------

def _upsert_risk(db: Session, asset_id: str, day, anomaly: float,
                 raw: float, smoothed: float, persist: float,
                 risk: float, level: str):
    row = (
        db.query(RiskResult)
        .filter(RiskResult.asset_id == asset_id, RiskResult.day == day)
        .one_or_none()
    )
    if row is None:
        row = RiskResult(
            asset_id=asset_id,
            day=day,
            anomaly_score=anomaly,
            fusion_score=raw,
            smoothed_fusion_score=smoothed,
            persistence_score=persist,
            risk_score=risk,
            risk_level=level,
            model_version=RISK_MODEL_VERSION,
        )
        db.add(row)
    else:
        row.anomaly_score = anomaly
        row.fusion_score = raw
        row.smoothed_fusion_score = smoothed
        row.persistence_score = persist
        row.risk_score = risk
        row.risk_level = level
        row.model_version = RISK_MODEL_VERSION
    return row


def compute_all_risks(db: Session):
    """Run the full Phase 5 pipeline: evidence -> persistence -> risk.

    Reads existing Phase 3 (in-memory deterministic scoring) and Phase 4
    (persisted daily rows) evidence, walks each asset's timeline
    chronologically tracking the elevated streak, and upserts one risk row
    per (asset_id, day). Re-running is idempotent (same values, no
    duplicate rows). Never writes to Phase 3/4 state.
    """
    anomaly_scores = load_anomaly_scores(db)
    timeline = load_fusion_timeline(db)
    asset_ids = sorted(timeline)
    n_days = 0
    for aid in asset_ids:
        anomaly = anomaly_scores.get(aid, 0.0)
        streak = 0
        for fusion_row in timeline[aid]:
            streak = persistence_update(
                streak, fusion_row.status in ELEVATED_STATUSES
            )
            persist = persistence_score(streak)
            risk = calculate_risk(
                anomaly,
                fusion_row.raw_score,
                fusion_row.smoothed_score,
                persist,
            )
            level = determine_risk_level(risk)
            _upsert_risk(
                db, aid, fusion_row.day, anomaly,
                fusion_row.raw_score, fusion_row.smoothed_score,
                persist, risk, level,
            )
            n_days += 1
    db.commit()
    return {"assets": len(asset_ids), "risk_results": n_days}


def compute_asset_risk(asset_id: str, db: Session):
    """Recompute (and persist) the full daily risk timeline for one asset.

    Uses the identical deterministic chain as compute_all_risks, scoped to a
    single asset. Returns the latest day's summary dict.
    """
    asset = db.query(Asset).filter(Asset.id == asset_id).one_or_none()
    if asset is None:
        raise ValueError(f"unknown asset_id {asset_id}")
    anomaly_scores = load_anomaly_scores(db)
    rows = (
        db.query(FusionResult)
        .filter(FusionResult.asset_id == asset_id)
        .order_by(FusionResult.day)
        .all()
    )
    if not rows:
        raise RuntimeError("No Phase 4 fusion results found for asset")
    anomaly = anomaly_scores.get(asset_id, 0.0)
    streak = 0
    latest = None
    for fusion_row in rows:
        streak = persistence_update(streak, fusion_row.status in ELEVATED_STATUSES)
        persist = persistence_score(streak)
        risk = calculate_risk(anomaly, fusion_row.raw_score, fusion_row.smoothed_score, persist)
        level = determine_risk_level(risk)
        _upsert_risk(
            db, asset_id, fusion_row.day, anomaly,
            fusion_row.raw_score, fusion_row.smoothed_score, persist, risk, level,
        )
        latest = {
            "day": fusion_row.day,
            "anomaly_score": anomaly,
            "fusion_score": fusion_row.raw_score,
            "smoothed_fusion_score": fusion_row.smoothed_score,
            "persistence_score": persist,
            "risk_score": risk,
            "risk_level": level,
        }
    db.commit()
    return latest
