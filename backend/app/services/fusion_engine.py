"""Phase 4 weak-signal fusion: WEAK SIGNALS -> SIGNAL FUSION -> EMERGING ANOMALY.

Combines five normalized weak-signal scores in [0, 1] (higher = stronger
abnormal evidence) into one fused emerging-anomaly score per asset per day.

Signals
-------
power_score        Abnormally HIGH power draw vs the fleet baseline.
brightness_score   Abnormally LOW light output vs the fleet baseline
                   (inverted: dimmer lamp => higher score).
temperature_score  TEMPERATURE-BEHAVIOR PROXY -- the Phase 2 dataset has NO
                   temperature sensor (sensor types are only power_watts,
                   brightness_pct, complaint_received), and Phase 2 must not
                   be modified, so no measured temperature exists. The proxy
                   is the mean of power_score and brightness_score: a lamp
                   drawing excess power while emitting less light dissipates
                   more heat. Deterministic, in [0, 1] by construction, and
                   never presented as a real sensor reading (field and docs
                   always call it a proxy).
maintenance_score  Maintenance frequency in the trailing 30-day window
                   relative to the fleet maximum in the same window
                   (count / fleet_max; 0 when the fleet has no records).
                   Pure frequency vs baseline -- a single routine visit does
                   NOT by itself produce a high score.
neighbor_score     Abnormal behavior among STREET-SEGMENT neighbors. The Phase 2
                   generator establishes neighbor relationships as same-row
                   adjacent assets on the 10x10 grid ("same street segment",
                   matching the generator's documented hero/neighbor trio),
                   and this signal reuses that relationship generically for
                   EVERY asset: same grid row, adjacent columns. The score is the mean of those
                   neighbors' own 4-signal base scores divided by 0.75 so it
                   stays in [0, 1]. It never copies the target asset's own
                   score and no asset code is hardcoded.

Fleet references (power/brightness) are fixed percentiles of ALL asset
daily-means over the full frozen 30-day window, recomputed deterministically
from the same data on every run (identical data => identical references =>
identical scores). One-sided scoring keeps typical fleet variation near 0:
only deviations toward the abnormal side accumulate score.

Fusion
------
fusion = 0.25*power + 0.20*brightness + 0.10*temperature
       + 0.20*maintenance + 0.25*neighbor            (weights sum to 1.0)

Status (from the SMOOTHED score, deterministic constants)
---------------------------------------------------------
score < 0.30                  NORMAL
0.30 <= score < 0.50          WATCH
0.50 <= score < 0.75          EMERGING
score >= 0.75                 CRITICAL

EMA smoothing (alpha = 0.3, per asset, chronological)
-----------------------------------------------------
ema(day_0) = raw(day_0)                       (initial value = first raw score)
ema(day_N) = 0.3 * raw(day_N) + 0.7 * ema(day_N-1)

Two-consecutive-day confirmation rule
-------------------------------------
An UPGRADE to a higher status is confirmed on day D only if the smoothed
status was already at-or-above that level on day D-1 (i.e. the higher state
persisted for 2 consecutive smoothed days); otherwise the previously
confirmed status is held. Downgrades and unchanged levels apply immediately.
Day 0 seeds both EMA and confirmed status (no history to delay against).
"""

from bisect import bisect_left
from datetime import timedelta

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.models.assets import Asset
from app.models.fusion_results import FusionResult
from app.models.maintenance_records import MaintenanceRecord
from app.models.sensor_readings import SensorReading
from data import config

# Exact Phase 4 weights. Fixed constants -- never learned, never changed
# dynamically. Sum = 1.0.
WEIGHTS = {
    "power": 0.25,
    "brightness": 0.20,
    "temperature": 0.10,
    "maintenance": 0.20,
    "neighbor": 0.25,
}

FUSION_MODEL_VERSION = "fusion_v1"

ALPHA = 0.3  # EMA smoothing factor (deterministic constant)

STATUS_ORDER = {"NORMAL": 0, "WATCH": 1, "EMERGING": 2, "CRITICAL": 3}
THRESHOLDS = {
    "NORMAL": 0.0,
    "WATCH": 0.3,
    "EMERGING": 0.5,
    "CRITICAL": 0.75,
}

MAINTENANCE_WINDOW_DAYS = 30  # trailing window for maintenance frequency


# ---------------------------------------------------------------------------
# Pure helpers (deterministic, no DB) -- directly unit tested.
# ---------------------------------------------------------------------------

