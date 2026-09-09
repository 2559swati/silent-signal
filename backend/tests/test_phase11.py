# pyrefly: ignore [missing-import]
"""Phase 11 tests: TEE abstraction + DemoTEEProvider + security API.

The Demo provider must use the real Phase 4-5 services in-process and
must NEVER report attested=True on any path.
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
from app.models.risk_results import RiskResult  # noqa: E402
from app.tee.base import TEEProvider  # noqa: E402
from app.tee.demo import DemoTEEProvider  # noqa: E402
from app.tee.factory import (  # noqa: E402
    UnsupportedTEEModeError,
    get_provider,
    resolve_mode,
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


def _sl1042(db):
    asset = db.query(Asset).filter(Asset.external_code == "SL-1042").first()
    assert asset is not None
    return asset


# 1. DemoTEEProvider implements TEEProvider.
def test_demo_implements_interface():
    provider = DemoTEEProvider()
    assert isinstance(provider, TEEProvider)
    assert issubclass(DemoTEEProvider, TEEProvider)


# 2. Demo mode reported.
def test_demo_mode_status():
    status = DemoTEEProvider().get_status()
    assert status.mode == "demo"
    assert status.healthy is True
    assert "demo" in status.description.lower()


# 3. attested=False, pcr0=None -- always.
def test_attestation_always_false():
    att = DemoTEEProvider().get_attestation_status()
    assert att.attested is False
    assert att.pcr0 is None


# 4. Repeated attestation reads can NEVER flip to True.
def test_attestation_never_true(seeded_db):
    provider = DemoTEEProvider()
    for _ in range(5):
        att = provider.get_attestation_status()
        assert att.attested is False
        assert att.pcr0 is None
    # Even after real analysis work, attestation stays false.
    provider.analyze_asset("SL-1042", seeded_db)
    assert provider.get_attestation_status().attested is False


# 5. Factory defaults to demo when TEE_MODE is missing.
def test_factory_default_demo(monkeypatch):
    monkeypatch.delenv("TEE_MODE", raising=False)
    assert resolve_mode() == "demo"
    assert isinstance(get_provider(), DemoTEEProvider)


# 6. TEE_MODE=demo selects DemoTEEProvider.
def test_factory_demo_mode(monkeypatch):
    monkeypatch.setenv("TEE_MODE", "demo")
    assert resolve_mode() == "demo"
    assert isinstance(get_provider(), DemoTEEProvider)


# 7. Unsupported modes fail clearly (never a fake production provider).
# NOTE (Phase 12): "nitro" is a SUPPORTED mode now (NitroTEEProvider behind
# the same TEEProvider interface). Only genuinely unknown modes raise.
def test_factory_unsupported_fails(monkeypatch):
    for bad in ("production", "enclave"):
        monkeypatch.setenv("TEE_MODE", bad)
        with pytest.raises(UnsupportedTEEModeError):
            get_provider()


# 7b. (Phase 12) TEE_MODE=nitro selects NitroTEEProvider -- never demo.
def test_factory_nitro_mode(monkeypatch):
    from app.tee.nitro import NITRO_MODE, NitroTEEProvider

    monkeypatch.setenv("TEE_MODE", "nitro")
    assert resolve_mode() == NITRO_MODE
    provider = get_provider()
    assert isinstance(provider, NitroTEEProvider)
    assert not isinstance(provider, DemoTEEProvider)
    assert provider.mode == NITRO_MODE


# analyze_asset delegates to the real Phase 4-5 services (no duplication).
def test_analyze_asset_uses_real_services(seeded_db):
    provider = DemoTEEProvider()
    result = provider.analyze_asset("SL-1042", seeded_db)
    sl = _sl1042(seeded_db)
    fusion = (
        seeded_db.query(FusionResult)
        .filter(FusionResult.asset_id == sl.id)
        .order_by(FusionResult.day.desc())
        .first()
    )
    risk = (
        seeded_db.query(RiskResult)
        .filter(RiskResult.asset_id == sl.id)
        .order_by(RiskResult.day.desc())
        .first()
    )
    assert result.asset_external_code == "SL-1042"
    assert result.risk_score == risk.risk_score
    assert result.risk_level == risk.risk_level
    assert result.fusion_score == risk.fusion_score
    assert result.fusion_status == fusion.status
    assert result.anomaly_score == risk.anomaly_score
    assert result.provider_mode == "demo"
    # UUID lookup works too; unknown assets fail clearly.
    by_uuid = provider.analyze_asset(sl.id, seeded_db)
    assert by_uuid.asset_external_code == "SL-1042"
    with pytest.raises(ValueError):
        provider.analyze_asset("NOPE", seeded_db)


# Security endpoints use the factory and report honest demo state.
def test_security_endpoints(seeded_db):
    status = client.get("/api/security/tee-status")
    assert status.status_code == 200, status.text
    assert status.json()["mode"] == "demo"
    assert status.json()["healthy"] is True
    att = client.get("/api/security/attestation")
    assert att.status_code == 200, att.text
    body = att.json()
    assert body["attested"] is False
    assert body["pcr0"] is None
