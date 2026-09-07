# pyrefly: ignore [missing-import]
"""Phase 7 tests: explanation -> preventive recommendations.

Covers the 16 required Phase 7 areas. Never modifies Phase 0-6 logic;
existing test files are untouched. The full suite run additionally proves
all Phase 0-6 tests still pass.
"""

import inspect
import json
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
from app.models.assets import Asset  # noqa: E402
from app.models.explanation_results import ExplanationResult  # noqa: E402
from app.models.fusion_results import FusionResult  # noqa: E402
from app.models.recommendation_results import RecommendationResult  # noqa: E402
from app.models.risk_results import RiskResult  # noqa: E402
from app.models.sensor_readings import SensorReading  # noqa: E402
from app.services import recommend_engine as recommend_mod  # noqa: E402
from app.services.recommend_engine import (  # noqa: E402
    RECOMMEND_MODEL_VERSION,
    RECOMMEND_THRESHOLD,
    URGENCY_THRESHOLD,
    build_recommendations,
    compute_all_recommendations,
    priority_for,
    urgency_for,
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


def _latest(db, asset_id):
    return (
        db.query(RecommendationResult)
        .filter(RecommendationResult.asset_id == asset_id)
        .order_by(RecommendationResult.day.desc())
        .first()
    )


def _full_evidence(**over):
    base = {
        "anomaly_score": 0.9,
        "power_score": 0.9,
        "brightness_score": 0.8,
        "temperature_score": 0.85,
        "maintenance_score": 0.7,
        "neighbor_score": 0.6,
        "raw_fusion_score": 0.8,
        "smoothed_fusion_score": 0.78,
        "fusion_status": "CRITICAL",
        "persistence_score": 1.0,
        "streak_days": 8,
        "risk_score": 0.85,
        "risk_level": "CRITICAL",
    }
    base.update(over)
    return base


# Priority rules: LOW/MEDIUM/HIGH/CRITICAL risk mapping.
def test_priority_mapping(seeded_db):
    assert priority_for("LOW") == "routine monitoring"
    assert priority_for("MEDIUM") == "planned inspection"
    assert priority_for("HIGH") == "prioritize preventive inspection"
    assert priority_for("CRITICAL") == "urgent preventive inspection"


# LOW risk -> routine monitoring, single action when nothing is elevated.
def test_low_risk(seeded_db):
    built = build_recommendations(_full_evidence(
        power_score=0.05, brightness_score=0.02, temperature_score=0.03,
        maintenance_score=0.0, neighbor_score=0.02, persistence_score=0.0,
        streak_days=0, risk_score=0.08, risk_level="LOW"))
    assert built["priority"] == "routine monitoring"
    assert built["urgency"] == "normal"
    assert [r["action"] for r in built["recommendations"]] == ["Continue routine monitoring."]
    assert seeded_db.query(RecommendationResult).filter(
        RecommendationResult.risk_level == "LOW").count() > 0


# MEDIUM risk -> planned inspection.
def test_medium_risk(seeded_db):
    built = build_recommendations(_full_evidence(risk_score=0.4, risk_level="MEDIUM"))
    assert built["priority"] == "planned inspection"
    assert built["recommendations"][0]["action"] == "Schedule a planned inspection."
    assert seeded_db.query(RecommendationResult).filter(
        RecommendationResult.risk_level == "MEDIUM").count() > 0


# HIGH risk -> prioritize preventive inspection.
def test_high_risk(seeded_db):
    built = build_recommendations(_full_evidence(risk_score=0.6, risk_level="HIGH"))
    assert built["priority"] == "prioritize preventive inspection"
    assert built["recommendations"][0]["action"] == "Prioritize a preventive inspection."
    assert seeded_db.query(RecommendationResult).filter(
        RecommendationResult.risk_level == "HIGH").count() > 0


# CRITICAL risk -> urgent preventive inspection.
def test_critical_risk(seeded_db):
    sl = _sl1042_id(seeded_db)
    row = _latest(seeded_db, sl)
    assert row.risk_level == "CRITICAL"
    assert row.priority == "urgent preventive inspection"
    recs = json.loads(row.recommendations_json)
    assert recs[0]["action"] == "Perform an urgent preventive inspection."
    assert seeded_db.query(RecommendationResult).filter(
        RecommendationResult.risk_level == "CRITICAL").count() > 0


# Power recommendation.
def test_power_recommendation(seeded_db):
    built = build_recommendations(_full_evidence(power_score=0.9))
    power = next(r for r in built["recommendations"] if r["evidence"]["signal"] == "power")
    assert "power subsystem" in power["action"].lower()
    assert "wiring" in power["action"].lower()
    quiet = build_recommendations(_full_evidence(
        power_score=0.05, brightness_score=0.02, temperature_score=0.03,
        maintenance_score=0.0, neighbor_score=0.01, persistence_score=0.0,
        streak_days=0, risk_score=0.05, risk_level="LOW"))
    assert all(r["evidence"]["signal"] != "power" for r in quiet["recommendations"])


# Brightness recommendation.
def test_brightness_recommendation(seeded_db):
    built = build_recommendations(_full_evidence(brightness_score=0.85))
    bright = next(r for r in built["recommendations"] if r["evidence"]["signal"] == "brightness")
    assert "lamp" in bright["action"].lower() or "led" in bright["action"].lower()


# Temperature proxy wording (never a sensor claim).
def test_temperature_proxy_wording(seeded_db):
    built = build_recommendations(_full_evidence(temperature_score=0.85))
    temp = next(r for r in built["recommendations"] if r["evidence"]["signal"] == "temperature")
    assert "proxy" in temp["action"].lower()
    assert "no physical temperature sensor exists" in temp["action"].lower()
    assert "sensor detected" not in temp["action"].lower()
    assert "physical temperature increased" not in temp["action"].lower()


# Maintenance recommendation.
def test_maintenance_recommendation(seeded_db):
    built = build_recommendations(_full_evidence(maintenance_score=0.8))
    maint = next(r for r in built["recommendations"] if r["evidence"]["signal"] == "maintenance")
    assert "preventive maintenance" in maint["action"].lower()


# Neighbor recommendation.
def test_neighbor_recommendation(seeded_db):
    built = build_recommendations(_full_evidence(neighbor_score=0.55))
    neigh = next(r for r in built["recommendations"] if r["evidence"]["signal"] == "neighbor")
    assert "nearby" in neigh["action"].lower() or "adjacent" in neigh["action"].lower()


# Persistence/urgency: escalated only on sustained evidence with real streak.
def test_persistence_urgency(seeded_db):
    assert URGENCY_THRESHOLD == 0.50
    assert urgency_for(0.0) == "normal"
    assert urgency_for(0.49) == "normal"
    assert urgency_for(0.50) == "escalated"
    assert urgency_for(1.0) == "escalated"
    built = build_recommendations(_full_evidence(persistence_score=1.0, streak_days=8))
    assert built["urgency"] == "escalated"
    persist = next(r for r in built["recommendations"] if r["evidence"]["signal"] == "persistence")
    assert "8 consecutive" in persist["reason"]
    assert persist["evidence"]["streak_days"] == 8
    calm = build_recommendations(_full_evidence(persistence_score=0.1, streak_days=0))
    assert calm["urgency"] == "normal"
    assert all(r["evidence"]["signal"] != "persistence" for r in calm["recommendations"])
    sl = _sl1042_id(seeded_db)
    assert _latest(seeded_db, sl).urgency == "escalated"


# Recommendation ordering: risk first, signals by score desc + tie-break, persistence last.
def test_recommendation_ordering(seeded_db):
    ev = _full_evidence(power_score=0.8, brightness_score=0.8, temperature_score=0.8,
                        maintenance_score=0.8, neighbor_score=0.8)
    sigs = [r["evidence"]["signal"] for r in build_recommendations(ev)["recommendations"]]
    assert sigs[0] == "risk"
    assert sigs[1:6] == ["power", "brightness", "temperature", "maintenance", "neighbor"]
    assert sigs[-1] == "persistence"
    sl = _sl1042_id(seeded_db)
    recs = json.loads(_latest(seeded_db, sl).recommendations_json)
    sigs = [r["evidence"]["signal"] for r in recs]
    assert sigs[0] == "risk" and sigs[-1] == "persistence"
    scores = [r["evidence"]["score"] for r in recs[1:-1]]
    assert scores == sorted(scores, reverse=True)


# Duplicate prevention: at most one action per signal.
def test_duplicate_prevention(seeded_db):
    for r in seeded_db.query(RecommendationResult).limit(500).all():
        recs = json.loads(r.recommendations_json)
        sigs = [i["evidence"]["signal"] for i in recs]
        assert len(sigs) == len(set(sigs)), (r.asset_id, r.day)
        actions = [i["action"] for i in recs]
        assert len(actions) == len(set(actions))
    assert seeded_db.query(func.count(RecommendationResult.id)).scalar() == 100 * 30


# Unknown asset -> 404; malformed key -> 404 (never 500).
def test_unknown_and_malformed_asset(seeded_db):
    assert client.get("/api/assets/DOES-NOT-EXIST/recommendations").status_code == 404
    for bad in ("NOPE", "!!!", "123"):
        assert client.get(f"/api/assets/{bad}/recommendations").status_code == 404, bad


# Deterministic repeated execution + database uniqueness.
def test_deterministic_idempotent(seeded_db):
    ev = _full_evidence()
    assert build_recommendations(ev) == build_recommendations(dict(ev))
    before = {
        (r.asset_id, r.day): (r.risk_score, r.risk_level, r.priority, r.urgency,
                              r.recommendations_json, r.evidence_json)
        for r in seeded_db.query(RecommendationResult).all()
    }
    db = TestingSessionLocal()
    try:
        result = compute_all_recommendations(db)
    finally:
        db.close()
    assert result == {"assets": 100, "recommendations": 3000}
    seeded_db.expire_all()
    assert seeded_db.query(func.count(RecommendationResult.id)).scalar() == 3000
    dupes = (
        seeded_db.query(RecommendationResult.asset_id, RecommendationResult.day, func.count("*"))
        .group_by(RecommendationResult.asset_id, RecommendationResult.day)
        .having(func.count("*") > 1)
        .count()
    )
    assert dupes == 0
    for r in seeded_db.query(RecommendationResult).all():
        assert (r.risk_score, r.risk_level, r.priority, r.urgency,
                r.recommendations_json, r.evidence_json) == before[(r.asset_id, r.day)]


# API response schema.
def test_api_response_schema(seeded_db):
    sl = _sl1042_id(seeded_db)
    for key in ("SL-1042", sl):
        resp = client.get(f"/api/assets/{key}/recommendations")
        assert resp.status_code == 200, (key, resp.text)
        body = resp.json()
        for field in ("asset_id", "asset_external_code", "day", "risk_score",
                      "risk_level", "priority", "urgency", "recommendations",
                      "evidence", "model_version"):
            assert field in body, field
        assert body["asset_external_code"] == "SL-1042"
        assert body["model_version"] == RECOMMEND_MODEL_VERSION
        row = _latest(seeded_db, sl)
        assert abs(body["risk_score"] - row.risk_score) < 1e-12
        assert body["priority"] == row.priority
        assert len(body["recommendations"]) == len(json.loads(row.recommendations_json))
        for item in body["recommendations"]:
            assert {"action", "reason", "evidence"} <= set(item)
            assert {"signal", "score", "severity"} <= set(item["evidence"])


# Model version + no SL-1042 hardcoding.
def test_version_and_no_hardcoding(seeded_db):
    assert RECOMMEND_MODEL_VERSION == "recommendation_v1"
    assert seeded_db.query(RecommendationResult).filter(
        RecommendationResult.model_version != "recommendation_v1").count() == 0
    src = inspect.getsource(recommend_mod)
    code_only = re.sub(r'"""[\s\S]*?"""', "", src)
    code_only = re.sub(r"'''[\s\S]*?'''", "", code_only)
    code_only = "\n".join(line.split("#")[0] for line in code_only.splitlines())
    assert "1042" not in code_only
    sl = _sl1042_id(seeded_db)
    row = _latest(seeded_db, sl)
    recs = json.loads(row.recommendations_json)
    assert all("SL-1042" not in i["action"] and "SL-1042" not in i["reason"] for i in recs)


# SL-1042 live-evidence check: actual elevated contributors drive its actions.
def test_sl1042_evidence_driven(seeded_db):
    sl = _sl1042_id(seeded_db)
    row = _latest(seeded_db, sl)
    assert abs(row.risk_score - 0.918320) < 1e-4
    recs = json.loads(row.recommendations_json)
    by_signal = {i["evidence"]["signal"]: i for i in recs}
    assert {"risk", "power", "brightness", "temperature",
            "maintenance", "neighbor", "persistence"} <= set(by_signal)
    ev = json.loads(row.evidence_json)
    assert ev["temperature_proxy_note"].startswith("Temperature-related behavior proxy")
    assert ev["elevated_streak_days"] >= 7


# Regression: Phases 0-6 state intact after recommendation runs.
def test_prior_phase_state_unchanged(seeded_db):
    assert seeded_db.query(Asset).count() == 100
    assert seeded_db.query(SensorReading).count() == (
        100 * 30 * 12 * 2 + 360 + config.OTHER_COMPLAINT_COUNT
    )
    assert seeded_db.query(func.count(FusionResult.id)).scalar() == 3000
    assert seeded_db.query(func.count(RiskResult.id)).scalar() == 3000
    assert seeded_db.query(func.count(ExplanationResult.id)).scalar() == 3000
    assert client.get("/api/assets/SL-1042/explanation").status_code == 200