def determine_status(score: float) -> str:
    """Map a smoothed fusion score to a status using fixed thresholds."""
    if score >= THRESHOLDS["CRITICAL"]:
        return "CRITICAL"
    if score >= THRESHOLDS["EMERGING"]:
        return "EMERGING"
    if score >= THRESHOLDS["WATCH"]:
        return "WATCH"
    return "NORMAL"


def ema_update(previous_ema, raw_score: float, alpha: float = ALPHA) -> float:
    """One EMA step. previous_ema=None (first day) seeds EMA with raw_score."""
    if previous_ema is None:
        return float(raw_score)
    return float(alpha * raw_score + (1.0 - alpha) * previous_ema)


def confirm_transition(previous_confirmed: str, previous_smoothed_status: str,
                       candidate_status: str) -> str:
    """Two-consecutive-day rule (see module docstring).

    Upgrades require the smoothed status to have been at-or-above the
    candidate level yesterday too; otherwise the previous confirmed status
    is held. Downgrades / unchanged levels apply immediately.
    """
    if STATUS_ORDER[candidate_status] <= STATUS_ORDER[previous_confirmed]:
        return candidate_status
    if STATUS_ORDER[previous_smoothed_status] >= STATUS_ORDER[candidate_status]:
        return candidate_status
    return previous_confirmed


def onesided_high(value: float, median: float, high_ref: float) -> float:
    """Score in [0, 1] for abnormally HIGH values (0 at/below median)."""
    denom = high_ref - median
    if denom <= 0:
        return 0.0
    return min(1.0, max(0.0, (value - median) / denom))


def onesided_low(value: float, median: float, low_ref: float) -> float:
    """Score in [0, 1] for abnormally LOW values (0 at/above median)."""
    denom = median - low_ref
    if denom <= 0:
        return 0.0
    return min(1.0, max(0.0, (median - value) / denom))


def fuse_signals(power: float, brightness: float, temperature: float,
                 maintenance: float, neighbor: float) -> float:
    """Exact weighted fusion. Inputs in [0, 1]; weights sum to 1.0."""
    raw = (
        WEIGHTS["power"] * power
        + WEIGHTS["brightness"] * brightness
        + WEIGHTS["temperature"] * temperature
        + WEIGHTS["maintenance"] * maintenance
        + WEIGHTS["neighbor"] * neighbor
    )
    return min(1.0, max(0.0, raw))


def grid_neighbors(external_code: str):
    """Street-segment neighbors of an asset code, derived from data.config.

    Generic for every asset: the 10x10 row-major grid (SL-1001..SL-1100)
    models streets as rows, so an asset's neighbors are the adjacent
    columns in the SAME row -- exactly the relationship the Phase 2
    generator uses for correlated drift ("same street segment"). Codes
    outside the grid have no neighbors. Sorted for determinism.
    """
    try:
        idx = int(external_code.split("-")[1]) - config.FIRST_CODE
    except (IndexError, ValueError):
        return []
    if idx < 0 or idx >= config.GRID_ROWS * config.GRID_COLS:
        return []
    row, col = idx // config.GRID_COLS, idx % config.GRID_COLS
    out = []
    for dc in (-1, 1):
        nc = col + dc
        if 0 <= nc < config.GRID_COLS:
            out.append(f"SL-{config.FIRST_CODE + row * config.GRID_COLS + nc}")
    return sorted(out)


# ---------------------------------------------------------------------------
# Data loading / batch scoring (deterministic; no writes).
# ---------------------------------------------------------------------------

def _day_bounds():
    start = config.FIXED_START
    return [start + timedelta(days=i) for i in range(config.DATASET_DAYS + 1)]


