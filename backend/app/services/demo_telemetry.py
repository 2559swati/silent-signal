"""Demo/simulated telemetry for map-registered assets (hackathon flow).

A registered public-infrastructure asset has coordinates but no sensor
rows, so the existing Phase 3-5 pipeline honestly reports missing evidence.
For demonstration WITHOUT physical sensors, this module writes clearly
separated SIMULATED readings that reuse the exact Phase 2 generator
physics (operating hours, setback dimming, baselines, bounds, deterministic
UUIDs) and then lets the caller run the EXISTING compute_all_* pipelines --
no second detection system, no formula changes.

Honesty rules enforced here and in the API response:
- Only assets with infra_source (map-registered) are eligible; seeded
  assets keep their frozen dataset (400 otherwise).
- Writes are deterministic per (asset, mode): same input, same rows.
  Re-enabling a mode first deletes that asset's prior simulated rows, so
  enabling is idempotent and never stacks readings.
- NOTHING here touches OSM metadata, and OSM metadata is never presented
  as telemetry. Every response carries simulated=true plus a warning.
- 'normal': baseline physics + noise (expected outcome: NORMAL/LOW).
- 'anomalous': hero-style gradual drift from day 9 (expected outcome:
  elevated fusion/risk through the existing thresholds).
"""

import os
import sys
import uuid
from datetime import timedelta

import numpy as np
from sqlalchemy.orm import Session

from app.models.assets import Asset
from app.models.sensor_readings import SensorReading

# Make `data.*` importable (repo root = three levels above this file's dir),
# same pattern as app/api/demo.py (backend/data/ may be an empty mount).
_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from data import config  # noqa: E402

SIMULATED_WARNING = (
    "Simulated telemetry - demonstration only. No physical sensor is "
    "installed or connected; these readings were generated deterministically "
    "for hackathon evaluation of the existing analysis pipeline."
)

MODES = ("normal", "anomalous")


def _rng_for(stable_key: str, mode: str):
    # Seeded by the STABLE external code (not the random row UUID) so the
    # same registered asset always yields the same demo rows across runs.
    seed = int(uuid.uuid5(uuid.NAMESPACE_URL, f"silent-signal:demo:{stable_key}:{mode}"))
    return np.random.default_rng(seed % (2**32))


def _reading_id(asset_id: str, mode: str, day: int, hour: int, sensor_type: str) -> str:
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"silent-signal:demo:{asset_id}:{mode}:{day}:{hour}:{sensor_type}",
        )
    )


def build_demo_readings(asset: Asset, mode: str) -> list[dict]:
    """Deterministic simulated rows for one asset (pure, no DB writes)."""
    if mode not in MODES:
        raise ValueError(f"unknown demo telemetry mode {mode!r}")
    rng = _rng_for(asset.external_code, mode)
    base_power = config.BASE_POWER_W + float(rng.normal(0, 2.5))
    base_bright = config.BASE_BRIGHTNESS_PCT + float(rng.normal(0, 1.5))
    rows: list[dict] = []
    for day in range(config.DATASET_DAYS):
        drift_days = max(0, day - config.DRIFT_START_DAY_INDEX)
        # Anomalous demo drift is 2x the hero rate: far enough past the
        # EMERGING/HIGH thresholds that run-to-run fleet-percentile shifts
        # cannot flip the verdict, still inside physical sensor bounds.
        p_drift = drift_days * config.POWER_DRIFT_W_PER_DAY * 2.0 if mode == "anomalous" else 0.0
        b_drift = drift_days * config.BRIGHTNESS_DRIFT_PP_PER_DAY * 2.0 if mode == "anomalous" else 0.0
        for hour in sorted(config.OPERATING_HOURS):
            ts = config.FIXED_START + timedelta(days=day, hours=hour)
            setback = hour in config.SETBACK_HOURS
            dim_p = -5.0 if setback else 0.0
            dim_b = -7.0 if setback else 0.0
            power = base_power + dim_p + float(rng.normal(0, 0.35)) + p_drift
            bright = base_bright + dim_b + float(rng.normal(0, 0.4)) + b_drift
            power = min(max(power, config.POWER_MIN_W), config.POWER_MAX_W)
            bright = min(max(bright, config.BRIGHTNESS_MIN_PCT), config.BRIGHTNESS_MAX_PCT)
            rows.append(
                {
                    "id": _reading_id(str(asset.id), mode, day, hour, config.SENSOR_POWER),
                    "asset_id": asset.id,
                    "recorded_at": ts,
                    "sensor_type": config.SENSOR_POWER,
                    "value": power,
                }
            )
            rows.append(
                {
                    "id": _reading_id(str(asset.id), mode, day, hour, config.SENSOR_BRIGHTNESS),
                    "asset_id": asset.id,
                    "recorded_at": ts,
                    "sensor_type": config.SENSOR_BRIGHTNESS,
                    "value": bright,
                }
            )
    return rows


def write_demo_readings(db: Session, asset: Asset, mode: str) -> int:
    """Replace this asset's simulated rows with a fresh deterministic set."""
    rows = build_demo_readings(asset, mode)
    db.query(SensorReading).filter(SensorReading.asset_id == asset.id).delete(
        synchronize_session=False
    )
    for chunk_start in range(0, len(rows), 5000):
        db.bulk_insert_mappings(SensorReading, rows[chunk_start : chunk_start + 5000])
    db.commit()
    return len(rows)
