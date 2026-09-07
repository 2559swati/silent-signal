# pyrefly: ignore [missing-import]
"""Phase 5 tests: emerging anomaly -> risk.

Covers the 20 required Phase 5 areas. Never modifies Phase 1-4 logic;
existing test files are untouched. The full suite run additionally proves
all Phase 1-4 tests still pass.
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
from app.models.assets import Asset  # noqa: E402
from app.models.fusion_results import FusionResult  # noqa: E402
from app.models.risk_results import RiskResult  # noqa: E402
from app.models.sensor_readings import SensorReading  # noqa: E402
from app.services import risk_engine as risk_mod  # noqa: E402
from app.services.risk_engine import (  # noqa: E402
    ELEVATED_STATUSES,
    PERSISTENCE_SATURATION_DAYS,
    RISK_MODEL_VERSION,
    RISK_WEIGHTS,
    calculate_risk,
    compute_all_risks,
    determine_risk_level,
    load_anomaly_scores,
    persistence_score,
    persistence_update,
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

COMPONENT_COLS = [
    "anomaly_score",
    "fusion_score",
    "smoothed_fusion_score",
    "persistence_score",
]


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


def _streaks_from_timeline(db):
    """Independent streak recomputation from Phase 4 confirmed statuses."""
    streaks = {}
    aids = [a.id for a in db.query(Asset).all()]
    for aid in aids:
        rows = (
            db.query(FusionResult)
            .filter(FusionResult.asset_id == aid)
            .order_by(FusionResult.day)
            .all()
        )
        run = []
        streak = 0
        for r in rows:
            streak = streak + 1 if r.status in ELEVATED_STATUSES else 0
            run.append((r.day, streak))
        streaks[aid] = run
    return streaks


# 1. Risk score is in [0, 1]
def test_risk_score_in_range(seeded_db):
    bad = (
        seeded_db.query(RiskResult)
        .filter((RiskResult.risk_score < 0.0) | (RiskResult.risk_score > 1.0))
        .count()
    )
    assert bad == 0
    assert seeded_db.query(func.count(RiskResult.id)).scalar() == 100 * 30


# 2. Risk components are in [0, 1]
def test_risk_components_in_range(seeded_db):
    for col in COMPONENT_COLS:
        bad = (
            seeded_db.query(RiskResult)
            .filter((getattr(RiskResult, col) < 0.0) | (getattr(RiskResult, col) > 1.0))
            .count()
        )
        assert bad == 0, col


# 3. Risk weights sum to exactly 1.0
def test_risk_weights_sum_to_one(seeded_db):
    assert RISK_WEIGHTS == {
        "anomaly": 0.30,
        "raw_fusion": 0.25,
        "smoothed_fusion": 0.30,
        "persistence": 0.15,
    }
    assert abs(sum(RISK_WEIGHTS.values()) - 1.0) < 1e-12


# 4. Risk formula is correct
def test_risk_formula(seeded_db):
    assert abs(calculate_risk(1.0, 0.8862, 0.8226, 1.0)
               - (0.30 * 1.0 + 0.25 * 0.8862 + 0.30 * 0.8226 + 0.15 * 1.0)) < 1e-12
    rows = seeded_db.query(RiskResult).limit(300).all()
    assert len(rows) > 0
    for r in rows:
        expected = (
            0.30 * r.anomaly_score
            + 0.25 * r.fusion_score
            + 0.30 * r.smoothed_fusion_score
            + 0.15 * r.persistence_score
        )
        assert abs(r.risk_score - expected) < 1e-9


# 5. Risk thresholds are correct
def test_risk_thresholds(seeded_db):
    assert determine_risk_level(0.0) == "LOW"
    assert determine_risk_level(0.2999) == "LOW"
    assert determine_risk_level(0.30) == "MEDIUM"
    assert determine_risk_level(0.4999) == "MEDIUM"
    assert determine_risk_level(0.50) == "HIGH"
    assert determine_risk_level(0.7499) == "HIGH"
    assert determine_risk_level(0.75) == "CRITICAL"
    assert determine_risk_level(1.0) == "CRITICAL"


# 6. LOW classification
def test_low_classification(seeded_db):
    assert determine_risk_level(calculate_risk(0.0, 0.0, 0.0, 0.0)) == "LOW"
    assert seeded_db.query(RiskResult).filter(RiskResult.risk_level == "LOW").count() > 0


# 7. MEDIUM classification
def test_medium_classification(seeded_db):
    assert determine_risk_level(calculate_risk(0.4, 0.4, 0.4, 0.4)) == "MEDIUM"
    assert seeded_db.query(RiskResult).filter(RiskResult.risk_level == "MEDIUM").count() > 0


# 8. HIGH classification
def test_high_classification(seeded_db):
    assert determine_risk_level(calculate_risk(0.6, 0.6, 0.6, 0.6)) == "HIGH"
    assert seeded_db.query(RiskResult).filter(RiskResult.risk_level == "HIGH").count() > 0


# 9. CRITICAL classification
def test_critical_classification(seeded_db):
    assert determine_risk_level(calculate_risk(1.0, 1.0, 1.0, 1.0)) == "CRITICAL"
    sl = _sl1042_id(seeded_db)
    latest = (
        seeded_db.query(RiskResult)
        .filter(RiskResult.asset_id == sl)
        .order_by(RiskResult.day.desc())
        .first()
    )
    assert latest.risk_level == determine_risk_level(latest.risk_score)
    assert latest.risk_score >= 0.75 and latest.risk_level == "CRITICAL"


# 10. Persistence calculation is deterministic
def test_persistence_deterministic(seeded_db):
    first = _streaks_from_timeline(seeded_db)
    seeded_db.expire_all()
    second = _streaks_from_timeline(seeded_db)
    assert first == second
    assert persistence_update(3, True) == 4
    assert persistence_update(3, False) == 0
    assert persistence_update(0, True) == 1
    assert persistence_score(7) == 1.0
    assert persistence_score(0) == 0.0


# 11. Persistence increases with sustained abnormal behavior
def test_persistence_increases_with_duration(seeded_db):
    assert PERSISTENCE_SATURATION_DAYS == 7
    vals = [persistence_score(s) for s in (1, 3, 6, 7, 10)]
    assert vals == sorted(vals)
    assert abs(vals[0] - 1 / 7) < 1e-12
    assert vals[3] == 1.0 and vals[4] == 1.0
    # SL-1042 sustains elevation into the final day: saturated persistence.
    sl = _sl1042_id(seeded_db)
    streaks = dict(_streaks_from_timeline(seeded_db)[sl])
    latest = (
        seeded_db.query(RiskResult)
        .filter(RiskResult.asset_id == sl)
        .order_by(RiskResult.day.desc())
        .first()
    )
    assert streaks[latest.day] >= 7
    assert latest.persistence_score == 1.0


# 12. A one-day spike does not imply long persistence
def test_one_day_spike_low_persistence(seeded_db):
    assert persistence_score(1) < 0.15
    # Every stored row agrees with the independently recomputed streak, so
    # an isolated elevated day can never carry a high persistence score.
    streaks = _streaks_from_timeline(seeded_db)
    checked = 0
    for aid, run in streaks.items():
        rows = {
            r.day: r
            for r in seeded_db.query(RiskResult)
            .filter(RiskResult.asset_id == aid)
            .all()
        }
        for day, streak in run:
            assert abs(rows[day].persistence_score - min(1.0, streak / 7)) < 1e-12
            if streak <= 1:
                assert rows[day].persistence_score < 0.15
            checked += 1
    assert checked == 100 * 30


# 13. Risk is deterministic
def test_risk_deterministic(seeded_db):
    db = TestingSessionLocal()
    try:
        scores1 = load_anomaly_scores(db)
        scores2 = load_anomaly_scores(db)
    finally:
        db.close()
    assert scores1 == scores2
    sl = _sl1042_id(seeded_db)
    rows = (
        seeded_db.query(RiskResult)
        .filter(RiskResult.asset_id == sl)
        .order_by(RiskResult.day)
        .all()
    )
    for r in rows:
        assert r.risk_score == calculate_risk(
            r.anomaly_score, r.fusion_score, r.smoothed_fusion_score, r.persistence_score
        )


# 14. Repeated pipeline execution produces identical values
# 16. No duplicate rows are created on repeated execution
def test_repeated_execution_identical_no_duplicates(seeded_db):
    before_count = seeded_db.query(func.count(RiskResult.id)).scalar()
    before = {
        (r.asset_id, r.day): (
            r.anomaly_score, r.fusion_score, r.smoothed_fusion_score,
            r.persistence_score, r.risk_score, r.risk_level,
        )
        for r in seeded_db.query(RiskResult).all()
    }
    db = TestingSessionLocal()
    try:
        result = compute_all_risks(db)
    finally:
        db.close()
    assert result == {"assets": 100, "risk_results": 3000}
    seeded_db.expire_all()
    after_count = seeded_db.query(func.count(RiskResult.id)).scalar()
    assert after_count == before_count == 3000
    for r in seeded_db.query(RiskResult).all():
        assert (
            r.anomaly_score, r.fusion_score, r.smoothed_fusion_score,
            r.persistence_score, r.risk_score, r.risk_level,
        ) == before[(r.asset_id, r.day)]


# 15. Database persistence works
def test_database_persistence(seeded_db):
    from sqlalchemy import inspect as sa_inspect
    assert "risk_results" in set(sa_inspect(engine).get_table_names())
    # FK integrity: every risk row joins to a real asset.
    joined = (
        seeded_db.query(func.count(RiskResult.id))
        .join(Asset, Asset.id == RiskResult.asset_id)
        .scalar()
    )
    assert joined == 3000
    # One row per (asset, day): no duplicates at the grain.
    dupes = (
        seeded_db.query(RiskResult.asset_id, RiskResult.day, func.count("*"))
        .group_by(RiskResult.asset_id, RiskResult.day)
        .having(func.count("*") > 1)
        .count()
    )
    assert dupes == 0
    assert seeded_db.query(RiskResult).filter(
        RiskResult.model_version != RISK_MODEL_VERSION).count() == 0


# 17. API returns the expected response
def test_risk_api(seeded_db):
    sl = _sl1042_id(seeded_db)
    for key in ("SL-1042", sl):
        resp = client.get(f"/api/assets/{key}/risk")
        assert resp.status_code == 200, (key, resp.text)
        body = resp.json()
        assert body["asset_external_code"] == "SL-1042"
        assert body["model_version"] == RISK_MODEL_VERSION
        for field in (
            "anomaly_score", "fusion_score", "smoothed_fusion_score",
            "persistence_score", "risk_score", "risk_level",
        ):
            assert field in body, field
        row = (
            seeded_db.query(RiskResult)
            .filter(RiskResult.asset_id == sl)
            .order_by(RiskResult.day.desc())
            .first()
        )
        assert abs(body["risk_score"] - row.risk_score) < 1e-12
        assert body["risk_level"] == row.risk_level


# 18. Unknown asset returns 404
def test_risk_api_unknown_asset(seeded_db):
    assert client.get("/api/assets/DOES-NOT-EXIST/risk").status_code == 404


# 19. SL-1042 is processed generically and is not hardcoded
def test_no_hardcoded_sl1042(seeded_db):
    src = inspect.getsource(risk_mod)
    code_only = re.sub(r'"""[\s\S]*?"""', "", src)
    code_only = re.sub(r"'''[\s\S]*?'''", "", code_only)
    code_only = "\n".join(line.split("#")[0] for line in code_only.splitlines())
    assert "1042" not in code_only
    sl = _sl1042_id(seeded_db)
    row = (
        seeded_db.query(RiskResult)
        .filter(RiskResult.asset_id == sl)
        .order_by(RiskResult.day.desc())
        .first()
    )
    assert row is not None and row.model_version == RISK_MODEL_VERSION


# Risk is calculated, not a copy of the Phase 4 status.
def test_risk_not_status_mapping(seeded_db):
    naive = {"NORMAL": "LOW", "WATCH": "MEDIUM", "EMERGING": "HIGH", "CRITICAL": "CRITICAL"}
    disagree = 0
    total = 0
    for fr in seeded_db.query(FusionResult).all():
        rr = (
            seeded_db.query(RiskResult)
            .filter(RiskResult.asset_id == fr.asset_id, RiskResult.day == fr.day)
            .one()
        )
        total += 1
        if naive[fr.status] != rr.risk_level:
            disagree += 1
    assert total == 3000
    assert disagree > 0


# 20. Risk pipeline leaves Phase 1/2/4 state unchanged.
def test_prior_phase_state_unchanged(seeded_db):
    assert seeded_db.query(Asset).count() == 100
    assert seeded_db.query(SensorReading).count() == (
        100 * 30 * 12 * 2 + 360 + config.OTHER_COMPLAINT_COUNT
    )
    assert seeded_db.query(func.count(FusionResult.id)).scalar() == 3000
    resp = client.get("/api/assets/SL-1042/fusion")
    assert resp.status_code == 200
