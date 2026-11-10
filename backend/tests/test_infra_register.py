# pyrefly: ignore [missing-import]
"""Map-registration tests: POST /api/assets/register + stored map coordinates.

Additive feature only: every test below either exercises the new endpoint
or proves seeded/demo behavior (SL-1042, grid derivation, missing-evidence
404s) is unchanged.
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
from app.models.assets import Asset  # noqa: E402

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


def _payload(osm_id="101", lat=21.1938, lon=81.3501, kind="Street light"):
    return {
        "latitude": lat,
        "longitude": lon,
        "infra_type": kind,
        "infra_source": f"osm:{osm_id}",
    }


def test_register_returns_201_with_identity(seeded_db):
    resp = client.post("/api/assets/register", json=_payload("201"))
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["external_code"] == "SL-EXT-OSM-201"
    assert body["latitude"] == 21.1938
    assert body["longitude"] == 81.3501
    assert body["infra_type"] == "Street light"
    assert body["infra_source"] == "osm:201"
    assert body["status"] == "watch"


def test_register_duplicate_source_409(seeded_db):
    first = client.post("/api/assets/register", json=_payload("202"))
    assert first.status_code == 201, first.text
    dup = client.post("/api/assets/register", json=_payload("202"))
    assert dup.status_code == 409
    assert "already registered" in dup.json()["detail"]


def test_register_invalid_coords_422(seeded_db):
    bad_lat = dict(_payload("203"), latitude=200.0)
    assert client.post("/api/assets/register", json=bad_lat).status_code == 422
    missing = {"latitude": 21.0, "longitude": 81.0}
    assert client.post("/api/assets/register", json=missing).status_code == 422


def test_map_prefers_stored_coords_and_keeps_grid(seeded_db):
    created = client.post("/api/assets/register", json=_payload("204", 21.25, 81.45)).json()
    body = client.get("/api/map").json()
    by_code = {a["external_code"]: a for a in body["assets"]}
    mine = by_code[created["external_code"]]
    assert mine["latitude"] == 21.25
    assert mine["longitude"] == 81.45
    assert mine["infra_source"] == "osm:204"
    assert mine["risk_level"] is None  # no telemetry: honestly unscored
    # Seeded hero keeps grid-derived schematic coordinates.
    hero = by_code["SL-1042"]
    assert hero["infra_source"] is None
    assert hero["latitude"] is not None and hero["longitude"] is not None


def test_registered_asset_reports_missing_evidence(seeded_db):
    created = client.post("/api/assets/register", json=_payload("205")).json()
    code = created["external_code"]
    assert client.get(f"/api/assets/{code}/fusion").status_code == 404
    assert client.get(f"/api/assets/{code}/risk").status_code == 404
    assert client.get(f"/api/assets/{code}/recommendations").status_code == 404


def test_existing_assets_unaffected(seeded_db):
    db = TestingSessionLocal()
    try:
        total = db.query(Asset).count()
        assert total >= 100  # seeded fleet intact
        sl = db.query(Asset).filter(Asset.external_code == "SL-1042").one()
        assert sl.latitude is None and sl.infra_source is None
    finally:
        db.close()
    assert client.get("/api/assets/SL-1042/fusion").status_code == 200
