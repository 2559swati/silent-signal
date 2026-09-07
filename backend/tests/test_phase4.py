# pyrefly: ignore [missing-import]
"""Phase 4 tests: weak signals -> signal fusion -> emerging anomaly.

Covers the 18 required Phase 4 areas plus explicit Phase 1/2/3 regression
checks. Never modifies Phase 1/2/3 logic; existing test files are untouched.
"""

import inspect
import os
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
from app.models.maintenance_records import MaintenanceRecord  # noqa: E402
from app.models.sensor_readings import SensorReading  # noqa: E402
from app.services import fusion_engine as fe  # noqa: E402
from app.services.fusion_engine import (  # noqa: E402
    ALPHA,
    FUSION_MODEL_VERSION,
    WEIGHTS,
    build_signal_table,
    compute_all_days,
    confirm_transition,
    determine_status,
    ema_update,
    fuse_signals,
    grid_neighbors,
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

SIGNAL_COLS = [
    "power_score",
    "brightness_score",
    "temperature_score",
    "maintenance_score",
    "neighbor_score",
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


# 1. signal scores in [0, 1]
def test_signal_scores_in_range(seeded_db):
    for col in SIGNAL_COLS:
        bad = (
            seeded_db.query(FusionResult)
            .filter((getattr(FusionResult, col) < 0.0) | (getattr(FusionResult, col) > 1.0))
            .count()
        )
        assert bad == 0, col
    assert seeded_db.query(func.count(FusionResult.id)).scalar() == 100 * 30


# 2. exact weights
def test_exact_weights(seeded_db):
    assert WEIGHTS == {
        "power": 0.25,
        "brightness": 0.20,
        "temperature": 0.10,
        "maintenance": 0.20,
        "neighbor": 0.25,
    }


# 3. weights sum to 1
def test_weights_sum_to_one(seeded_db):
    assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-12


# 4. fusion formula
def test_fusion_formula(seeded_db):
    rows = seeded_db.query(FusionResult).limit(300).all()
    assert len(rows) > 0
    for r in rows:
        expected = fuse_signals(
            r.power_score,
            r.brightness_score,
            r.temperature_score,
            r.maintenance_score,
            r.neighbor_score,
        )
        assert abs(r.raw_score - expected) < 1e-9
    sl = _sl1042_id(seeded_db)
    r = (
        seeded_db.query(FusionResult)
        .filter(FusionResult.asset_id == sl)
        .order_by(FusionResult.day.desc())
        .first()
    )
    expected = (
        0.25 * r.power_score
        + 0.20 * r.brightness_score
        + 0.10 * r.temperature_score
        + 0.20 * r.maintenance_score
        + 0.25 * r.neighbor_score
    )
    assert abs(r.raw_score - expected) < 1e-9


# 5. fusion score in [0, 1]
def test_fusion_score_in_range(seeded_db):
    for col in ("raw_score", "smoothed_score"):
        bad = (
            seeded_db.query(FusionResult)
            .filter((getattr(FusionResult, col) < 0.0) | (getattr(FusionResult, col) > 1.0))
            .count()
        )
        assert bad == 0, col


# 6. status thresholds
def test_status_thresholds(seeded_db):
    assert determine_status(0.0) == "NORMAL"
    assert determine_status(0.2999) == "NORMAL"
    assert determine_status(0.30) == "WATCH"
    assert determine_status(0.4999) == "WATCH"
    assert determine_status(0.50) == "EMERGING"
    assert determine_status(0.7499) == "EMERGING"
    assert determine_status(0.75) == "CRITICAL"
    assert determine_status(1.0) == "CRITICAL"
    # Stored confirmed statuses obey the two-day rule along every trajectory:
    # an upgrade on day D requires day D-1's smoothed status at/above the
    # new level; downgrades are immediate.
    order = {"NORMAL": 0, "WATCH": 1, "EMERGING": 2, "CRITICAL": 3}
    assets = [a.id for a in seeded_db.query(Asset).all()]
    for aid in assets:
        rows = (
            seeded_db.query(FusionResult)
            .filter(FusionResult.asset_id == aid)
            .order_by(FusionResult.day)
            .all()
        )
        assert len(rows) == 30
        for prev, cur in zip(rows, rows[1:]):
            assert cur.status in ("NORMAL", "WATCH", "EMERGING", "CRITICAL")
            if order[cur.status] > order[prev.status]:
                prev_candidate = determine_status(prev.smoothed_score)
                assert order[prev_candidate] >= order[cur.status]


# 7. EMA alpha = 0.3
def test_ema_alpha(seeded_db):
    assert ALPHA == 0.3


# 8. EMA calculation
def test_ema_calculation(seeded_db):
    assert ema_update(None, 0.6) == 0.6  # initial EMA = first raw score
    assert abs(ema_update(0.5, 0.8) - (0.3 * 0.8 + 0.7 * 0.5)) < 1e-12
    # Day-0 smoothed equals raw for every asset; day-1 chains correctly.
    sl = _sl1042_id(seeded_db)
    rows = (
        seeded_db.query(FusionResult)
        .filter(FusionResult.asset_id == sl)
        .order_by(FusionResult.day)
        .all()
    )
    assert len(rows) == 30
    assert abs(rows[0].smoothed_score - rows[0].raw_score) < 1e-12
    for prev, cur in zip(rows, rows[1:]):
        assert abs(cur.smoothed_score - (0.3 * cur.raw_score + 0.7 * prev.smoothed_score)) < 1e-9


# 9. two-consecutive-day transition rule
def test_two_day_transition_rule(seeded_db):
    # Single isolated spike is held.
    assert confirm_transition("NORMAL", "NORMAL", "EMERGING") == "NORMAL"
    # Second consecutive day at the higher level confirms.
    assert confirm_transition("NORMAL", "EMERGING", "EMERGING") == "EMERGING"
    # Downgrades apply immediately (no hold).
    assert confirm_transition("EMERGING", "EMERGING", "WATCH") == "WATCH"
    assert confirm_transition("CRITICAL", "WATCH", "NORMAL") == "NORMAL"
    # Unchanged level passes through.
    assert confirm_transition("WATCH", "WATCH", "WATCH") == "WATCH"
    # Prior smoothed day above the candidate also satisfies "2 days at/above".
    assert confirm_transition("WATCH", "CRITICAL", "EMERGING") == "EMERGING"
    # Held status never exceeds the candidate.
    assert confirm_transition("NORMAL", "WATCH", "CRITICAL") == "NORMAL"


# 10. neighbor signal determinism (+ generic grid reuse, not a copy)
def test_neighbor_signal_determinism(seeded_db):
    db1 = TestingSessionLocal()
    db2 = TestingSessionLocal()
    try:
        _, t1, _ = build_signal_table(db1)
        _, t2, _ = build_signal_table(db2)
    finally:
        db1.close()
        db2.close()
    assert t1.keys() == t2.keys()
    for day in t1:
        assert set(t1[day]) == set(t2[day])
        for aid in t1[day]:
            assert t1[day][aid]["neighbor_score"] == t2[day][aid]["neighbor_score"]
    # Grid derivation matches the generator's documented hero neighbors
    # without the engine hardcoding them.
    assert set(grid_neighbors("SL-1042")) == set(config.NEIGHBORS)
    # Neighbor score is a neighborhood aggregate, not the asset's own score.
    sl = _sl1042_id(seeded_db)
    row = (
        seeded_db.query(FusionResult)
        .filter(FusionResult.asset_id == sl)
        .order_by(FusionResult.day.desc())
        .first()
    )
    assert 0.0 <= row.neighbor_score <= 1.0
    assert abs(row.neighbor_score - row.raw_score) > 1e-6


# 11. maintenance signal determinism (+ fleet-relative, frequency-based)
def test_maintenance_signal_determinism(seeded_db):
    db1 = TestingSessionLocal()
    db2 = TestingSessionLocal()
    try:
        _, t1, _ = build_signal_table(db1)
        _, t2, _ = build_signal_table(db2)
    finally:
        db1.close()
        db2.close()
    for day in t1:
        for aid in t1[day]:
            assert t1[day][aid]["maintenance_score"] == t2[day][aid]["maintenance_score"]
    # Fleet-relative: the max-count asset on the last day scores 1.0 while
    # an asset with no window records scores 0.0 (not "any visit => high").
    last_day = max(t1)
    scores = {aid: t1[last_day][aid]["maintenance_score"] for aid in t1[last_day]}
    assert max(scores.values()) == 1.0
    no_maint_codes = (
        set(a.external_code for a in seeded_db.query(Asset).all())
        - set(code for (code,) in seeded_db.query(Asset.external_code)
              .join(MaintenanceRecord, MaintenanceRecord.asset_id == Asset.id).distinct().all())
    )
    assert len(no_maint_codes) > 0
    code_to_id = {a.external_code: a.id for a in seeded_db.query(Asset).all()}
    for code in list(no_maint_codes)[:5]:
        assert scores[code_to_id[code]] == 0.0


# 12. SL-1042 calculation
def test_sl1042_calculation(seeded_db):
    resp = client.get("/api/assets/SL-1042/fusion")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    for key in (
        "power_score", "brightness_score", "temperature_score",
        "maintenance_score", "neighbor_score", "fusion_score",
        "smoothed_fusion_score", "status", "model_version",
    ):
        assert key in body, key
    assert body["asset_external_code"] == "SL-1042"
    assert body["model_version"] == FUSION_MODEL_VERSION
    assert body["status"] in ("NORMAL", "WATCH", "EMERGING", "CRITICAL")


# 13. no hardcoded SL-1042 result (executable logic only: docstrings and
# comments are stripped so documentation may still name the demo asset)
def test_no_hardcoded_sl1042(seeded_db):
    import re

    src = inspect.getsource(fe)
    code_only = re.sub(r'"""[\s\S]*?"""', "", src)
    code_only = re.sub(r"'''[\s\S]*?'''", "", code_only)
    code_only = "\n".join(
        line.split("#")[0] for line in code_only.splitlines()
    )
    assert "1042" not in code_only
    assert "NEIGHBORS" not in code_only
    # The fusion response is computed, never branched on asset identity.
    assert "external_code ==" not in code_only


# 14. deterministic repeat
def test_deterministic_repeat(seeded_db):
    db = TestingSessionLocal()
    try:
        days1, t1, refs1 = build_signal_table(db)
        days2, t2, refs2 = build_signal_table(db)
    finally:
        db.close()
    assert days1 == days2 and refs1 == refs2
    sl = _sl1042_id(seeded_db)
    for day in days1:
        assert t1[day][sl] == t2[day][sl]
    flat1 = [(d, a, v) for d in days1 for a, s in t1[d].items() for v in s.values()]
    flat2 = [(d, a, v) for d in days2 for a, s in t2[d].items() for v in s.values()]
    assert flat1 == flat2


# 15. idempotent repeat
def test_idempotent_repeat(seeded_db):
    before_count = seeded_db.query(func.count(FusionResult.id)).scalar()
    before_rows = {
        (r.asset_id, r.day): (r.raw_score, r.smoothed_score, r.status)
        for r in seeded_db.query(FusionResult).all()
    }
    db = TestingSessionLocal()
    try:
        compute_all_days(db)
    finally:
        db.close()
    seeded_db.expire_all()
    after_count = seeded_db.query(func.count(FusionResult.id)).scalar()
    assert after_count == before_count  # no duplicate rows
    for r in seeded_db.query(FusionResult).all():
        assert (r.raw_score, r.smoothed_score, r.status) == before_rows[(r.asset_id, r.day)]


# 16. Phase 1 regression
def test_phase1_regression(seeded_db):
    from sqlalchemy import inspect as sa_inspect
    tables = set(sa_inspect(engine).get_table_names())
    for t in ("assets", "sensor_readings", "maintenance_records", "anomalies",
              "signal_contributions", "recommendations", "tee_analysis"):
        assert t in tables, t
    resp = client.get("/api/assets?page=1&page_size=2")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 100 and len(body["items"]) == 2


# 17. Phase 2 regression
def test_phase2_regression(seeded_db):
    assert seeded_db.query(Asset).count() == 100
    assert seeded_db.query(SensorReading).count() == 100 * 30 * 12 * 2 + 360 + config.OTHER_COMPLAINT_COUNT
    sl = _sl1042_id(seeded_db)

    def _series(sensor_type):
        return [
            r.value for r in seeded_db.query(SensorReading)
            .filter(SensorReading.asset_id == sl, SensorReading.sensor_type == sensor_type)
            .order_by(SensorReading.recorded_at).all()
        ]

    power, bright = _series(config.SENSOR_POWER), _series(config.SENSOR_BRIGHTNESS)
    assert sum(power[-60:]) / 60 > sum(power[:60]) / 60 + 5.0
    assert sum(bright[:60]) / 60 > sum(bright[-60:]) / 60 + 5.0


# 18. Phase 3 regression
def test_phase3_regression(seeded_db):
    import ml.anomaly as anom
    import sklearn.ensemble
    assert anom.MODEL_VERSION == "isolation_forest_v1"
    src = inspect.getsource(anom._train_and_score)
    assert "random_state=42" in src
    assert "n_estimators=100" in src
    assert "contamination=0.05" in src
    from ml.features import build_features
    feats = build_features(seeded_db)
    assert len(feats) == 100
    scores = anom._train_and_score(feats)
    assert float(scores["score"].min()) >= 0.0 and float(scores["score"].max()) <= 1.0
    code_of = {a.id: a.external_code for a in seeded_db.query(Asset).all()}
    sl_id = next(i for i, c in code_of.items() if c == "SL-1042")
    sl_score = float(scores.loc[scores["asset_id"] == sl_id, "score"].iloc[0])
    rank = int((scores["score"] > sl_score).sum() + 1)
    assert rank == 1


def test_fusion_api(seeded_db):
    sl = _sl1042_id(seeded_db)
    for key in ("SL-1042", sl):
        resp = client.get(f"/api/assets/{key}/fusion")
        assert resp.status_code == 200, (key, resp.text)
        body = resp.json()
        assert body["asset_external_code"] == "SL-1042"
        assert body["model_version"] == FUSION_MODEL_VERSION
    assert client.get("/api/assets/DOES-NOT-EXIST/fusion").status_code == 404
