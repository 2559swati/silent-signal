import os
import sys
import random
import uuid
from datetime import datetime, timedelta
# pyrefly: ignore [missing-import]
import numpy as np

# Ensure the project root is in the path to import backend modules
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend'))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

# pyrefly: ignore [missing-import]
from app.core.db import SessionLocal, Base, engine
# pyrefly: ignore [missing-import]
from app.models.assets import Asset
# pyrefly: ignore [missing-import]
from app.models.sensor_readings import SensorReading
# pyrefly: ignore [missing-import]
from app.models.maintenance_records import MaintenanceRecord

# Import configuration constants
from data import config

# Deterministic seed for reproducibility
random.seed(config.SEED)
np.random.seed(config.SEED)

def deterministic_uuid(code: str) -> str:
    """Deterministic UUID based on external code"""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, code))

def generate_asset_codes() -> list[str]:
    """Generate list of external codes, reserving the demo asset"""
    codes = []
    i = config.FIRST_CODE
    while len(codes) < config.NUM_ASSETS - 1:
        code = f"SL-{i}"
        if code == config.SL_1042_CODE:
            i += 1
            continue
        codes.append(code)
        i += 1
    return codes

def geo_for_index(idx: int):
    """Deterministic grid placement (not persisted)"""
    row = idx // config.GRID_COLS
    col = idx % config.GRID_COLS
    lat = config.BASE_LAT + row * config.GRID_STEP_LAT
    lon = config.BASE_LON + col * config.GRID_STEP_LON
    return round(lat, 6), round(lon, 6)

def create_assets(session) -> int:
    existing = {a.external_code for a in session.query(Asset.external_code).all()}
    codes = generate_asset_codes()
    assets = []
    # Status list according to CATEGORY_MIX
    status_plan = []
    for status, count in config.CATEGORY_MIX.items():
        status_plan.extend([status] * count)
    assert len(status_plan) == config.NUM_ASSETS
    status_iter = iter(status_plan)
    # Demo asset
    if config.SL_1042_CODE not in existing:
        assets.append(
            Asset(
                id=deterministic_uuid(config.SL_1042_CODE),
                external_code=config.SL_1042_CODE,
                criticality=random.randint(1, 5),
                public_exposure=random.randint(1, 5),
                status=next(status_iter),
            )
        )
    for idx, code in enumerate(codes):
        if code in existing:
            continue
        _ = geo_for_index(idx)
        assets.append(
            Asset(
                id=deterministic_uuid(code),
                external_code=code,
                criticality=random.randint(1, 5),
                public_exposure=random.randint(1, 5),
                status=next(status_iter),
            )
        )
    session.bulk_save_objects(assets)
    session.commit()
    return len(assets)

def generate_sensor_series(base, drift_per_step, noise_sd, steps):
    """Linear drift plus Gaussian noise"""
    return base + drift_per_step * np.arange(steps) + np.random.normal(0, noise_sd, steps)