def build_signal_table(db: Session):
    """Score all five signals + raw fusion for every asset and day.

    Returns (days, table) where days is the sorted list of dates and
    table[day][asset_id] = dict(power_score, brightness_score,
    temperature_score, maintenance_score, neighbor_score, raw_score).
    Pure computation -- performs no writes. Deterministic: identical DB
    content always yields identical output.
    """
    assets = db.query(Asset).order_by(Asset.external_code).all()
    asset_ids = [a.id for a in assets]
    code_of = {a.id: a.external_code for a in assets}
    id_of_code = {a.external_code: a.id for a in assets}

    bounds = _day_bounds()
    window_start, window_end = bounds[0], bounds[-1]

    readings = (
        db.query(SensorReading)
        .filter(
            SensorReading.recorded_at >= window_start,
            SensorReading.recorded_at < window_end,
            SensorReading.sensor_type.in_(
                [config.SENSOR_POWER, config.SENSOR_BRIGHTNESS]
            ),
        )
        .all()
    )
    if not readings:
        raise RuntimeError("No sensor data found for the configured period")

    df = pd.DataFrame(
        [
            {
                "asset_id": r.asset_id,
                "day": r.recorded_at.date(),
                "sensor_type": r.sensor_type,
                "value": r.value,
            }
            for r in readings
        ]
    )
    power_daily = (
        df[df.sensor_type == config.SENSOR_POWER]
        .groupby(["asset_id", "day"])
        .value.mean()
    )
    bright_daily = (
        df[df.sensor_type == config.SENSOR_BRIGHTNESS]
        .groupby(["asset_id", "day"])
        .value.mean()
    )

    # Fleet references: fixed percentiles over ALL asset daily-means in the
    # full window (deterministic; recomputed from identical data each run).
    p_vals = power_daily.to_numpy(dtype=float)
    b_vals = bright_daily.to_numpy(dtype=float)
    p50, p99 = float(np.percentile(p_vals, 50)), float(np.percentile(p_vals, 99))
    b50, b01 = float(np.percentile(b_vals, 50)), float(np.percentile(b_vals, 1))
    refs = {"p50": p50, "p99": p99, "b50": b50, "b01": b01}

    # Fallbacks for asset-days with no readings (cannot happen on the frozen
    # Phase 2 dataset, which covers every asset-day; guards only).
    asset_power_fallback = {
        aid: float(power_daily.xs(aid, level="asset_id").mean())
        for aid in asset_ids
        if aid in power_daily.index.get_level_values("asset_id")
    }
    asset_bright_fallback = {
        aid: float(bright_daily.xs(aid, level="asset_id").mean())
        for aid in asset_ids
        if aid in bright_daily.index.get_level_values("asset_id")
    }

    # Maintenance: per-asset sorted performed dates, loaded once.
    maint_rows = db.query(MaintenanceRecord.asset_id, MaintenanceRecord.performed_at).all()
    maint_dates = {}
    for aid, ts in maint_rows:
        maint_dates.setdefault(aid, []).append(ts.date())
    for dates in maint_dates.values():
        dates.sort()

    days = sorted({b.date() for b in bounds[:-1]})
    table = {}
    for day in days:
        day_scores = {}
        # Pass 1: four own-signals + 4-signal base (neighbor needs these).
        base4 = {}
        for aid in asset_ids:
            try:
                mean_p = float(power_daily.loc[(aid, day)])
            except KeyError:
                mean_p = asset_power_fallback.get(aid, p50)
            try:
                mean_b = float(bright_daily.loc[(aid, day)])
            except KeyError:
                mean_b = asset_bright_fallback.get(aid, b50)
            p = onesided_high(mean_p, p50, p99)
            b = onesided_low(mean_b, b50, b01)
            t = (p + b) / 2.0  # TEMPERATURE-BEHAVIOR PROXY (see docstring)
            window_lo = day - timedelta(days=MAINTENANCE_WINDOW_DAYS - 1)
            dates = maint_dates.get(aid, [])
            m_count = bisect_left(dates, day + timedelta(days=1)) - bisect_left(
                dates, window_lo
            )
            day_scores[aid] = {
                "power_score": p,
                "brightness_score": b,
                "temperature_score": t,
                "_maint_count": m_count,
            }
            base4[aid] = (
                WEIGHTS["power"] * p
                + WEIGHTS["brightness"] * b
                + WEIGHTS["temperature"] * t
            )
        # Fleet maintenance baseline for THIS day: max trailing-window count.
        fleet_max = max(
            [s["_maint_count"] for s in day_scores.values()] + [0]
        )
        # Neighbor base lookup needs base4 + maintenance part per asset.
        full_base = {}
        for aid in asset_ids:
            m = (
                day_scores[aid]["_maint_count"] / fleet_max
                if fleet_max > 0
                else 0.0
            )
            m = min(1.0, max(0.0, m))
            day_scores[aid]["maintenance_score"] = m
            full_base[aid] = base4[aid] + WEIGHTS["maintenance"] * m
        # Pass 2: neighbor signal (mean of neighbors' 4-signal base / 0.75).
        for aid in asset_ids:
            nbr_ids = [
                id_of_code[c]
                for c in grid_neighbors(code_of[aid])
                if c in id_of_code
            ]
            if nbr_ids:
                n = sum(full_base[nid] for nid in nbr_ids) / len(nbr_ids) / 0.75
            else:
                n = 0.0
            n = min(1.0, max(0.0, n))
            s = day_scores[aid]
            s["neighbor_score"] = n
            s["raw_score"] = fuse_signals(
                s["power_score"],
                s["brightness_score"],
                s["temperature_score"],
                s["maintenance_score"],
                n,
            )
            del s["_maint_count"]
        table[day] = day_scores
    return days, table, refs


