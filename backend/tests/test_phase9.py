# pyrefly: ignore [missing-import]
"""Phase 9 tests: evidence -> actionable alerts (deterministic rule layer).

Covers the 13 required Phase 9 areas. Never modifies Phase 0-8 logic;
existing test files are untouched. The full suite run additionally proves
all Phase 0-8 tests still pass. UI V1 is frozen: no frontend changes here.
"""

import inspect
import os
import re
import sys

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
from app.models.alert_results import AlertResult  # noqa: E402
from app.models.assets import Asset  # noqa: E402
from app.models.explanation_results import ExplanationResult  # noqa: E402
from app.models.fusion_results import FusionResult  # noqa: E402
from app.models.recommendation_results import RecommendationResult  # noqa: E402
from app.models.risk_results import RiskResult  # noqa: E402
from app.models.sensor_readings import SensorReading  # noqa: E402
from app.services import alert_engine as alert_mod  # noqa: E402
from app.services.alert_engine import (  # noqa: E402
    ALERT_MODEL_VERSION,
    ALERT_TYPES,
    CONVERGENCE_COUNT,
    CRITICAL_RISK,
    EMERGING_ANOMALY,
    RISK_ESCALATION,
    SIGNAL_CONVERGENCE,
    SUSTAINED_RISK,
    build_alert,
    compute_all_alerts,
    determine_alert_types,
    determine_priority,
    determine_severity,
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


def _sl1042_id(db):
    asset = db.query(Asset).filter(Asset.external_code == "SL-1042").first()
    assert asset is not None, "SL-1042 missing"
    return asset.id


def _item(**over):
    base = {
        "asset_id": "aid", "day": "2024-01-30",
        "anomaly_score": 0.9,
        "power_score": 0.9, "brightness_score": 0.8, "temperature_score": 0.85,
        "maintenance_score": 0.7, "neighbor_score": 0.6,
        "raw_fusion": 0.8, "smoothed_fusion": 0.78, "fusion_status": "CRITICAL",
        "persistence_score": 1.0, "streak_days": 8,
        "risk_score": 0.85, "risk_level": "CRITICAL",
    }
    base.update(over)
    return base


# 1. Critical risk produces CRITICAL_RISK alert.
def test_critical_risk_alert(seeded_db):
    assert CRITICAL_RISK in determine_alert_types(_item(), "HIGH")
    assert CRITICAL_RISK not in determine_alert_types(_item(risk_level="HIGH", risk_score=0.6), "MEDIUM")
    sl = _sl1042_id(seeded_db)
    latest = (
        seeded_db.query(AlertResult)
        .filter(AlertResult.asset_id == sl)
        .order_by(AlertResult.day.desc())
        .first()
    )
    types = {
        r.alert_type for r in seeded_db.query(AlertResult)
        .filter(AlertResult.asset_id == sl, AlertResult.day == latest.day).all()
    }
    assert CRITICAL_RISK in types


# 2. Sustained elevated behavior produces SUSTAINED_RISK alert.
def test_sustained_risk_alert(seeded_db):
    assert SUSTAINED_RISK in determine_alert_types(_item(persistence_score=1.0), None)
    assert SUSTAINED_RISK not in determine_alert_types(_item(persistence_score=0.1), None)
    built = build_alert(SUSTAINED_RISK, _item(persistence_score=1.0, streak_days=8), None)
    assert "8 consecutive" in built["message"]
    sl = _sl1042_id(seeded_db)
    assert seeded_db.query(AlertResult).filter(
        AlertResult.asset_id == sl, AlertResult.alert_type == SUSTAINED_RISK).count() > 0


# 3. Emerging fusion produces EMERGING_ANOMALY alert.
def test_emerging_anomaly_alert(seeded_db):
    assert EMERGING_ANOMALY in determine_alert_types(
        _item(fusion_status="EMERGING", smoothed_fusion=0.6), "MEDIUM")
    assert EMERGING_ANOMALY not in determine_alert_types(
        _item(fusion_status="NORMAL", smoothed_fusion=0.1), None)
    # Status alone is not enough: corroborating smoothed evidence required.
    assert EMERGING_ANOMALY not in determine_alert_types(
        _item(fusion_status="EMERGING", smoothed_fusion=0.1), None)


# 4. Multiple meaningful factors can produce SIGNAL_CONVERGENCE.
def test_signal_convergence(seeded_db):
    assert CONVERGENCE_COUNT == 3
    assert SIGNAL_CONVERGENCE in determine_alert_types(_item(), None)
    assert SIGNAL_CONVERGENCE not in determine_alert_types(_item(
        power_score=0.9, brightness_score=0.1, temperature_score=0.1,
        maintenance_score=0.0, neighbor_score=0.0), None)
    built = build_alert(SIGNAL_CONVERGENCE, _item(), None)
    assert "5" in built["message"] and "power" in built["message"]


# Escalation fires only on a persisted ordinal increase (never day 0).
def test_risk_escalation_rule(seeded_db):
    assert RISK_ESCALATION in determine_alert_types(
        _item(risk_level="HIGH", risk_score=0.6), "MEDIUM")
    assert RISK_ESCALATION not in determine_alert_types(
        _item(risk_level="HIGH", risk_score=0.6), "HIGH")
    assert RISK_ESCALATION not in determine_alert_types(
        _item(risk_level="MEDIUM", risk_score=0.4), "HIGH")
    assert RISK_ESCALATION not in determine_alert_types(
        _item(risk_level="CRITICAL", risk_score=0.9), None)
    assert seeded_db.query(AlertResult).filter(
        AlertResult.alert_type == RISK_ESCALATION).count() > 0


# 5. Alert severity follows Phase 5 thresholds.
def test_severity_follows_phase5(seeded_db):
    assert determine_severity(0.0) == "LOW"
    assert determine_severity(0.2999) == "LOW"
    assert determine_severity(0.30) == "MEDIUM"
    assert determine_severity(0.4999) == "MEDIUM"
    assert determine_severity(0.50) == "HIGH"
    assert determine_severity(0.7499) == "HIGH"
    assert determine_severity(0.75) == "CRITICAL"
    for r in seeded_db.query(AlertResult).limit(500).all():
        assert r.severity == determine_severity(r.risk_score)


# 6. Alert priority follows severity.
def test_priority_follows_severity(seeded_db):
    assert determine_priority("CRITICAL") == "URGENT"
    assert determine_priority("HIGH") == "HIGH"
    assert determine_priority("MEDIUM") == "MEDIUM"
    assert determine_priority("LOW") == "LOW"
    for r in seeded_db.query(AlertResult).limit(500).all():
        assert r.priority == determine_priority(r.severity)


# 7. Duplicate alerts are prevented (+ uniqueness at the grain).
def test_no_duplicate_alerts(seeded_db):
    dupes = (
        seeded_db.query(AlertResult.asset_id, AlertResult.day, AlertResult.alert_type, func.count("*"))
        .group_by(AlertResult.asset_id, AlertResult.day, AlertResult.alert_type)
        .having(func.count("*") > 1)
        .count()
    )
    assert dupes == 0
    assert set(ALERT_TYPES) == {
        CRITICAL_RISK, SUSTAINED_RISK, RISK_ESCALATION, EMERGING_ANOMALY, SIGNAL_CONVERGENCE,
    }


# 8. Running computation twice produces identical results.
def test_deterministic_idempotent(seeded_db):
    assert build_alert(CRITICAL_RISK, _item(), "HIGH") == build_alert(CRITICAL_RISK, _item(), "HIGH")
    assert determine_alert_types(_item(), "HIGH") == determine_alert_types(_item(), "HIGH")
    before = {
        (r.asset_id, str(r.day), r.alert_type): (
            r.severity, r.priority, r.title, r.message, r.risk_score,
            r.fusion_score, r.anomaly_score, r.persistence_score, r.persistence_streak,
        )
        for r in seeded_db.query(AlertResult).all()
    }
    before_count = len(before)
    assert before_count > 0
    db = TestingSessionLocal()
    try:
        result = compute_all_alerts(db)
    finally:
        db.close()
    assert result["assets"] == 100
    seeded_db.expire_all()
    after = {
        (r.asset_id, str(r.day), r.alert_type): (
            r.severity, r.priority, r.title, r.message, r.risk_score,
            r.fusion_score, r.anomaly_score, r.persistence_score, r.persistence_streak,
        )
        for r in seeded_db.query(AlertResult).all()
    }
    assert len(after) == before_count and after == before


# 9/10. Unknown + malformed asset identifiers behave consistently (404).
def test_unknown_and_malformed_assets(seeded_db):
    assert client.get("/api/assets/DOES-NOT-EXIST/alerts").status_code == 404
    for bad in ("NOPE", "!!!", "123"):
        assert client.get(f"/api/assets/{bad}/alerts").status_code == 404, bad


# Asset + fleet alert APIs.
def test_alert_apis(seeded_db):
    sl = _sl1042_id(seeded_db)
    for key in ("SL-1042", sl):
        resp = client.get(f"/api/assets/{key}/alerts")
        assert resp.status_code == 200, (key, resp.text)
        body = resp.json()
        assert body["asset_external_code"] == "SL-1042"
        assert body["total_alerts"] == len(body["alerts"]) > 0
        assert body["model_version"] == "alert_v1"
        types = {a["alert_type"] for a in body["alerts"]}
        assert CRITICAL_RISK in types
        for a in body["alerts"]:
            assert {"alert_type", "severity", "priority", "title", "message",
                    "risk_score", "persistence_streak", "acknowledged", "model_version"} <= set(a)
    fleet = client.get("/api/alerts")
    assert fleet.status_code == 200, fleet.text
    fbody = fleet.json()
    assert fbody["total_alerts"] == len(fbody["alerts"]) > 0
    assert fbody["model_version"] == "alert_v1"
    sevs = [a["severity"] for a in fbody["alerts"]]
    assert sevs[0] == "CRITICAL"
    assert {a["asset_external_code"] for a in fbody["alerts"]} >= {"SL-1042"}


# 11. SL-1042 must NOT be hardcoded.
def test_no_hardcoded_sl1042(seeded_db):
    src = inspect.getsource(alert_mod)
    code_only = re.sub(r'"""[\s\S]*?"""', "", src)
    code_only = re.sub(r"'''[\s\S]*?'''", "", code_only)
    code_only = "\n".join(line.split("#")[0] for line in code_only.splitlines())
    assert "1042" not in code_only
    sl = _sl1042_id(seeded_db)
    rows = seeded_db.query(AlertResult).filter(AlertResult.asset_id == sl).all()
    assert len(rows) > 0
    assert all(r.model_version == "alert_v1" for r in rows)


# 12. No alert from invented/dummy evidence (rules need real thresholds).
def test_no_alerts_from_quiet_evidence(seeded_db):
    quiet = _item(
        anomaly_score=0.05, power_score=0.05, brightness_score=0.02,
        temperature_score=0.03, maintenance_score=0.0, neighbor_score=0.01,
        raw_fusion=0.05, smoothed_fusion=0.05, fusion_status="NORMAL",
        persistence_score=0.0, streak_days=0, risk_score=0.05, risk_level="LOW",
    )
    assert determine_alert_types(quiet, "LOW") == []
    assert determine_alert_types(quiet, None) == []
    # Persistence alone never invents a critical alert on quiet evidence.
    assert CRITICAL_RISK not in determine_alert_types(quiet, "LOW")


# Severity is derived from risk, never copied from fusion status.
def test_severity_not_status_mapping(seeded_db):
    assert determine_severity(0.2) == "LOW"
    assert build_alert(SIGNAL_CONVERGENCE, _item(
        risk_score=0.2, risk_level="LOW", fusion_status="NORMAL",
        power_score=0.4, brightness_score=0.35, temperature_score=0.37,
        maintenance_score=0.0, neighbor_score=0.0,
        persistence_score=0.0, streak_days=0), "LOW")["severity"] == "LOW"


# 13. Existing Phase 0-8 state unchanged + prior APIs compatible.
def test_prior_phases_intact(seeded_db):
    assert seeded_db.query(Asset).count() == 100
    assert seeded_db.query(SensorReading).count() == (
        100 * 30 * 12 * 2 + 360 + config.OTHER_COMPLAINT_COUNT
    )
    assert seeded_db.query(func.count(FusionResult.id)).scalar() == 3000
    assert seeded_db.query(func.count(RiskResult.id)).scalar() == 3000
    assert seeded_db.query(func.count(ExplanationResult.id)).scalar() == 3000
    assert seeded_db.query(func.count(RecommendationResult.id)).scalar() == 3000
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/assets/SL-1042/fusion").status_code == 200
    assert client.get("/api/assets/SL-1042/risk").status_code == 200
    assert client.get("/api/assets/SL-1042/explanation").status_code == 200
    assert client.get("/api/assets/SL-1042/recommendations").status_code == 200
