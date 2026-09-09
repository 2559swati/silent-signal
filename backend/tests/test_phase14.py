# pyrefly: ignore [missing-import]
"""Phase 14 tests: Blueprint Section 18 coverage (tests ONLY, no features).

Every case below exercises the REAL pipeline (HTTP -> route -> service ->
test DB -> response) or the REAL pure engines (no mocks, no duplicated
algorithms, no threshold changes). The module reseeds its own deterministic
dataset, so it is isolated from -- and order-independent of -- other modules.

Section 18 checklist:
  TC1 normal asset stays normal .................... test_normal_asset_* (API)
  TC2 single noisy reading never critical .......... test_single_noisy_* (engine)
  TC3 multiple weak signals increase fusion ........ test_weak_signals_* (engine)
  TC4 SL-1042 detected as emerging anomaly ......... test_sl1042_* (API + rows)
  TC5 risk prioritization .......................... test_risk_* (API)
  TC6 recommendations fire only when documented .... test_recommendations_* (API)
  TC7 complaint_received=false still detects ....... test_complaint_false_* (API+rows)
  TC8 DemoTEEProvider identifies as demo ........... test_demo_tee_* (API)
  TC9 invalid API requests ......................... test_invalid_* (API)
  Full pipeline end-to-end ......................... test_e2e_full_pipeline (API)

Honesty note on TC4: the frozen Phase 4/5 pipeline (thresholds + EMA +
two-day rule, all covered by Phase 4/5 tests) reports SL-1042's LATEST day
as CRITICAL (smoothed 0.823 >= 0.75 after 21 sustained drift days). The
"emerging anomaly" detection is verified precisely: seed status emerging,
an EMERGING day in the confirmed timeline, and a fired EMERGING_ANOMALY
alert. Thresholds were NOT touched to force a headline value.
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
from app.models.fusion_results import FusionResult  # noqa: E402
from app.models.sensor_readings import SensorReading  # noqa: E402
from app.services.fusion_engine import determine_status, fuse_signals  # noqa: E402
from data import config  # noqa: E402

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
def seeded_api():
    """Deterministic reseed for this module (isolation, no order dependence)."""
    Base.metadata.create_all(bind=engine)
    resp = client.post("/api/demo/reset")
    assert resp.status_code == 200, resp.text
    assert resp.json()["assets"] == config.NUM_ASSETS
    db = TestingSessionLocal()
    yield (client, db)
    db.close()


def _codes_by_seed_status(api, status):
    resp = api.get("/api/assets", params={"page": 1, "page_size": 100, "status": status})
    assert resp.status_code == 200, resp.text
    return [i["external_code"] for i in resp.json()["items"]]


# ---------------------------------------------------------------------------
# TC1 -- normal asset remains normal (API)
# ---------------------------------------------------------------------------

def test_normal_asset_no_critical(seeded_api):
    api, _db = seeded_api
    healthy = _codes_by_seed_status(api, "healthy")
    assert len(healthy) == 70
    code = healthy[0]
    fusion = api.get(f"/api/assets/{code}/fusion").json()
    assert fusion["status"] == "NORMAL", fusion
    risk = api.get(f"/api/assets/{code}/risk").json()
    assert risk["risk_level"] == "LOW", risk
    assert risk["risk_score"] < 0.30
    alerts = api.get(f"/api/assets/{code}/alerts").json()
    assert all(a["severity"] != "CRITICAL" for a in alerts["alerts"])


def test_normal_assets_have_no_critical_alerts(seeded_api):
    api, _db = seeded_api
    for code in _codes_by_seed_status(api, "healthy")[:10]:
        resp = api.get(f"/api/assets/{code}/alerts")
        if resp.status_code == 404:
            continue  # no alerts at all: vacuously no critical alert
        assert resp.status_code == 200, (code, resp.text)
        assert all(a["severity"] != "CRITICAL"
                   for a in resp.json()["alerts"]), code


# ---------------------------------------------------------------------------
# TC2 -- single noisy reading never becomes critical (real engine)
# ---------------------------------------------------------------------------

def test_single_noisy_signal_never_critical():
    """Even a fully-elevated single signal stays below CRITICAL (max 0.25)."""
    names = ("power", "brightness", "temperature", "maintenance", "neighbor")
    for i in range(5):
        scores = [0.0] * 5
        scores[i] = 1.0
        fused = fuse_signals(*scores)
        assert fused <= 0.25 + 1e-9, (names[i], fused)
        assert determine_status(fused) != "CRITICAL", names[i]


def test_single_noisy_below_emerging_threshold():
    fused = fuse_signals(1.0, 0.0, 0.0, 0.0, 0.0)
    assert fused == pytest.approx(0.25)
    # 0.25 < WATCH threshold 0.30: a lone spike is absorbed, not escalated.
    assert determine_status(fused) == "NORMAL"


# ---------------------------------------------------------------------------
# TC3 -- multiple weak signals increase fusion (real engine)
# ---------------------------------------------------------------------------

def test_weak_signals_combine_stronger():
    single = fuse_signals(0.5, 0.0, 0.0, 0.0, 0.0)
    combined = fuse_signals(0.5, 0.5, 0.5, 0.5, 0.5)
    assert combined == pytest.approx(0.5)
    assert combined > single
    assert determine_status(combined) == "EMERGING"
    assert determine_status(single) != "EMERGING"


def test_fusion_monotonic_in_each_signal():
    base = (0.2, 0.2, 0.2, 0.2, 0.2)
    for i in range(5):
        raised = list(base)
        raised[i] = 0.9
        assert fuse_signals(*raised) > fuse_signals(*base)


# ---------------------------------------------------------------------------
# TC4 -- SL-1042 detected as an emerging anomaly (API + pipeline rows)
# ---------------------------------------------------------------------------

def test_sl1042_seed_status_emerging(seeded_api):
    api, _db = seeded_api
    assert "SL-1042" in _codes_by_seed_status(api, "emerging")


def test_sl1042_timeline_passes_through_emerging(seeded_api):
    _api, db = seeded_api
    sl = db.query(Asset).filter(Asset.external_code == "SL-1042").one()
    statuses = [
        r.status for r in db.query(FusionResult)
        .filter(FusionResult.asset_id == sl.id).order_by(FusionResult.day).all()
    ]
    assert "EMERGING" in statuses, statuses
    # Sustained drift escalates afterwards -- documents the honest latest value.
    assert statuses[-1] == "CRITICAL"


def test_sl1042_emerging_anomaly_alert_fired(seeded_api):
    api, _db = seeded_api
    body = api.get("/api/assets/SL-1042/alerts").json()
    assert body["total_alerts"] >= 1
    assert "EMERGING_ANOMALY" in {a["alert_type"] for a in body["alerts"]}
    fleet = api.get("/api/alerts").json()
    assert "SL-1042" in {a["asset_external_code"] for a in fleet["alerts"]}


# ---------------------------------------------------------------------------
# TC5 -- risk prioritization (API, real risk engine)
# ---------------------------------------------------------------------------

def test_risk_prioritizes_sl1042_over_healthy(seeded_api):
    api, _db = seeded_api
    hero = api.get("/api/assets/SL-1042/risk").json()["risk_score"]
    for code in _codes_by_seed_status(api, "healthy"):
        other = api.get(f"/api/assets/{code}/risk").json()["risk_score"]
        assert hero > other, (code, hero, other)


def test_risk_levels_follow_documented_thresholds(seeded_api):
    api, _db = seeded_api
    assert api.get("/api/assets/SL-1042/risk").json()["risk_level"] == "CRITICAL"
    healthy = _codes_by_seed_status(api, "healthy")[0]
    assert api.get(f"/api/assets/{healthy}/risk").json()["risk_level"] == "LOW"


def test_risk_orders_by_evidence_not_criticality(seeded_api):
    """Documented honesty boundary: criticality/exposure are stored asset
    attributes (1-5, validated) but the frozen Phase 5 formula weights only
    anomaly + fusion + persistence evidence. A criticality-5 healthy asset
    must therefore still score far below the evidence-backed hero asset.
    Changing the formula would break Phase 5 tests first."""
    api, _db = seeded_api
    hero = api.get("/api/assets/SL-1042/risk").json()["risk_score"]
    body = api.get("/api/assets", params={"page": 1, "page_size": 100}).json()
    crit5_healthy = [i for i in body["items"]
                     if i["status"] == "healthy" and i["criticality"] == 5]
    assert len(crit5_healthy) >= 1
    for item in crit5_healthy:
        assert 1 <= item["criticality"] <= 5
        assert 1 <= item["public_exposure"] <= 5
        other = api.get(f"/api/assets/{item['external_code']}/risk").json()
        assert other["risk_level"] == "LOW", item
        assert hero > other["risk_score"], item


# ---------------------------------------------------------------------------
# TC6 -- recommendations fire only under documented conditions (API)
# ---------------------------------------------------------------------------

def test_sl1042_gets_urgent_inspection(seeded_api):
    api, _db = seeded_api
    body = api.get("/api/assets/SL-1042/recommendations").json()
    assert body["priority"] == "urgent preventive inspection"
    assert body["recommendations"][0]["action"] == (
        "Perform an urgent preventive inspection."
    )
    assert len(body["recommendations"]) > 1  # risk action + signal actions


def test_healthy_asset_only_routine_monitoring(seeded_api):
    api, _db = seeded_api
    # Find a healthy asset with no elevated signal (deterministic dataset:
    # at least one exists). Its documented output is the lone risk action.
    code = next(
        c for c in _codes_by_seed_status(api, "healthy")
        if len(api.get(f"/api/assets/{c}/recommendations").json()["recommendations"]) == 1
    )
    body = api.get(f"/api/assets/{code}/recommendations").json()
    assert body["priority"] == "routine monitoring"
    assert len(body["recommendations"]) == 1
    assert body["recommendations"][0]["action"] == "Continue routine monitoring."
    assert all("inspect" not in i["action"].lower() for i in body["recommendations"])


def test_signal_action_matches_elevated_evidence(seeded_api):
    """A documented signal action fires iff its signal evidence is elevated.

    (The first healthy asset has maintenance_score 0.33 >= 0.30, so the
    maintenance action is correctly present alongside routine monitoring.)
    """
    api, _db = seeded_api
    code = _codes_by_seed_status(api, "healthy")[0]
    body = api.get(f"/api/assets/{code}/recommendations").json()
    assert body["priority"] == "routine monitoring"
    assert body["recommendations"][0]["action"] == "Continue routine monitoring."
    evidence = body["evidence"]
    assert float(evidence["maintenance_score"]) >= 0.30
    assert any("maintenance" in i["action"].lower()
               for i in body["recommendations"][1:])


# ---------------------------------------------------------------------------
# TC7 -- complaint_received=false still detects (API + rows)
# ---------------------------------------------------------------------------

def test_complaint_false_still_detects(seeded_api):
    api, db = seeded_api
    sl = db.query(Asset).filter(Asset.external_code == "SL-1042").one()
    complaints = db.query(SensorReading).filter(
        SensorReading.asset_id == sl.id,
        SensorReading.sensor_type == config.SENSOR_COMPLAINT,
    ).all()
    assert len(complaints) == 30 * len(config.OPERATING_HOURS)
    assert all(c.value == 0.0 for c in complaints)  # complaint_received=false
    # ... yet the pipeline still flags the anomaly:
    statuses = [
        r.status for r in db.query(FusionResult)
        .filter(FusionResult.asset_id == sl.id).order_by(FusionResult.day).all()
    ]
    assert "EMERGING" in statuses
    alerts = api.get("/api/assets/SL-1042/alerts").json()
    assert alerts["total_alerts"] >= 1


# ---------------------------------------------------------------------------
# TC8 -- DemoTEEProvider identifies as demo (API)
# ---------------------------------------------------------------------------

def test_demo_tee_identifies_as_simulation(seeded_api, monkeypatch):
    api, _db = seeded_api
    monkeypatch.setenv("TEE_MODE", "demo")
    status = api.get("/api/security/tee-status").json()
    assert status["mode"] == "demo"
    assert "demo" in status["description"].lower()
    assert "nitro" not in status["description"].lower()
    att = api.get("/api/security/attestation").json()
    assert att["attested"] is False
    assert att["pcr0"] is None


# ---------------------------------------------------------------------------
# TC9 -- invalid API requests (API: status codes, safety, no leakage)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", [
    "/api/assets/NOPE-SUCH-ASSET/fusion",
    "/api/assets/NOPE-SUCH-ASSET/risk",
    "/api/assets/NOPE-SUCH-ASSET/explanation",
    "/api/assets/NOPE-SUCH-ASSET/recommendations",
    "/api/assets/NOPE-SUCH-ASSET/alerts",
])
def test_unknown_asset_404(seeded_api, path):
    api, _db = seeded_api
    resp = api.get(path)
    assert resp.status_code == 404, (path, resp.text)
    assert resp.json()["detail"] == "Asset not found"


@pytest.mark.parametrize("path,params", [
    ("/api/assets", {"page": 0}),
    ("/api/assets", {"page_size": 101}),
    ("/api/assets", {"status": "bogus"}),
    ("/api/assets/NOT-A-UUID/anomaly", {}),
])
def test_validation_422(seeded_api, path, params):
    api, _db = seeded_api
    resp = api.get(path, params=params)
    assert resp.status_code == 422, (path, params, resp.text)


def test_demo_reset_wrong_method_405(seeded_api):
    api, _db = seeded_api
    assert api.get("/api/demo/reset").status_code == 405


def test_unknown_route_404(seeded_api):
    api, _db = seeded_api
    assert api.get("/api/no-such-endpoint").status_code == 404


def test_error_responses_leak_nothing(seeded_api):
    api, _db = seeded_api
    bodies = [
        api.get("/api/assets/NOPE-SUCH-ASSET/fusion").text,
        api.get("/api/assets", params={"page": 0}).text,
        api.get("/api/assets/NOT-A-UUID/anomaly").text,
        api.get("/api/no-such-endpoint").text,
    ]
    for text in bodies:
        lowered = text.lower()
        assert "traceback" not in lowered, text
        assert "password" not in lowered, text
        assert "secret" not in lowered, text
        assert "nitro_data_key" not in lowered, text
    # Server still healthy afterwards (no crash).
    assert api.get("/api/health").json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# Dashboard summary (read-only roll-up used by the Phase 15 smoke test)
# ---------------------------------------------------------------------------

def test_dashboard_summary_non_empty(seeded_api):
    api, _db = seeded_api
    body = api.get("/api/dashboard/summary").json()
    assert body["total_assets"] == config.NUM_ASSETS
    assert body["assets_by_status"] == {
        "healthy": 70, "watch": 15, "emerging": 10, "critical": 5}
    assert body["latest_day"] is not None
    assert body["total_alerts"] >= 1
    assert sum(body["alerts_by_severity"].values()) == body["total_alerts"]
    assert sum(body["risk_by_level"].values()) == config.NUM_ASSETS
    assert sum(body["fusion_by_status"].values()) == config.NUM_ASSETS


def test_dashboard_summary_empty_db():
    from app.models.alert_results import AlertResult
    from app.models.explanation_results import ExplanationResult
    from app.models.fusion_results import FusionResult
    from app.models.recommendation_results import RecommendationResult
    from app.models.risk_results import RiskResult
    db = TestingSessionLocal()
    try:
        for model in (AlertResult, ExplanationResult, RecommendationResult,
                      RiskResult, FusionResult, SensorReading, Asset):
            db.query(model).delete()
        db.commit()
        body = client.get("/api/dashboard/summary").json()
        assert body["total_assets"] == 0
        assert body["total_alerts"] == 0
        assert body["latest_day"] is None
    finally:
        db.close()
        # Restore the deterministic dataset for order-independence.
        assert client.post("/api/demo/reset").status_code == 200


# ---------------------------------------------------------------------------
# Full end-to-end pipeline (API: reset -> ... -> recommend -> alerts)
# ---------------------------------------------------------------------------

def test_e2e_full_pipeline(seeded_api):
    api, db = seeded_api
    # 1. Dataset generation (deterministic reseed through the real endpoint).
    reset = api.post("/api/demo/reset")
    assert reset.status_code == 200, reset.text
    assert reset.json() == {
        "status": "ok", "assets": 100,
        "sensor_readings": 72366, "maintenance_records": 59,
    }
    # 2-3. ML/anomaly + fusion: SL-1042 emerges (see TC4 honesty note).
    # The asset record itself keeps its seeded EMERGING classification
    # (no pipeline stage rewrites Asset.status -- only FusionResult rows).
    emerging = api.get("/api/assets", params={"status": "emerging", "page_size": 100}).json()
    assert "SL-1042" in {i["external_code"] for i in emerging["items"]}
    fusion = api.get("/api/assets/SL-1042/fusion").json()
    assert fusion["asset_external_code"] == "SL-1042"
    sl = db.query(Asset).filter(Asset.external_code == "SL-1042").one()
    timeline = [
        r.status for r in db.query(FusionResult)
        .filter(FusionResult.asset_id == sl.id).order_by(FusionResult.day).all()
    ]
    assert "EMERGING" in timeline
    # 4. Risk.
    risk = api.get("/api/assets/SL-1042/risk").json()
    assert risk["risk_level"] in ("HIGH", "CRITICAL")
    assert risk["risk_score"] >= 0.50
    # 5. Explain.
    expl = api.get("/api/assets/SL-1042/explanation").json()
    assert expl["summary"] and expl["factors"]
    assert "SL-1042" not in expl["summary"]  # no hardcoded hero text
    # 6. Recommend.
    rec = api.get("/api/assets/SL-1042/recommendations").json()
    assert rec["priority"] in (
        "prioritize preventive inspection", "urgent preventive inspection")
    # 7. Alerts (incl. fleet projection).
    alerts = api.get("/api/assets/SL-1042/alerts").json()
    assert "EMERGING_ANOMALY" in {a["alert_type"] for a in alerts["alerts"]}
    fleet = api.get("/api/alerts").json()
    assert fleet["total_alerts"] >= 1
    # 8. complaint_received=false throughout, detection unaffected.
    complaints = db.query(SensorReading).filter(
        SensorReading.asset_id == sl.id,
        SensorReading.sensor_type == config.SENSOR_COMPLAINT,
    ).all()
    assert complaints and all(c.value == 0.0 for c in complaints)