# ---------------------------------------------------------------------------
# Persistence (upsert / idempotent).
# ---------------------------------------------------------------------------

def _upsert_day(db: Session, asset_id: str, day, signals: dict,
                smoothed: float, status: str):
    row = (
        db.query(FusionResult)
        .filter(FusionResult.asset_id == asset_id, FusionResult.day == day)
        .one_or_none()
    )
    if row is None:
        row = FusionResult(
            asset_id=asset_id,
            day=day,
            power_score=signals["power_score"],
            brightness_score=signals["brightness_score"],
            temperature_score=signals["temperature_score"],
            maintenance_score=signals["maintenance_score"],
            neighbor_score=signals["neighbor_score"],
            raw_score=signals["raw_score"],
            smoothed_score=smoothed,
            status=status,
            model_version=FUSION_MODEL_VERSION,
        )
        db.add(row)
    else:
        row.power_score = signals["power_score"]
        row.brightness_score = signals["brightness_score"]
        row.temperature_score = signals["temperature_score"]
        row.maintenance_score = signals["maintenance_score"]
        row.neighbor_score = signals["neighbor_score"]
        row.raw_score = signals["raw_score"]
        row.smoothed_score = smoothed
        row.status = status
        row.model_version = FUSION_MODEL_VERSION
    return row


def compute_all_days(db: Session):
    """Run the full Phase 4 pipeline: signals -> fusion -> EMA -> confirm.

    Days are processed chronologically per asset; EMA is seeded with the
    first raw score and the two-day rule is applied against in-memory
    history. Results are upserted on (asset_id, day), so re-running is
    idempotent (same values, no duplicate rows).
    """
    from datetime import datetime

    days, table, _refs = build_signal_table(db)
    asset_ids = sorted({aid for d in days for aid in table[d]})
    ema = {aid: None for aid in asset_ids}
    confirmed = {}
    prev_candidate = {}
    for day in days:
        for aid in asset_ids:
            signals = table[day][aid]
            ema[aid] = ema_update(ema[aid], signals["raw_score"])
            candidate = determine_status(ema[aid])
            if aid not in confirmed:
                # Day 0 seeds the confirmed status (nothing to delay against).
                status = candidate
            else:
                status = confirm_transition(
                    confirmed[aid], prev_candidate[aid], candidate
                )
            confirmed[aid] = status
            prev_candidate[aid] = candidate
            _upsert_day(db, aid, day, signals, ema[aid], status)
        db.commit()
    return {"days": len(days), "assets": len(asset_ids)}


def compute_fusion_for_day(day_index: int, db: Session):
    """Score a single 0-based day and persist it.

    The EMA/confirmation chain is replayed deterministically from day 0
    through day_index in memory (cheap: 30 days), so the single-day result
    is exactly what the full run would store. Only day_index is written.
    """
    from datetime import datetime  # noqa: F401 (kept for symmetry)

    days, table, _refs = build_signal_table(db)
    if day_index < 0 or day_index >= len(days):
        raise ValueError(f"day_index {day_index} out of range 0..{len(days) - 1}")
    asset_ids = sorted({aid for d in days for aid in table[d]})
    ema = {aid: None for aid in asset_ids}
    confirmed = {}
    prev_candidate = {}
    for pos, day in enumerate(days):
        for aid in asset_ids:
            signals = table[day][aid]
            ema[aid] = ema_update(ema[aid], signals["raw_score"])
            candidate = determine_status(ema[aid])
            if aid not in confirmed:
                status = candidate
            else:
                status = confirm_transition(
                    confirmed[aid], prev_candidate[aid], candidate
                )
            confirmed[aid] = status
            prev_candidate[aid] = candidate
        if pos == day_index:
            for aid in asset_ids:
                _upsert_day(
                    db, aid, day, table[day][aid], ema[aid], confirmed[aid]
                )
            db.commit()
            return {"day": day.isoformat(), "assets": len(asset_ids)}
