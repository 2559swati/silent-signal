"""Phase 12 encrypted-telemetry envelope for the Nitro Enclave boundary.

Host encrypts the sensitive per-asset telemetry bundle BEFORE it crosses
the (v)sock boundary; only the enclave side decrypts it in memory.
Fernet (AES-128-CBC + HMAC-SHA256 via the `cryptography` package) gives
authenticated encryption: tampered / truncated / wrong-key tokens fail
closed without revealing plaintext.

Security rules enforced here:
- Keys come from NITRO_DATA_KEY / TEE_DATA_KEY env (Fernet base64 key).
  A missing key generates an EPHEMERAL process-local key (local dev /
  tests only) -- never logged, never persisted.
- Plaintext telemetry is NEVER logged. Error messages carry only sizes
  and field names, never values.
- Payload schema is validated on decrypt (required fields, types,
  [0, 1] ranges) so malformed enclave inputs fail safely.
"""

import base64
import json
import os

from cryptography.fernet import Fernet, InvalidToken

REQUIRED_SIGNAL_FIELDS = (
    "power_score",
    "brightness_score",
    "temperature_score",
    "maintenance_score",
    "neighbor_score",
)

REQUIRED_FIELDS = REQUIRED_SIGNAL_FIELDS + ("anomaly_score", "persistence_score")


class TelemetryCryptoError(ValueError):
    """Raised when a telemetry envelope cannot be decrypted/validated."""


_EPHEMERAL_KEY: bytes | None = None


def _load_key_from_env() -> bytes | None:
    raw = os.environ.get("NITRO_DATA_KEY") or os.environ.get("TEE_DATA_KEY")
    if not raw:
        return None
    raw = raw.strip()
    try:
        # Validate it is a real Fernet key (also accepts raw 32B base64).
        Fernet(raw.encode("utf-8") if isinstance(raw, str) else raw)
        return raw.encode("utf-8") if isinstance(raw, str) else raw
    except Exception as exc:
        raise TelemetryCryptoError(
            "NITRO_DATA_KEY/TEE_DATA_KEY is not a valid Fernet key. "
            "Generate one with: python -c 'from cryptography.fernet import "
            "Fernet; print(Fernet.generate_key().decode())'"
        ) from exc


def get_data_key() -> bytes:
    """Return the envelope key (env) or an ephemeral process-local key.

    The ephemeral fallback is for local dev/tests only and is documented
    as such; production Nitro deployments MUST set NITRO_DATA_KEY (or a
    KMS-derived key in Phase 13). The key value is never logged.
    """
    global _EPHEMERAL_KEY
    env_key = _load_key_from_env()
    if env_key is not None:
        return env_key
    if _EPHEMERAL_KEY is None:
        _EPHEMERAL_KEY = Fernet.generate_key()
    return _EPHEMERAL_KEY


def _fernet(key: bytes | None = None) -> Fernet:
    return Fernet(key if key is not None else get_data_key())


def encrypt_telemetry(payload: dict, key: bytes | None = None) -> bytes:
    """Serialize + authenticated-encrypt a telemetry bundle.

    Raises TelemetryCryptoError on non-dict / non-JSON-serializable input.
    Never logs plaintext.
    """
    if not isinstance(payload, dict):
        raise TelemetryCryptoError("telemetry payload must be a dict")
    try:
        # Canonical JSON: deterministic bytes for identical input.
        plaintext = json.dumps(
            payload, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise TelemetryCryptoError("telemetry payload is not JSON-serializable") from exc
    return _fernet(key).encrypt(plaintext)


def decrypt_telemetry(token: bytes, key: bytes | None = None) -> dict:
    """Decrypt + validate a telemetry envelope.

    Raises TelemetryCryptoError on tampered / wrong-key / malformed /
    schema-invalid tokens. Error text never contains plaintext values.
    """
    if not isinstance(token, (bytes, bytearray)):
        raise TelemetryCryptoError("telemetry token must be bytes")
    try:
        plaintext = _fernet(key).decrypt(bytes(token))
    except InvalidToken as exc:
        raise TelemetryCryptoError(
            "telemetry envelope failed authentication "
            f"(size={len(token)} bytes; tampered, truncated or wrong key)"
        ) from exc
    except Exception as exc:
        raise TelemetryCryptoError(
            f"telemetry envelope could not be decrypted (size={len(token)} bytes)"
        ) from exc
    try:
        payload = json.loads(plaintext.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise TelemetryCryptoError("telemetry envelope is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise TelemetryCryptoError("telemetry payload must be a JSON object")
    missing = [f for f in REQUIRED_FIELDS if f not in payload]
    if missing:
        raise TelemetryCryptoError(
            f"telemetry payload missing fields: {sorted(missing)}"
        )
    for field in REQUIRED_FIELDS:
        try:
            value = float(payload[field])
        except (TypeError, ValueError) as exc:
            raise TelemetryCryptoError(
                f"telemetry field {field!r} must be numeric"
            ) from exc
        if not 0.0 <= value <= 1.0:
            raise TelemetryCryptoError(
                f"telemetry field {field!r} out of range [0, 1]"
            )
        payload[field] = value
    return payload


def generate_data_key() -> str:
    """Generate a new Fernet data key (base64 string) for NITRO_DATA_KEY."""
    return Fernet.generate_key().decode("utf-8")


def _redacted(payload: dict) -> str:
    """Safe debug summary: field names + sizes only, never values."""
    keys = sorted(payload.keys()) if isinstance(payload, dict) else []
    return f"<telemetry fields={keys}>"
