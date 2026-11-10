# pyrefly: ignore [missing-import]
"""Demo-telemetry tests: simulated readings + existing pipeline, honestly labeled.

A map-registered asset progresses DISCOVERED -> REGISTERED ->
TELEMETRY NOT CONNECTED -> DEMO TELEMETRY ENABLED -> MONITORING ->
ANOMALY DETECTED -> RISK/ALERT/RECOMMENDATION using only the existing
Phase 2 physics and Phase 4-9 pipeline entry points. Seeded fleet (SL-1042)
must remain unaffected.
"""

import os
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from app.main import app as fastapi_app  # noqa: E402
from app.core.db import Base, get_db  # noqa: E402
import app.models  # noqa: E402,F401 - register models
from app.models.sensor_readings import SensorReading  # noqa: E402
from app.models.assets import Asset  # noqa: E402
from app.services.demo_telemetry import (  # noqa: E402
    SIMULATED_WARNING,
    build_demo_readings,
)

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


@pytest.fixture(scope="module")
def seeded_db():
    Base.metadata.create_all(bind=engine)
    resp = client.post("/api/demo/reset")
    assert resp.status_code == 200, resp.text
    db = TestingSessionLocal()
    yield db
    db.close()


def _register(db, osm_id):
    db.query(Asset).filter(Asset.infra_source == f"osm:{osm_id}").delete()
    db.commit()
    resp = client.post("/api/assets/register", json={
        "latitude": 21.19, "longitude": 81.35,
        "infra_type": "Street light", "infra_source": f"osm:{osm_id}",
    })
    assert resp.status_code == 201, resp.text
    return resp.json()["external_code"]


def test_registered_without_telemetry_is_not_connected(seeded_db):
    code = _register(seeded_db, "311")
    assert client.get(f"/api/assets/{code}/fusion").status_code == 404
    assert client.get(f"/api/assets/{code}/risk").status_code == 404


def test_demo_builder_is_deterministic(seeded_db):
    asset = seeded_db.query(Asset).filter(Asset.external_code == _register(seeded_db, "312")).one()
    first = build_demo_readings(asset, "normal")
    second = build_demo_readings(asset, "normal")
    assert [r["id"] for r in first] == [r["id"] for r in second]
    assert [r["value"] for r in first] == [r["value"] for r in second]
    assert len(first) == 30 * 12 * 2  # days x operating hours x sensors
    assert {r["sensor_type"] for r in first} == {"power_watts", "brightness_pct"}


def test_normal_demo_telemetry_monitors_low(seeded_db):
    code = _register(seeded_db, "313")
    resp = client.post(f"/api/assets/{code}/demo-telemetry", json={"mode": "normal"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["simulated"] is True
    assert body["readings_written"] == 720
    assert "demonstration only" in body["warning"]
    assert SIMULATED_WARNING in body["warning"]
    assert client.get(f"/api/assets/{code}/fusion").json()["status"] == "NORMAL"
    assert client.get(f"/api/assets/{code}/risk").json()["risk_level"] == "LOW"


def test_anomalous_demo_telemetry_detects(seeded_db):
    code = _register(seeded_db, "314")
    resp = client.post(f"/api/assets/{code}/demo-telemetry", json={"mode": "anomalous"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["simulated"] is True
    fusion = client.get(f"/api/assets/{code}/fusion").json()
    assert fusion["status"] in ("EMERGING", "CRITICAL")
    risk = client.get(f"/api/assets/{code}/risk").json()
    assert risk["risk_level"] in ("HIGH", "CRITICAL")
    alerts = client.get(f"/api/assets/{code}/alerts").json()
    assert "EMERGING_ANOMALY" in {a["alert_type"] for a in alerts["alerts"]}
    recs = client.get(f"/api/assets/{code}/recommendations").json()
    assert recs["priority"] in ("prioritize preventive inspection", "urgent preventive inspection")


def test_demo_telemetry_idempotent(seeded_db):
    code = _register(seeded_db, "315")
    client.post(f"/api/assets/{code}/demo-telemetry", json={"mode": "anomalous"})
    db = TestingSessionLocal()
    try:
        asset = db.query(Asset).filter(Asset.external_code == code).one()
        n1 = db.query(SensorReading).filter(SensorReading.asset_id == asset.id).count()
    finally:
        db.close()
    client.post(f"/api/assets/{code}/demo-telemetry", json={"mode": "anomalous"})
    db = TestingSessionLocal()
    try:
        asset = db.query(Asset).filter(Asset.external_code == code).one()
        n2 = db.query(SensorReading).filter(SensorReading.asset_id == asset.id).count()
    finally:
        db.close()
    assert n1 == n2 == 720


def test_seeded_assets_reject_demo_telemetry(seeded_db):
    resp = client.post("/api/assets/SL-1042/demo-telemetry", json={"mode": "normal"})
    assert resp.status_code == 400
    assert client.post("/api/assets/NOPE/demo-telemetry", json={"mode": "normal"}).status_code == 404
    code = _register(seeded_db, "316")
    bad = client.post(f"/api/assets/{code}/demo-telemetry", json={"mode": "weird"})
    assert bad.status_code == 422


def test_seeded_fleet_unaffected(seeded_db):
    db = TestingSessionLocal()
    try:
        sl = db.query(Asset).filter(Asset.external_code == "SL-1042").one()
        statuses = sorted({r.status for r in sl.fusion_results})
    finally:
        db.close()
    assert "EMERGING" in statuses  # hero timeline intact after demo runs
    fleet = client.get("/api/alerts").json()
    assert "SL-1042" in {a["asset_external_code"] for a in fleet["alerts"]}
