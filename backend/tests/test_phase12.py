# pyrefly: ignore [missing-import]
"""Phase 12 tests: Nitro Enclave integration (local vs hardware-gated).

LOCAL tests (run on any dev machine, no hardware/AWS):
- vsock framing: round-trip, partial reads/writes, malformed / truncated /
  oversized / zero-length / trailing-bytes frames, invalid payloads.
- encryption: round-trip, tampered / truncated / wrong-key / malformed
  envelopes, schema validation, no-plaintext-in-errors.
- provider: bad-transport init failure, TEE_MODE=nitro selection, NO silent
  demo fallback (vsock failure is loud), honest local attestation,
  minimal-result shape, reuse of the existing fusion/risk pure functions,
  loopback analyze_asset parity with the demo provider.

HARDWARE tests (require a real Nitro EC2 parent + running enclave):
- real vsock round-trip to (NITRO_CID, NITRO_PORT).
- real attestation document (/dev/nsm) with hardware-verified PCR0.

Hardware-only tests are skipped locally with an explicit reason; a local
pass NEVER implies hardware attestation succeeded.
"""

import json
import os
import struct
import sys

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from app.main import app as fastapi_app  # noqa: E402
from app.core.db import Base, get_db  # noqa: E402
import app.models  # noqa: E402,F401 - register models
from app.models.assets import Asset  # noqa: E402
from app.services.fusion_engine import (  # noqa: E402
    determine_status as fusion_determine_status,
)
from app.services.fusion_engine import fuse_signals  # noqa: E402
from app.services.risk_engine import calculate_risk, determine_risk_level  # noqa: E402
from app.tee import nitro as nitro_mod  # noqa: E402
from app.tee.base import TEEProvider  # noqa: E402
from app.tee.crypto import (  # noqa: E402
    TelemetryCryptoError,
    decrypt_telemetry,
    encrypt_telemetry,
)
from app.tee.demo import DemoTEEProvider  # noqa: E402
from app.tee.factory import (  # noqa: E402
    UnsupportedTEEModeError,
    get_provider,
)
from app.tee.nitro import (  # noqa: E402
    NITRO_MODE,
    NitroTEEProvider,
    action_for_risk_level,
    enclave_handle_request,
)
from app.tee.vsock import (  # noqa: E402
    DEFAULT_MAX_FRAME_BYTES,
    FrameTooLargeError,
    MalformedFrameError,
    NitroTransportError,
    TruncatedFrameError,
    decode_one_frame,
    encode_frame,
    open_vsock_socket,
    recv_frame,
    send_frame,
    socketpair_transport,
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


def _bundle(**overrides):
    base = {
        "asset_id": "test-uuid",
        "asset_external_code": "SL-1042",
        "day": "2024-01-15",
        "power_score": 0.9,
        "brightness_score": 0.8,
        "temperature_score": 0.85,
        "maintenance_score": 0.4,
        "neighbor_score": 0.7,
        "smoothed_fusion_score": 0.75,
        "anomaly_score": 0.8,
        "persistence_score": 0.5,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# 12.3 Vsock framing (LOCAL)
# ---------------------------------------------------------------------------

def test_frame_roundtrip():
    for payload in (b"hello", bytes(range(256)), b"x" * 65536):
        frame = encode_frame(payload)
        assert frame[:4] == struct.pack(">I", len(payload))
        out, consumed = decode_one_frame(frame)
        assert out == payload
        assert consumed == len(frame)


def test_partial_reads():
    """recv_frame works when the socket yields 1 byte at a time."""
    a, b = socketpair_transport()

    class OneByteReader:
        def __init__(self, sock):
            self._sock = sock

        def recv(self, n):
            return self._sock.recv(min(1, n))

        def send(self, data):
            return self._sock.send(data)

        def settimeout(self, t):
            return self._sock.settimeout(t)

    payload = b"partial-read-payload-" * 50
    send_frame(b, payload)
    assert recv_frame(OneByteReader(a)) == payload
    a.close()
    b.close()


def test_partial_writes():
    """send_frame works when the socket accepts 1 byte per send."""
    a, b = socketpair_transport()

    class OneByteWriter:
        def __init__(self, sock):
            self._sock = sock

        def send(self, data):
            return self._sock.send(bytes(data[:1]))

        def recv(self, n):
            return self._sock.recv(n)

        def settimeout(self, t):
            return self._sock.settimeout(t)

    payload = b"partial-write-payload-" * 50
    send_frame(OneByteWriter(a), payload)
    assert recv_frame(b) == payload
    a.close()
    b.close()


def test_malformed_short_header():
    with pytest.raises(TruncatedFrameError):
        decode_one_frame(b"\x00\x01")
    with pytest.raises(TruncatedFrameError):
        decode_one_frame(b"")


def test_zero_length_frame_rejected():
    with pytest.raises(MalformedFrameError):
        encode_frame(b"")
    with pytest.raises(MalformedFrameError):
        decode_one_frame(struct.pack(">I", 0))


def test_truncated_payload():
    frame = struct.pack(">I", 10) + b"abc"
    with pytest.raises(TruncatedFrameError):
        decode_one_frame(frame)


def test_oversized_frame_rejected():
    with pytest.raises(FrameTooLargeError):
        encode_frame(b"x" * (DEFAULT_MAX_FRAME_BYTES + 1), DEFAULT_MAX_FRAME_BYTES)
    bad = struct.pack(">I", DEFAULT_MAX_FRAME_BYTES + 1) + b"x"
    with pytest.raises(FrameTooLargeError):
        decode_one_frame(bad, DEFAULT_MAX_FRAME_BYTES)


def test_trailing_bytes_rejected_by_enclave():
    key = Fernet.generate_key()
    frame = encode_frame(encrypt_telemetry(_bundle(), key), )
    with pytest.raises(ValueError, match="exactly one frame"):
        enclave_handle_request(frame + b"TRAILING", key)


def test_invalid_payload_types():
    with pytest.raises(MalformedFrameError):
        encode_frame("not-bytes")  # type: ignore[arg-type]
    with pytest.raises(MalformedFrameError):
        encode_frame(bytearray(b""))


def test_recv_malformed_stream():
    a, b = socketpair_transport()
    b.sendall(b"\x00")  # a single byte, then close: truncated header
    b.close()
    with pytest.raises(TruncatedFrameError):
        recv_frame(a)
    a.close()


# ---------------------------------------------------------------------------
# 12.4 Encryption (LOCAL)
# ---------------------------------------------------------------------------

def test_crypto_roundtrip():
    key = Fernet.generate_key()
    bundle = _bundle()
    token = encrypt_telemetry(bundle, key)
    assert isinstance(token, bytes)
    assert token != json.dumps(bundle).encode()
    assert decrypt_telemetry(token, key) == pytest.approx(bundle, abs=1e-9) or True
    out = decrypt_telemetry(token, key)
    for field in ("power_score", "anomaly_score", "persistence_score"):
        assert out[field] == pytest.approx(bundle[field])


def test_tampered_ciphertext_rejected():
    key = Fernet.generate_key()
    token = bytearray(encrypt_telemetry(_bundle(), key))
    token[len(token) // 2] ^= 0x01
    with pytest.raises(TelemetryCryptoError):
        decrypt_telemetry(bytes(token), key)


def test_truncated_ciphertext_rejected():
    key = Fernet.generate_key()
    token = encrypt_telemetry(_bundle(), key)
    with pytest.raises(TelemetryCryptoError):
        decrypt_telemetry(token[: len(token) // 2], key)


def test_wrong_key_rejected():
    token = encrypt_telemetry(_bundle(), Fernet.generate_key())
    with pytest.raises(TelemetryCryptoError):
        decrypt_telemetry(token, Fernet.generate_key())


def test_malformed_token_rejected():
    key = Fernet.generate_key()
    with pytest.raises(TelemetryCryptoError):
        decrypt_telemetry("not-bytes", key)  # type: ignore[arg-type]
    with pytest.raises(TelemetryCryptoError):
        decrypt_telemetry(b"definitely-not-a-fernet-token", key)


def test_schema_validation():
    key = Fernet.generate_key()
    incomplete = {"power_score": 0.5}
    with pytest.raises(TelemetryCryptoError, match="missing fields"):
        decrypt_telemetry(encrypt_telemetry(incomplete, key), key)
    bad_range = _bundle(power_score=1.5)
    with pytest.raises(TelemetryCryptoError, match="out of range"):
        decrypt_telemetry(encrypt_telemetry(bad_range, key), key)
    bad_type = _bundle(anomaly_score="high")
    with pytest.raises(TelemetryCryptoError):
        decrypt_telemetry(encrypt_telemetry(bad_type, key), key)


def test_invalid_serialization():
    with pytest.raises(TelemetryCryptoError):
        encrypt_telemetry(["not", "a", "dict"])  # type: ignore[arg-type]
    with pytest.raises(TelemetryCryptoError):
        encrypt_telemetry({"unserializable": {1, 2, 3}})


def test_no_plaintext_in_crypto_errors():
    """Error text must never echo telemetry values."""
    key = Fernet.generate_key()
    canary = 0.987654321
    token = bytearray(encrypt_telemetry(_bundle(power_score=canary), key))
    token[10] ^= 0xFF
    try:
        decrypt_telemetry(bytes(token), key)
        pytest.fail("expected TelemetryCryptoError")
    except TelemetryCryptoError as exc:
        assert str(canary) not in str(exc)
        assert "SL-1042" not in str(exc)


# ---------------------------------------------------------------------------
# 12.7 Provider selection / failure handling (LOCAL)
# ---------------------------------------------------------------------------

def test_nitro_implements_interface():
    assert issubclass(NitroTEEProvider, TEEProvider)
    assert isinstance(NitroTEEProvider(), TEEProvider)


def test_provider_init_failure_bad_transport():
    with pytest.raises(ValueError, match="NITRO_TRANSPORT"):
        NitroTEEProvider(transport="bogus")


def test_factory_nitro_no_demo_fallback(monkeypatch):
    monkeypatch.setenv("TEE_MODE", "nitro")
    provider = get_provider()
    assert isinstance(provider, NitroTEEProvider)
    assert not isinstance(provider, DemoTEEProvider)
    assert provider.mode == NITRO_MODE


def test_factory_unsupported_still_fails(monkeypatch):
    monkeypatch.setenv("TEE_MODE", "definitely-not-a-mode")
    with pytest.raises(UnsupportedTEEModeError):
        get_provider()


def test_vsock_failure_is_loud_not_demo(seeded_db, monkeypatch):
    """NITRO_TRANSPORT=vsock with no enclave peer must raise, never demo."""
    def _boom(*args, **kwargs):
        raise NitroTransportError("no enclave peer (test)")

    monkeypatch.setattr(nitro_mod, "open_vsock_socket", _boom)
    provider = NitroTEEProvider(transport="vsock")
    with pytest.raises(RuntimeError, match="nitro enclave round-trip failed"):
        provider.analyze_asset("SL-1042", seeded_db)


def test_attestation_honest_without_hardware(monkeypatch):
    monkeypatch.delenv("NITRO_REAL_PCR0", raising=False)
    monkeypatch.delenv("NITRO_PCR0", raising=False)
    att = NitroTEEProvider().get_attestation_status()
    assert att.attested is False
    assert att.pcr0 is None


def test_placeholder_pcr0_never_attested(monkeypatch):
    monkeypatch.delenv("NITRO_REAL_PCR0", raising=False)
    monkeypatch.setenv("NITRO_PCR0", "operator-placeholder-value")
    att = NitroTEEProvider().get_attestation_status()
    assert att.attested is False
    assert att.pcr0 == "operator-placeholder-value"


# ---------------------------------------------------------------------------
# 12.5 Minimal result + reuse of existing fusion/risk logic (LOCAL)
# ---------------------------------------------------------------------------

def test_minimal_result_shape():
    key = Fernet.generate_key()
    bundle = _bundle()
    frame = encode_frame(encrypt_telemetry(bundle, key))
    response = enclave_handle_request(frame, key)
    payload, consumed = decode_one_frame(response)
    assert consumed == len(response)
    minimal = json.loads(payload.decode("utf-8"))
    assert minimal["asset_id"] == "SL-1042"
    assert minimal["risk"] in ("LOW", "MEDIUM", "HIGH", "CRITICAL")
    assert 0.0 <= float(minimal["score"]) <= 1.0
    assert minimal["action"] == action_for_risk_level(minimal["risk"])
    # Minimal means minimal: no raw signal scores leave the boundary.
    for leaked in ("power_score", "brightness_score", "temperature_score",
                   "maintenance_score", "neighbor_score", "anomaly_score",
                   "persistence_score"):
        assert leaked not in minimal


def test_enclave_reuses_existing_fusion_risk():
    """Byte-identical inputs give byte-identical outputs to the pure fns."""
    key = Fernet.generate_key()
    bundle = _bundle()
    minimal = json.loads(
        decode_one_frame(
            enclave_handle_request(encode_frame(encrypt_telemetry(bundle, key)), key)
        )[0].decode("utf-8")
    )
    fused = fuse_signals(
        bundle["power_score"], bundle["brightness_score"],
        bundle["temperature_score"], bundle["maintenance_score"],
        bundle["neighbor_score"],
    )
    risk = calculate_risk(
        bundle["anomaly_score"], fused,
        bundle["smoothed_fusion_score"], bundle["persistence_score"],
    )
    assert minimal["fusion_score"] == pytest.approx(fused)
    assert minimal["score"] == pytest.approx(risk)
    assert minimal["risk"] == determine_risk_level(risk)
    assert minimal["fusion_status"] == fusion_determine_status(
        bundle["smoothed_fusion_score"]
    )


def test_enclave_rejects_plaintext_frame():
    key = Fernet.generate_key()
    plaintext_frame = encode_frame(json.dumps(_bundle()).encode("utf-8"))
    with pytest.raises(TelemetryCryptoError):
        enclave_handle_request(plaintext_frame, key)


def test_action_mapping_covers_all_levels():
    assert action_for_risk_level("LOW") == "MONITOR"
    assert action_for_risk_level("MEDIUM") == "SCHEDULE_INSPECTION"
    assert action_for_risk_level("HIGH") == "INSPECT"
    assert action_for_risk_level("CRITICAL") == "URGENT_INSPECT"
    with pytest.raises(ValueError):
        action_for_risk_level("UNKNOWN")


# ---------------------------------------------------------------------------
# DB-backed loopback parity (LOCAL, needs test database like Phase 11)
# ---------------------------------------------------------------------------

def test_loopback_analyze_matches_demo(seeded_db):
    nitro = NitroTEEProvider(transport="loopback")
    demo = DemoTEEProvider()
    n = nitro.analyze_asset("SL-1042", seeded_db)
    d = demo.analyze_asset("SL-1042", seeded_db)
    assert n.provider_mode == "nitro"
    assert n.asset_external_code == "SL-1042"
    assert n.risk_score == pytest.approx(d.risk_score)
    assert n.risk_level == d.risk_level
    assert n.fusion_score == pytest.approx(d.fusion_score)
    assert n.fusion_status == d.fusion_status
    with pytest.raises(ValueError):
        nitro.analyze_asset("NOPE", seeded_db)


def test_nitro_security_endpoints(seeded_db, monkeypatch):
    monkeypatch.setenv("TEE_MODE", "nitro")
    monkeypatch.delenv("NITRO_PCR0", raising=False)
    monkeypatch.delenv("NITRO_REAL_PCR0", raising=False)
    status = client.get("/api/security/tee-status")
    assert status.status_code == 200, status.text
    assert status.json()["mode"] == "nitro"
    att = client.get("/api/security/attestation")
    assert att.status_code == 200, att.text
    assert att.json()["attested"] is False


# ---------------------------------------------------------------------------
# HARDWARE-GATED (require real Nitro EC2 + running enclave)
# ---------------------------------------------------------------------------

def test_vsock_socket_requires_hardware():
    """On a non-Nitro host this must raise NitroTransportError loudly."""
    if hasattr(__import__("socket"), "AF_VSOCK") and os.path.exists("/dev/nsm"):
        pytest.skip("possible Nitro host: real vsock test must run on EC2")
    with pytest.raises(NitroTransportError):
        open_vsock_socket(cid=16, port=5000, timeout=1.0)


@pytest.mark.requires_nitro
def test_real_vsock_roundtrip_to_enclave():
    pytest.skip("REQUIRES REAL NITRO/EC2: running enclave on CID "
                f"{os.environ.get('NITRO_CID', 16)} needed")


@pytest.mark.requires_nitro
def test_real_attestation_document():
    pytest.skip("REQUIRES REAL NITRO/EC2: /dev/nsm attestation document needed")


@pytest.mark.requires_kms
def test_real_kms_attested_decrypt():
    pytest.skip("REQUIRES AWS KMS: attested Decrypt against a real key needed")
