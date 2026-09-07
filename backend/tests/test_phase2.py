# pyrefly: ignore [missing-import]
"""Phase 2 tests: deterministic synthetic dataset (Blueprint Section 5).

Covers reproducibility checksum, SL-1042 drift, SL-1042 complaints,
dataset validation, and the POST /api/demo/reset contract.
"""

import hashlib
import os
import sys
from collections import Counter
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker

# Repo root for `data.*` imports.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from data import config  # noqa: E402

from app.main import app as fastapi_app  # noqa: E402
from app.core.db import Base, get_db  # noqa: E402
import app.models  # noqa: E402,F401 - register models
from app.models.assets import Asset  # noqa: E402
from app.models.maintenance_records import MaintenanceRecord  # noqa: E402
from app.models.sensor_readings import SensorReading  # noqa: E402

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://postgres:password@localhost:5432/silentsignal_test",
)
engine = create_engine(TEST_DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


fastapi_app.dependency_overrides[get_db] = override_get_db
client = TestClient(fastapi_app)

EXPECTED_READINGS = 100 * 30 * 12 * 2 + 360 + config.OTHER_COMPLAINT_COUNT  # 72366


@pytest.fixture(scope="module")
def seeded_db():
    Base.metadata.create_all(bind=engine)
    resp = client.post("/api/demo/reset")
    assert resp.status_code == 200, resp.text
    db = TestingSessionLocal()
    yield db
    db.close()


def _checksum(db):
    h = hashlib.sha256()
    for a in db.query(Asset).order_by(Asset.external_code).all():
        h.update(f"A|{a.external_code}|{a.criticality}|{a.public_exposure}|{a.status}".encode())
    rows = (
        db.query(SensorReading, Asset.external_code)
        .join(Asset, SensorReading.asset_id == Asset.id)
        .order_by(Asset.external_code, SensorReading.recorded_at, SensorReading.sensor_type)
        .all()
    )
    for r, code in rows:
        h.update(
            f"R|{code}|{r.recorded_at.isoformat()}|{r.sensor_type}|{r.value:.4f}".encode()
        )
    mrows = (
        db.query(MaintenanceRecord, Asset.external_code)
        .join(Asset, MaintenanceRecord.asset_id == Asset.id)
        .order_by(Asset.external_code, MaintenanceRecord.performed_at)
        .all()
    )
    for m, code in mrows:
        h.update(f"M|{code}|{m.performed_at.isoformat()}|{m.description}".encode())
    return h.hexdigest()


def _sl1042_id(db):
    asset = db.query(Asset).filter(Asset.external_code == config.SL_1042_CODE).first()
    assert asset is not None, "SL-1042 missing"
    return asset.id


def _series(db, asset_id, sensor_type):
    return [
        r.value
        for r in db.query(SensorReading)
        .filter(
            SensorReading.asset_id == asset_id,
            SensorReading.sensor_type == sensor_type,
        )
        .order_by(SensorReading.recorded_at)
        .all()
    ]


def test_demo_reset_contract(seeded_db):
    resp = client.post("/api/demo/reset")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["assets"] == 100
    assert body["sensor_readings"] == EXPECTED_READINGS
    assert body["maintenance_records"] == seeded_db.query(MaintenanceRecord).count()


def test_reproducibility_checksum(seeded_db):
    resp1 = client.post("/api/demo/reset")
    assert resp1.status_code == 200
    sum1 = _checksum(seeded_db)
    resp2 = client.post("/api/demo/reset")
    assert resp2.status_code == 200
    sum2 = _checksum(seeded_db)
    assert sum1 == sum2


def test_asset_counts_and_mix(seeded_db):
    assert seeded_db.query(Asset).count() == 100
    assert seeded_db.query(Asset).filter(Asset.external_code == config.SL_1042_CODE).count() == 1
    mix = Counter(s for (s,) in seeded_db.query(Asset.status).all())
    assert mix["healthy"] == 70
    assert mix["watch"] == 15
    assert mix["emerging"] == 10
    assert mix["critical"] == 5
    codes = sorted(c for (c,) in seeded_db.query(Asset.external_code).all())
    assert codes[0] == "SL-1001" and codes[-1] == "SL-1100"


def test_reading_count_and_coverage(seeded_db):
    assert seeded_db.query(SensorReading).count() == EXPECTED_READINGS
    # Every asset: 360 distinct operating-hour timestamps, power+brightness each.
    assets = seeded_db.query(Asset).all()
    assert len(assets) == 100
    for a in assets:
        ts = [
            r.recorded_at
            for r in seeded_db.query(SensorReading.recorded_at)
            .filter(
                SensorReading.asset_id == a.id,
                SensorReading.sensor_type.in_([config.SENSOR_POWER, config.SENSOR_BRIGHTNESS]),
            )
            .distinct()
            .all()
        ]
        assert len(ts) == 30 * len(config.OPERATING_HOURS), a.external_code
        assert all(t.hour in config.OPERATING_HOURS for t in ts)


def test_sl1042_drift(seeded_db):
    sl = _sl1042_id(seeded_db)
    power = _series(seeded_db, sl, config.SENSOR_POWER)
    bright = _series(seeded_db, sl, config.SENSOR_BRIGHTNESS)
    assert len(power) == 360 and len(bright) == 360
    first_p = sum(power[:60]) / 60
    last_p = sum(power[-60:]) / 60
    first_b = sum(bright[:60]) / 60
    last_b = sum(bright[-60:]) / 60
    assert last_p > first_p + 5.0, (first_p, last_p)
    assert last_b < first_b - 5.0, (first_b, last_b)
    # Gradual: still operational, no catastrophic values.
    assert max(power) < 90.0
    assert min(bright) > 50.0


def test_sl1042_no_complaints(seeded_db):
    sl = _sl1042_id(seeded_db)
    complaints = (
        seeded_db.query(SensorReading)
        .filter(
            SensorReading.asset_id == sl,
            SensorReading.sensor_type == config.SENSOR_COMPLAINT,
        )
        .all()
    )
    assert len(complaints) == 30 * len(config.OPERATING_HOURS)
    assert all(c.value == 0.0 for c in complaints)


def test_correlated_neighbors(seeded_db):
    for code in config.NEIGHBORS:
        assert seeded_db.query(Asset).filter(Asset.external_code == code).count() == 1
    sl = _sl1042_id(seeded_db)
    sl_power = _series(seeded_db, sl, config.SENSOR_POWER)
    sl_delta = sum(sl_power[-60:]) / 60 - sum(sl_power[:60]) / 60
    for code in config.NEIGHBORS:
        n_id = seeded_db.query(Asset).filter(Asset.external_code == code).first().id
        n_power = _series(seeded_db, n_id, config.SENSOR_POWER)
        assert len(n_power) == 360
        n_delta = sum(n_power[-60:]) / 60 - sum(n_power[:60]) / 60
        assert 0 < n_delta < sl_delta, (code, n_delta, sl_delta)


def test_maintenance_last_week(seeded_db):
    sl = _sl1042_id(seeded_db)
    window_start = config.FIXED_START + timedelta(days=config.DATASET_DAYS - 7)
    late = (
        seeded_db.query(MaintenanceRecord)
        .filter(
            MaintenanceRecord.asset_id == sl,
            MaintenanceRecord.performed_at >= window_start,
        )
        .all()
    )
    assert len(late) == 1
    assert "fail" not in late[0].description.lower()
    # Realistic history exists beyond the hero asset.
    assert seeded_db.query(MaintenanceRecord).count() > 10


def test_value_bounds(seeded_db):
    bad_power = (
        seeded_db.query(SensorReading)
        .filter(
            SensorReading.sensor_type == config.SENSOR_POWER,
            (SensorReading.value < config.POWER_MIN_W)
            | (SensorReading.value > config.POWER_MAX_W),
        )
        .count()
    )
    bad_bright = (
        seeded_db.query(SensorReading)
        .filter(
            SensorReading.sensor_type == config.SENSOR_BRIGHTNESS,
            (SensorReading.value < config.BRIGHTNESS_MIN_PCT)
            | (SensorReading.value > config.BRIGHTNESS_MAX_PCT),
        )
        .count()
    )
    assert bad_power == 0
    assert bad_bright == 0
    complaints_total = (
        seeded_db.query(func.count(SensorReading.id))
        .filter(
            SensorReading.sensor_type == config.SENSOR_COMPLAINT,
            SensorReading.value == 1.0,
        )
        .scalar()
    )
    assert complaints_total == config.OTHER_COMPLAINT_COUNT
