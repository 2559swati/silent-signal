# pyrefly: ignore [missing-import]
"""Phase 6 tests: risk -> explanation (deterministic rule-based layer).

Covers the 27 required Phase 6 areas. Never modifies Phase 1-5 logic;
existing test files are untouched. The full suite run additionally proves
all Phase 1-5 tests still pass.
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
from app.models.risk_results import RiskResult  # noqa: E402
from app.models.sensor_readings import SensorReading  # noqa: E402
from app.services import explain_engine as explain_mod  # noqa: E402
from app.services.explain_engine import (  # noqa: E402
    EXPLAIN_MODEL_VERSION,
    FACTOR_THRESHOLD,
    SEVERITY_THRESHOLDS,
    SIGNAL_ORDER,
    TEMPERATURE_PROXY_NOTE,
    build_explanation,
    build_summary,
    compute_all_explanations,
    persistence_reason,
    severity_for,
    signal_reason,
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


def _latest_explanation(db, asset_id):
    return (
        db.query(ExplanationResult)
        .filter(ExplanationResult.asset_id == asset_id)
        .order_by(ExplanationResult.day.desc())
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


# 1. explanation generation
def test_explanation_generation(seeded_db):
    assert seeded_db.query(func.count(ExplanationResult.id)).scalar() == 100 * 30
    sl = _sl1042_id(seeded_db)
    row = _latest_explanation(seeded_db, sl)
    assert row is not None
    assert row.risk_level == "CRITICAL"
    assert len(row.summary) > 0
    factors = json.loads(row.factors_json)
    assert len(factors) >= 2  # top signal + overall risk at minimum
    assert factors[-1]["signal"] == "risk"


# 2. deterministic output
def test_deterministic_output(seeded_db):
    ev = _full_evidence()
    first = build_explanation(ev)
    second = build_explanation(dict(ev))
    assert first == second
    assert json.dumps(first) == json.dumps(second)


# 3. score bounds
def test_score_bounds(seeded_db):
    bad = (
        seeded_db.query(ExplanationResult)
        .filter((ExplanationResult.risk_score < 0.0) | (ExplanationResult.risk_score > 1.0))
        .count()
    )
    assert bad == 0
    for r in seeded_db.query(ExplanationResult).limit(200).all():
        for f in json.loads(r.factors_json):
            assert 0.0 <= f["score"] <= 1.0, f


# 4. risk level handling
def test_risk_level_handling(seeded_db):
    for level in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
        assert seeded_db.query(ExplanationResult).filter(
            ExplanationResult.risk_level == level).count() > 0
    for r in seeded_db.query(ExplanationResult).limit(200).all():
        assert r.risk_level in ("LOW", "MEDIUM", "HIGH", "CRITICAL")
        factors = json.loads(r.factors_json)
        assert factors[-1]["severity"] == r.risk_level.lower()


# 5. power explanation
def test_power_explanation(seeded_db):
    assert "abnormal" in signal_reason("power", "high").lower()
    assert "no major power" in signal_reason("power", "low").lower()
    built = build_explanation(_full_evidence(power_score=0.95))
    power = next(f for f in built["factors"] if f["signal"] == "power")
    assert power["severity"] == "critical" and power["score"] == 0.95


# 6. brightness explanation
def test_brightness_explanation(seeded_db):
    assert "dim" in signal_reason("brightness", "high").lower()
    # Below-threshold non-top brightness earns no factor of its own.
    built = build_explanation(_full_evidence(brightness_score=0.1))
    assert "brightness" not in [f["signal"] for f in built["factors"]]
    low = build_explanation(_full_evidence(
        power_score=0.1, brightness_score=0.05, temperature_score=0.07,
        maintenance_score=0.0, neighbor_score=0.02,
        persistence_score=0.0, risk_score=0.05, risk_level="LOW"))
    assert low["factors"][0]["signal"] == "power"  # top contributor always present


# 7. temperature proxy explanation
def test_temperature_proxy_explanation(seeded_db):
    for sev in ("low", "medium", "high", "critical"):
        text = signal_reason("temperature", sev)
        assert "proxy" in text.lower(), sev
    assert "sensor" not in signal_reason("temperature", "high").lower().replace(
        "no physical temperature sensor exists", "")
    built = build_explanation(_full_evidence())
    temp = next(f for f in built["factors"] if f["signal"] == "temperature")
    assert "proxy" in temp["reason"].lower()
    assert "sensor detected" not in temp["reason"].lower()
    assert "physical temperature increased" not in temp["reason"].lower()


# 8. maintenance explanation
def test_maintenance_explanation(seeded_db):
    assert "maintenance" in signal_reason("maintenance", "high").lower()
    built = build_explanation(_full_evidence(maintenance_score=0.9))
    maint = next(f for f in built["factors"] if f["signal"] == "maintenance")
    assert maint["severity"] == "critical"


# 9. neighbor explanation
def test_neighbor_explanation(seeded_db):
    assert "correlat" in signal_reason("neighbor", "high").lower()
    built = build_explanation(_full_evidence(neighbor_score=0.55))
    neigh = next(f for f in built["factors"] if f["signal"] == "neighbor")
    assert neigh["severity"] == "high"


# 10. persistence explanation
def test_persistence_explanation(seeded_db):
    assert "8 consecutive" in persistence_reason(8)
    built = build_explanation(_full_evidence(persistence_score=1.0, streak_days=8))
    persist = next(f for f in built["factors"] if f["signal"] == "persistence")
    assert persist["severity"] == "critical"
    assert "8 consecutive" in persist["reason"]
    quiet = build_explanation(_full_evidence(persistence_score=0.0, streak_days=0))
    assert all(f["signal"] != "persistence" for f in quiet["factors"])


# 11. factor severity
def test_factor_severity(seeded_db):
    assert severity_for(0.0) == "low"
    assert severity_for(0.2999) == "low"
    assert severity_for(0.30) == "medium"
    assert severity_for(0.4999) == "medium"
    assert severity_for(0.50) == "high"
    assert severity_for(0.7499) == "high"
    assert severity_for(0.75) == "critical"
    assert severity_for(1.0) == "critical"
    # Severity cut points match the Phase 5 risk thresholds (no conflicts).
    assert SEVERITY_THRESHOLDS["MEDIUM"] == 0.30
    assert SEVERITY_THRESHOLDS["HIGH"] == 0.50
    assert SEVERITY_THRESHOLDS["CRITICAL"] == 0.75


# 12. factor ordering
def test_factor_ordering(seeded_db):
    built = build_explanation(_full_evidence())
    names = [f["signal"] for f in built["factors"]]
    assert names[-1] == "risk"
    assert "persistence" in names and names.index("persistence") == len(names) - 2
    signal_names = names[:-2]
    scores = [next(f["score"] for f in built["factors"] if f["signal"] == n)
              for n in signal_names]
    assert scores == sorted(scores, reverse=True)
    # Stored SL-1042 row obeys the same ordering.
    sl = _sl1042_id(seeded_db)
    factors = json.loads(_latest_explanation(seeded_db, sl).factors_json)
    names = [f["signal"] for f in factors]
    assert names[-1] == "risk"
    sig_scores = [f["score"] for f in factors if f["signal"] not in ("persistence", "risk")]
    assert sig_scores == sorted(sig_scores, reverse=True)


# 13. deterministic tie-breaking
def test_deterministic_tie_breaking(seeded_db):
    ev = _full_evidence(power_score=0.8, brightness_score=0.8, temperature_score=0.8,
                        maintenance_score=0.8, neighbor_score=0.8)
    names = [f["signal"] for f in build_explanation(ev)["factors"]]
    assert names[:5] == list(SIGNAL_ORDER) == ["power", "brightness", "temperature",
                                               "maintenance", "neighbor"]


# 14. summary generation
def test_summary_generation(seeded_db):
    assert "low infrastructure risk" in build_summary("LOW", 0.0).lower()
    assert "moderate infrastructure risk" in build_summary("MEDIUM", 0.0).lower()
    assert "elevated infrastructure risk" in build_summary("HIGH", 0.6).lower()
    assert "critical infrastructure risk" in build_summary("CRITICAL", 1.0).lower()
    assert "persisted" in build_summary("CRITICAL", 1.0).lower()
    assert "persisted" not in build_summary("CRITICAL", 0.0).lower()
    assert "persisted" not in build_summary("LOW", 0.0).lower()


# 15. SL-1042 generic behavior
def test_sl1042_generic_behavior(seeded_db):
    sl = _sl1042_id(seeded_db)
    row = _latest_explanation(seeded_db, sl)
    factors = json.loads(row.factors_json)
    evidence = json.loads(row.evidence_json)
    names = {f["signal"] for f in factors}
    assert {"power", "brightness", "temperature", "maintenance",
            "neighbor", "persistence", "risk"} <= names
    assert "SL-1042" not in row.summary
    assert all("SL-1042" not in f["reason"] for f in factors)
    assert evidence["temperature_proxy_note"] == TEMPERATURE_PROXY_NOTE
    assert abs(evidence["risk_score"] - 0.918320) < 1e-4
    assert evidence["risk_level"] == "CRITICAL"


# 16. no SL-1042 hardcoding
def test_no_hardcoded_sl1042(seeded_db):
    src = inspect.getsource(explain_mod)
    code_only = re.sub(r'"""[\s\S]*?"""', "", src)
    code_only = re.sub(r"'''[\s\S]*?'''", "", code_only)
    code_only = "\n".join(line.split("#")[0] for line in code_only.splitlines())
    assert "1042" not in code_only


# 17. database persistence
def test_database_persistence(seeded_db):
    from sqlalchemy import inspect as sa_inspect
    assert "explanation_results" in set(sa_inspect(engine).get_table_names())
    joined = (
        seeded_db.query(func.count(ExplanationResult.id))
        .join(Asset, Asset.id == ExplanationResult.asset_id)
        .scalar()
    )
    assert joined == 3000
    dupes = (
        seeded_db.query(ExplanationResult.asset_id, ExplanationResult.day, func.count("*"))
        .group_by(ExplanationResult.asset_id, ExplanationResult.day)
        .having(func.count("*") > 1)
        .count()
    )
    assert dupes == 0
    assert seeded_db.query(ExplanationResult).filter(
        ExplanationResult.model_version != EXPLAIN_MODEL_VERSION).count() == 0


# 18. duplicate prevention/idempotency
def test_idempotent_repeat(seeded_db):
    before = {
        (r.asset_id, r.day): (r.risk_score, r.risk_level, r.summary,
                              r.factors_json, r.evidence_json)
        for r in seeded_db.query(ExplanationResult).all()
    }
    db = TestingSessionLocal()
    try:
        result = compute_all_explanations(db)
    finally:
        db.close()
    assert result == {"assets": 100, "explanations": 3000}
    seeded_db.expire_all()
    assert seeded_db.query(func.count(ExplanationResult.id)).scalar() == 3000
    for r in seeded_db.query(ExplanationResult).all():
        assert (r.risk_score, r.risk_level, r.summary,
                r.factors_json, r.evidence_json) == before[(r.asset_id, r.day)]


# 19. API 200
def test_explanation_api(seeded_db):
    sl = _sl1042_id(seeded_db)
    for key in ("SL-1042", sl):
        resp = client.get(f"/api/assets/{key}/explanation")
        assert resp.status_code == 200, (key, resp.text)
        body = resp.json()
        assert body["asset_external_code"] == "SL-1042"
        assert body["model_version"] == EXPLAIN_MODEL_VERSION
        for field in ("asset_id", "day", "risk_score", "risk_level",
                      "summary", "factors", "evidence"):
            assert field in body, field
        row = _latest_explanation(seeded_db, sl)
        assert abs(body["risk_score"] - row.risk_score) < 1e-12
        assert body["summary"] == row.summary
        assert len(body["factors"]) == len(json.loads(row.factors_json))


# 20. API 404
def test_explanation_api_unknown_asset(seeded_db):
    assert client.get("/api/assets/DOES-NOT-EXIST/explanation").status_code == 404


# 21. malformed asset handling
def test_malformed_asset_handling(seeded_db):
    # Not an external code and not a UUID: must be 404, never 500.
    for bad in ("NOPE", "!!!", "123", "SL-"):
        resp = client.get(f"/api/assets/{bad}/explanation")
        assert resp.status_code == 404, bad
        assert client.get(f"/api/assets/{bad}/risk").status_code == 404, bad
        assert client.get(f"/api/assets/{bad}/fusion").status_code == 404, bad


# 22. model_version
def test_model_version(seeded_db):
    assert EXPLAIN_MODEL_VERSION == "explain_v1"
    assert "20" not in EXPLAIN_MODEL_VERSION  # no timestamps/dates
    assert seeded_db.query(ExplanationResult).filter(
        ExplanationResult.model_version != "explain_v1").count() == 0


# 23-27. regression: Phase 1/2/3/4/5 state intact after explanation runs
def test_phase1_regression(seeded_db):
    from sqlalchemy import inspect as sa_inspect
    tables = set(sa_inspect(engine).get_table_names())
    for t in ("assets", "sensor_readings", "maintenance_records", "anomalies",
              "signal_contributions", "recommendations", "tee_analysis",
              "fusion_results", "risk_results", "explanation_results"):
        assert t in tables, t
    resp = client.get("/api/assets?page=1&page_size=2")
    assert resp.status_code == 200 and resp.json()["total"] == 100


def test_phase2_regression(seeded_db):
    assert seeded_db.query(Asset).count() == 100
    assert seeded_db.query(SensorReading).count() == (
        100 * 30 * 12 * 2 + 360 + config.OTHER_COMPLAINT_COUNT
    )


def test_phase3_regression(seeded_db):
    import ml.anomaly as anom
    from ml.features import build_features
    feats = build_features(seeded_db)
    scores = anom._train_and_score(feats)
    code_of = {a.id: a.external_code for a in seeded_db.query(Asset).all()}
    sl_id = next(i for i, c in code_of.items() if c == "SL-1042")
    sl_score = float(scores.loc[scores["asset_id"] == sl_id, "score"].iloc[0])
    assert int((scores["score"] > sl_score).sum() + 1) == 1


def test_phase4_regression(seeded_db):
    assert seeded_db.query(func.count(FusionResult.id)).scalar() == 3000
    resp = client.get("/api/assets/SL-1042/fusion")
    assert resp.status_code == 200
    assert abs(resp.json()["fusion_score"] - 0.886207) < 1e-4


def test_phase5_regression(seeded_db):
    assert seeded_db.query(func.count(RiskResult.id)).scalar() == 3000
    resp = client.get("/api/assets/SL-1042/risk")
    assert resp.status_code == 200
    body = resp.json()
    assert abs(body["risk_score"] - 0.918320) < 1e-4
    assert body["risk_level"] == "CRITICAL"


def test_factor_threshold_centralized(seeded_db):
    assert FACTOR_THRESHOLD == 0.30
    # Below-threshold non-top signals earn no factor of their own.
    built = build_explanation(_full_evidence(
        power_score=0.9, brightness_score=0.1, temperature_score=0.1,
        maintenance_score=0.05, neighbor_score=0.02,
        persistence_score=0.0, streak_days=0,
        risk_score=0.4, risk_level="MEDIUM"))
    names = [f["signal"] for f in built["factors"]]
    assert names[0] == "power"
    assert "brightness" not in names and "persistence" not in names
    assert names[-1] == "risk"