def create_sensor_readings(session) -> int:
    # Build timestamps for each operating hour over the fixed period
    timestamps = []
    for day_offset in range(config.DATASET_DAYS):
        day_start = config.FIXED_START + timedelta(days=day_offset)
        for hour in sorted(config.OPERATING_HOURS):
            ts = day_start.replace(hour=hour, minute=0, second=0, microsecond=0)
            timestamps.append(ts)
    assets = session.query(Asset).all()
    total_inserted = 0
    for asset in assets:
        is_special = asset.external_code == config.SL_1042_CODE
        is_neighbor = asset.external_code in config.NEIGHBORS
        # Base realistic values within bounds
        power_base = random.uniform(config.POWER_MIN_W + 5, config.POWER_MAX_W - 5)
        brightness_base = random.uniform(config.BRIGHTNESS_MIN_PCT + 5, config.BRIGHTNESS_MAX_PCT - 5)
        # Determine drift per hour
        if is_special:
            power_drift = config.POWER_DRIFT_W_PER_DAY / len(config.OPERATING_HOURS)
            brightness_drift = config.BRIGHTNESS_DRIFT_PP_PER_DAY / len(config.OPERATING_HOURS)
        elif is_neighbor:
            factor = config.NEIGHBOR_DRIFT_FRACTION
            power_drift = (config.POWER_DRIFT_W_PER_DAY * factor) / len(config.OPERATING_HOURS)
            brightness_drift = (config.BRIGHTNESS_DRIFT_PP_PER_DAY * factor) / len(config.OPERATING_HOURS)
        else:
            power_drift = brightness_drift = 0.0
        power_series = generate_sensor_series(power_base, power_drift, 0.3, len(timestamps))
        brightness_series = generate_sensor_series(brightness_base, brightness_drift, 5.0, len(timestamps))
        batch = []
        for ts, p, b in zip(timestamps, power_series, brightness_series):
            batch.append(SensorReading(asset_id=asset.id, recorded_at=ts, sensor_type=config.SENSOR_POWER, value=round(p, 3)))
            batch.append(SensorReading(asset_id=asset.id, recorded_at=ts, sensor_type=config.SENSOR_BRIGHTNESS, value=round(b, 3)))
            if is_special:
                batch.append(SensorReading(asset_id=asset.id, recorded_at=ts, sensor_type=config.SENSOR_COMPLAINT, value=0.0))
        session.bulk_save_objects(batch)
        session.commit()
        total_inserted += len(batch)
    # Sparse complaints for non‑hero assets
    if config.OTHER_COMPLAINT_COUNT > 0:
        non_demo = [a for a in assets if a.external_code != config.SL_1042_CODE]
        remaining = config.OTHER_COMPLAINT_COUNT
        idx = 0
        while remaining > 0 and idx < len(non_demo):
            asset = non_demo[idx]
            session.add(SensorReading(asset_id=asset.id, recorded_at=config.FIXED_START, sensor_type=config.SENSOR_COMPLAINT, value=1.0))
            remaining -= 1
            idx += 1
        session.commit()
        total_inserted += config.OTHER_COMPLAINT_COUNT
    return total_inserted

def create_maintenance_records(session) -> int:
    assets = session.query(Asset).all()
    records = []
    for asset in assets:
        is_special = asset.external_code == config.SL_1042_CODE
        if is_special:
            recent_ts = config.FIXED_START + timedelta(days=config.DATASET_DAYS - 3)
            older_ts = config.FIXED_START + timedelta(days=5)
            records.append(MaintenanceRecord(asset_id=asset.id, performed_at=recent_ts, description="Routine inspection"))
            records.append(MaintenanceRecord(asset_id=asset.id, performed_at=older_ts, description="Component replacement"))
        else:
            num_events = random.randint(0, 2)
            for _ in range(num_events):
                days_ago = random.randint(1, config.DATASET_DAYS - 8)
                performed_at = config.FIXED_START + timedelta(days=days_ago)
                desc = "Routine inspection" if random.random() < 0.7 else "Component replacement"
                records.append(MaintenanceRecord(asset_id=asset.id, performed_at=performed_at, description=desc))
    session.bulk_save_objects(records)
    session.commit()
    return len(records)

def validate(session) -> bool:
    asset_cnt = session.query(Asset).count()
    special = session.query(Asset).filter(Asset.external_code == config.SL_1042_CODE).first() is not None
    reading_cnt = session.query(SensorReading).count()
    maint_cnt = session.query(MaintenanceRecord).count()
    print(f"Validation: assets={asset_cnt} special={special} readings={reading_cnt} maint={maint_cnt}")
    return asset_cnt == config.NUM_ASSETS and special and reading_cnt > 0

def main():
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        print("Creating assets …")
        create_assets(session)
        print("Creating sensor readings …")
        create_sensor_readings(session)
        print("Creating maintenance records …")
        create_maintenance_records(session)
        validate(session)
    finally:
        session.close()

if __name__ == "__main__":
    main()
