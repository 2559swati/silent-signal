"""Phase 2 deterministic synthetic dataset generator (Blueprint Section 5).

Produces, with numpy.random.default_rng(42) only:
  - 100 streetlight assets (SL-1001..SL-1100) on a deterministic 10x10 grid,
    exact category mix 70 healthy / 15 watch / 10 emerging / 5 critical
  - 30 days of operating-hour readings: power_watts + brightness_pct
    (100 x 30 x 12 x 2 = 72,000 rows) plus sparse complaint_received rows
  - scripted gradual night-only drift for SL-1042 from day index 9
  - weaker correlated drift for neighbors SL-1041 / SL-1043
  - realistic maintenance history + one extra last-week visit for SL-1042

Schema note: Phase 1 tables are frozen EAV (sensor_readings has
sensor_type/value columns), so per-metric rows are used and only the two
drift-critical signals plus the complaint flag are materialized. The full
30x24 hourly coverage applies to operating hours (lamps are off daytime
by design; absence of daytime rows is the off state, never degradation).

Everything is inserted in ONE database transaction; any error rolls back.
"""

import os
import sys
import uuid
from datetime import timedelta

import numpy as np

# Make both `app.*` (backend/) and `data.*` (repo root) importable whether
# this runs under pytest, uvicorn, or as a script.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_THIS_DIR)  # silent-signal/
_BACKEND_DIR = os.path.join(_REPO_ROOT, "backend")
for _p in (_REPO_ROOT, _BACKEND_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from data import config  # noqa: E402
from app.models.anomalies import Anomaly  # noqa: E402,F401
from app.models.assets import Asset  # noqa: E402
from app.models.maintenance_records import MaintenanceRecord  # noqa: E402
from app.models.recommendations import Recommendation  # noqa: E402,F401
from app.models.sensor_readings import SensorReading  # noqa: E402
from app.models.signal_contributions import SignalContribution  # noqa: E402,F401
from app.models.tee_analysis import TEEAnalysis  # noqa: E402,F401

_DNS = uuid.NAMESPACE_URL


def _asset_uuid(code: str) -> str:
    return str(uuid.uuid5(_DNS, f"silent-signal:asset:{code}"))


def _reading_uuid(code: str, ts, sensor_type: str) -> str:
    return str(uuid.uuid5(_DNS, f"silent-signal:reading:{code}:{ts.isoformat()}:{sensor_type}"))


def _maint_uuid(code: str, ts, idx: int) -> str:
    return str(uuid.uuid5(_DNS, f"silent-signal:maint:{code}:{ts.isoformat()}:{idx}"))


def grid_position(code_index: int):
    """Row-major 10x10 grid position for the i-th asset (0-based)."""
    return code_index // config.GRID_COLS, code_index % config.GRID_COLS


def grid_latlon(code_index: int):
    row, col = grid_position(code_index)
    return (
        config.BASE_LAT + row * config.GRID_STEP_LAT,
        config.BASE_LON + col * config.GRID_STEP_LON,
    )


def build_plan():
    """Deterministic generation plan (pure data, no DB). Returns dict."""
    rng = np.random.default_rng(config.RANDOM_SEED)

    codes = [f"SL-{config.FIRST_CODE + i}" for i in range(config.NUM_ASSETS)]

    # Exact category mix: pin hero + neighbors first, fill the rest.
    status_of = {
        config.SL_1042_CODE: "emerging",
        **{n: "watch" for n in config.NEIGHBORS},
    }
    remaining = [c for c in codes if c not in status_of]
    perm = rng.permutation(len(remaining))
    ordered = [remaining[i] for i in perm]
    need = {"healthy": 70, "watch": 13, "emerging": 9, "critical": 5}
    pos = 0
    for cat in ("healthy", "watch", "emerging", "critical"):
        for _ in range(need[cat]):
            status_of[ordered[pos]] = cat
            pos += 1

    assets = []
    for i, code in enumerate(codes):
        lat, lon = grid_latlon(i)
        assets.append(
            {
                "id": _asset_uuid(code),
                "external_code": code,
                "criticality": int(rng.integers(1, 6)),
                "public_exposure": int(rng.integers(1, 6)),
                "status": status_of[code],
                "_lat": lat,
                "_lon": lon,
            }
        )

    base_power = {a["external_code"]: config.BASE_POWER_W + float(rng.normal(0, 2.5)) for a in assets}
    base_bright = {a["external_code"]: config.BASE_BRIGHTNESS_PCT + float(rng.normal(0, 1.5)) for a in assets}

    # Sparse deterministic complaints on non-hero assets (hero: never).
    others = [c for c in codes if c != config.SL_1042_CODE]
    complaint_events = set()
    while len(complaint_events) < config.OTHER_COMPLAINT_COUNT:
        c = others[int(rng.integers(0, len(others)))]
        d = int(rng.integers(0, config.DATASET_DAYS))
        h = sorted(config.OPERATING_HOURS)[int(rng.integers(0, len(config.OPERATING_HOURS)))]
        complaint_events.add((c, d, h))

    readings = []
    op_hours = sorted(config.OPERATING_HOURS)
    for day in range(config.DATASET_DAYS):
        drift_days = max(0, day - config.DRIFT_START_DAY_INDEX)
        sl_p_drift = drift_days * config.POWER_DRIFT_W_PER_DAY
        sl_b_drift = drift_days * config.BRIGHTNESS_DRIFT_PP_PER_DAY
        for hour in op_hours:
            ts = config.FIXED_START + timedelta(days=day, hours=hour)
            shared_p = float(rng.normal(0, 0.3))
            shared_b = float(rng.normal(0, 0.3))
            sl_np = float(rng.normal(0, 0.35))
            sl_nb = float(rng.normal(0, 0.4))
            setback = hour in config.SETBACK_HOURS
            dim_p = -5.0 if setback else 0.0
            dim_b = -7.0 if setback else 0.0
            for a in assets:
                code = a["external_code"]
                own_p = float(rng.normal(0, 0.35))
                own_b = float(rng.normal(0, 0.4))
                if code == config.SL_1042_CODE:
                    power = base_power[code] + dim_p + 0.6 * shared_p + sl_np + sl_p_drift
                    bright = base_bright[code] + dim_b + 0.6 * shared_b + sl_nb + sl_b_drift
                elif code in config.NEIGHBORS:
                    power = (
                        base_power[code] + dim_p + 0.6 * shared_p + own_p
                        + sl_p_drift * config.NEIGHBOR_DRIFT_FRACTION + 0.3 * sl_np
                    )
                    bright = (
                        base_bright[code] + dim_b + 0.6 * shared_b + own_b
                        + sl_b_drift * config.NEIGHBOR_DRIFT_FRACTION + 0.3 * sl_nb
                    )
                else:
                    power = base_power[code] + dim_p + 0.6 * shared_p + own_p
                    bright = base_bright[code] + dim_b + 0.6 * shared_b + own_b
                power = min(max(power, config.POWER_MIN_W), config.POWER_MAX_W)
                bright = min(max(bright, config.BRIGHTNESS_MIN_PCT), config.BRIGHTNESS_MAX_PCT)
                readings.append(
                    {
                        "id": _reading_uuid(code, ts, config.SENSOR_POWER),
                        "asset_id": a["id"],
                        "recorded_at": ts,
                        "sensor_type": config.SENSOR_POWER,
                        "value": power,
                        "_code": code,
                    }
                )
                readings.append(
                    {
                        "id": _reading_uuid(code, ts, config.SENSOR_BRIGHTNESS),
                        "asset_id": a["id"],
                        "recorded_at": ts,
                        "sensor_type": config.SENSOR_BRIGHTNESS,
                        "value": bright,
                        "_code": code,
                    }
                )
                if code == config.SL_1042_CODE:
                    readings.append(
                        {
                            "id": _reading_uuid(code, ts, config.SENSOR_COMPLAINT),
                            "asset_id": a["id"],
                            "recorded_at": ts,
                            "sensor_type": config.SENSOR_COMPLAINT,
                            "value": 0.0,
                            "_code": code,
                        }
                    )
                if (code, day, hour) in complaint_events:
                    readings.append(
                        {
                            "id": _reading_uuid(code, ts, config.SENSOR_COMPLAINT + ":event"),
                            "asset_id": a["id"],
                            "recorded_at": ts,
                            "sensor_type": config.SENSOR_COMPLAINT,
                            "value": 1.0,
                            "_code": code,
                        }
                    )

    maintenance = []
    reasons = [
        "Routine preventive inspection - no issues found",
        "Lamp cleaned and wiring checked",
        "Scheduled patrol check - all nominal",
    ]
    for a in assets:
        code = a["external_code"]
        if rng.random() < 0.45:
            d = int(rng.integers(0, 21))
            ts = config.FIXED_START + timedelta(days=d, hours=10)
            maintenance.append(
                {
                    "id": _maint_uuid(code, ts, 0),
                    "asset_id": a["id"],
                    "performed_at": ts,
                    "description": reasons[int(rng.integers(0, len(reasons)))],
                    "_code": code,
                }
            )
            if rng.random() < 0.15:
                d2 = int(rng.integers(0, 21))
                ts2 = config.FIXED_START + timedelta(days=d2, hours=14)
                maintenance.append(
                    {
                        "id": _maint_uuid(code, ts2, 1),
                        "asset_id": a["id"],
                        "performed_at": ts2,
                        "description": reasons[int(rng.integers(0, len(reasons)))],
                        "_code": code,
                    }
                )
    # SL-1042: one routine record plus ONE EXTRA last-week weak-signal visit.
    sl_id = _asset_uuid(config.SL_1042_CODE)
    early = config.FIXED_START + timedelta(days=6, hours=10)
    late = config.FIXED_START + timedelta(days=25, hours=10)
    maintenance.append(
        {
            "id": _maint_uuid(config.SL_1042_CODE, early, 0),
            "asset_id": sl_id,
            "performed_at": early,
            "description": "Scheduled inspection - all nominal",
            "_code": config.SL_1042_CODE,
        }
    )
    maintenance.append(
        {
            "id": _maint_uuid(config.SL_1042_CODE, late, 1),
            "asset_id": sl_id,
            "performed_at": late,
            "description": "Follow-up check - light output slightly dimmer than baseline, monitor",
            "_code": config.SL_1042_CODE,
        }
    )

    # Deterministic ordering: asset + timestamp (+ sensor type).
    readings.sort(key=lambda r: (r["_code"], r["recorded_at"], r["sensor_type"]))
    maintenance.sort(key=lambda m: (m["_code"], m["performed_at"]))

    asset_rows = [{k: v for k, v in a.items() if not k.startswith("_")} for a in assets]
    reading_rows = [{k: v for k, v in r.items() if not k.startswith("_")} for r in readings]
    maint_rows = [{k: v for k, v in m.items() if not k.startswith("_")} for m in maintenance]
    return {"assets": asset_rows, "readings": reading_rows, "maintenance": maint_rows}


def reset_and_generate(db_session=None):
    """Regenerate the full deterministic dataset in ONE transaction.

    Deletes existing demo data (children first for FK safety), bulk
    inserts the fresh plan, commits once. Rolls back everything on error.
    Returns (assets, readings, maintenance) counts.
    """
    from app.core.db import SessionLocal

    own_session = db_session is None
    db = SessionLocal() if own_session else db_session
    try:
        # Children before parents (FK-safe), single transaction, no
        # intermediate commit, no table drops.
        for model in (TEEAnalysis, Recommendation, SignalContribution, Anomaly, SensorReading, MaintenanceRecord, Asset):
            db.query(model).delete(synchronize_session=False)
        plan = build_plan()
        for chunk_start in range(0, len(plan["assets"]), 5000):
            db.bulk_insert_mappings(Asset, plan["assets"][chunk_start : chunk_start + 5000])
        for chunk_start in range(0, len(plan["readings"]), 5000):
            db.bulk_insert_mappings(SensorReading, plan["readings"][chunk_start : chunk_start + 5000])
        for chunk_start in range(0, len(plan["maintenance"]), 5000):
            db.bulk_insert_mappings(MaintenanceRecord, plan["maintenance"][chunk_start : chunk_start + 5000])
        db.commit()
        return len(plan["assets"]), len(plan["readings"]), len(plan["maintenance"])
    except Exception:
        db.rollback()
        raise
    finally:
        if own_session:
            db.close()


if __name__ == "__main__":
    n_a, n_r, n_m = reset_and_generate()
    print(f"assets={n_a} sensor_readings={n_r} maintenance_records={n_m}")
