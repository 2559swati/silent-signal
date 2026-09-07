# pyrefly: ignore [missing-import]
import os
# pyrefly: ignore [missing-import]
from fastapi.testclient import TestClient
# pyrefly: ignore [missing-import]
from sqlalchemy import create_engine, inspect
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import sessionmaker

from app.main import app as fastapi_app
from app.core.db import Base, get_db
import app.models  # noqa: F401 - register models
from app.models.assets import Asset

# Phase 1 uses PostgreSQL UUID PKs, so tests run against Postgres
# (Docker: silent-signal-postgres-1), not SQLite.
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://postgres:password@postgres:5432/silentsignal_test",
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

EXPECTED_TABLES = {
    "assets",
    "sensor_readings",
    "maintenance_records",
    "anomalies",
    "signal_contributions",
    "recommendations",
    "tee_analysis",
}


def setup_function(_):
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_db_connection():
    with engine.connect() as conn:
        assert conn is not None


def test_tables_exist():
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert EXPECTED_TABLES.issubset(tables), f"missing: {EXPECTED_TABLES - tables}"


def test_fk_constraints():
    inspector = inspect(engine)
    sr_fks = inspector.get_foreign_keys("sensor_readings")
    assert any(fk["referred_table"] == "assets" for fk in sr_fks)
    mr_fks = inspector.get_foreign_keys("maintenance_records")
    assert any(fk["referred_table"] == "assets" for fk in mr_fks)
    an_fks = inspector.get_foreign_keys("anomalies")
    assert any(fk["referred_table"] == "assets" for fk in an_fks)
    sc_fks = inspector.get_foreign_keys("signal_contributions")
    assert any(fk["referred_table"] == "anomalies" for fk in sc_fks)
    rec_fks = inspector.get_foreign_keys("recommendations")
    assert any(fk["referred_table"] == "anomalies" for fk in rec_fks)
    tee_fks = inspector.get_foreign_keys("tee_analysis")
    assert any(fk["referred_table"] == "anomalies" for fk in tee_fks)


def test_unique_check_index_constraints():
    inspector = inspect(engine)
    # UNIQUE on assets.external_code
    uniques = inspector.get_unique_constraints("assets")
    assert any("external_code" in u["column_names"] for u in uniques)
    # CHECK constraints are in table DDL / metadata
    asset_table = Base.metadata.tables["assets"]
    check_names = {c.name for c in asset_table.constraints if c.__class__.__name__ == "CheckConstraint"}
    assert "check_criticality_1_to_5" in check_names
    assert "check_public_exposure_1_to_5" in check_names
    assert "check_status" in check_names
    anomaly_table = Base.metadata.tables["anomalies"]
    anomaly_checks = {c.name for c in anomaly_table.constraints if c.__class__.__name__ == "CheckConstraint"}
    assert "check_anomaly_score_0_to_1" in anomaly_checks
    # Composite index on sensor_readings(asset_id, recorded_at)
    indexes = inspector.get_indexes("sensor_readings")
    assert any(
        idx["column_names"] == ["asset_id", "recorded_at"]
        for idx in indexes
    ), f"indexes: {indexes}"


def _seed_assets(n=3, status="healthy"):
    db = TestingSessionLocal()
    for i in range(n):
        db.add(Asset(external_code=f"EXT-{i:03d}", criticality=3, public_exposure=2, status=status))
    db.commit()
    db.close()


def test_assets_endpoint_pagination():
    _seed_assets(n=5)
    resp = client.get("/api/assets?page=1&page_size=2")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 5
    assert body["page"] == 1
    assert body["page_size"] == 2
    assert len(body["items"]) == 2


def test_assets_endpoint_status_filter():
    _seed_assets(n=2, status="healthy")
    db = TestingSessionLocal()
    db.add(Asset(external_code="EXT-CRIT", criticality=5, public_exposure=5, status="critical"))
    db.commit()
    db.close()
    resp = client.get("/api/assets?status=critical")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["status"] == "critical"
