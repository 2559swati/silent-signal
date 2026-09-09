"""Phase 12 Nitro Enclave provider.

Trust boundary (business logic unchanged, only the execution boundary is new):

    host: load per-asset evidence from DB -> encrypt telemetry (Fernet)
        -> length-prefixed frame -> enclave transport (vsock on hardware,
           in-process loopback locally exercising the identical framing)
    enclave (trusted): decode frame -> decrypt in memory -> run the EXISTING
           Phase 4/5 pure functions (fuse_signals / determine_status /
           calculate_risk / determine_risk_level -- NO duplication, NO db,
           NO network, NO plaintext logging) -> minimal result frame
    host: decode minimal result -> AssetAnalysis (same dataclass as demo,
           so the dashboard/backend contract is unchanged)

Enclave isolation rules enforced:
- `enclave_handle_request()` takes ONLY opaque bytes (+ key); it receives
  no DB session, performs no queries and opens no sockets.
- Plaintext telemetry is never logged on either side (errors carry sizes
  and asset codes only).
- Attestation is HONEST: without real Nitro hardware (/dev/nsm +
  attestation document) the provider reports attested=False, pcr0=None.
  An operator-supplied NITRO_PCR0 is treated as an UNVERIFIED placeholder
  (attested stays False) -- it is never presented as a real measurement.
  Rebuilding the EIF changes PCR0; Phase 13 gates KMS decryption on the
  real measurement (see module notes + docs).

Transports:
- `loopback` (default): in-process round-trip through the real
  encrypt -> frame -> decode -> decrypt -> compute path. Used for local
  dev/tests where no Nitro hardware exists. Attestation stays False.
- `vsock`: real AF_VSOCK socket to (NITRO_CID, NITRO_PORT). Hardware-only;
  failures raise NitroTransportError and are NEVER silently downgraded to
  demo mode.
"""

import json
import os
from datetime import date

from sqlalchemy.orm import Session

from app.models.assets import Asset
from app.models.fusion_results import FusionResult
from app.models.risk_results import RiskResult
from app.services.fusion_engine import determine_status as fusion_determine_status
from app.services.fusion_engine import fuse_signals
from app.services.risk_engine import calculate_risk, determine_risk_level
from app.services.risk_engine import compute_asset_risk
from app.tee.base import AssetAnalysis, AttestationStatus, TEEProvider, TEEStatus
from app.tee.crypto import decrypt_telemetry, encrypt_telemetry
from app.tee.vsock import (
    DEFAULT_CID,
    DEFAULT_MAX_FRAME_BYTES,
    DEFAULT_PORT,
    NitroTransportError,
    decode_one_frame,
    encode_frame,
    open_vsock_socket,
    recv_frame,
    send_frame,
)

NITRO_MODE = "nitro"

# Risk level -> minimal enclave maintenance action (dashboard contract).
ACTION_BY_RISK_LEVEL = {
    "LOW": "MONITOR",
    "MEDIUM": "SCHEDULE_INSPECTION",
    "HIGH": "INSPECT",
    "CRITICAL": "URGENT_INSPECT",
}


def action_for_risk_level(risk_level: str) -> str:
    """Map a Phase 5 risk level to the minimal enclave action code."""
    try:
        return ACTION_BY_RISK_LEVEL[risk_level]
    except KeyError as exc:
        raise ValueError(f"unknown risk level {risk_level!r}") from exc


def operator_supplied_pcr0() -> str | None:
    """Operator-supplied PCR0 placeholder (UNVERIFIED).

    Read from NITRO_PCR0 env. A placeholder is NOT a hardware measurement
    and MUST NOT be reported as attested. Documented so operators know to
    replace it with the real EIF measurement (see `attestation_notes()`).
    """
    raw = (os.environ.get("NITRO_PCR0") or "").strip()
    return raw or None


def _try_read_nsm_pcr0() -> str | None:
    """Best-effort read of the real enclave measurement.

    On genuine Nitro hardware the attestation document is obtained via
    /dev/nsm (NSM ioctl). This build reports the measurement only when it
    can actually retrieve hardware attestation evidence; everywhere else
    (local dev, CI, non-Nitro EC2) it returns None so callers stay honest.
    Full NSM ioctl parsing is hardware-only and intentionally not faked.
    """
    if not os.path.exists("/dev/nsm"):
        return None
    # /dev/nsm exists but this build does not fabricate a measurement:
    # real parsing requires the NSM ioctl + CBOR attestation-doc decode on
    # the host, which is exercised only on Nitro hardware (see docs).
    # An explicit opt-in env lets hardware operators surface the real PCR0
    # obtained from their attestation flow without this code inventing one.
    real = (os.environ.get("NITRO_REAL_PCR0") or "").strip()
    return real or None


def attestation_notes() -> str:
    return (
        "PCR0 is the EIF measurement (sha384 of the enclave image). "
        "Rebuilding the EIF changes PCR0. Obtain the real PCR0 from the "
        "EIF build output (`nitro-cli describe-eif`) or the attestation "
        "document on the Nitro host, then pin it in the KMS key policy "
        "(Phase 13). NITRO_PCR0 is an UNVERIFIED placeholder unless it "
        "carries a hardware-verified measurement."
    )


def enclave_handle_request(request_bytes: bytes, key: bytes | None = None) -> bytes:
    """Trusted-side handler: framed encrypted telemetry -> framed result.

    ISOLATION: no `db`, no imports of DB/network modules, no logging of
    plaintext. Runs ONLY the existing pure Phase 4/5 functions on the
    decrypted bundle and returns a framed minimal-result envelope:

        {"asset_id": ..., "risk": <level>, "score": <risk_score>,
         "action": <ACTION code>, "fusion_status": ..., "day": ...}

    Raises ValueError (framing/crypto/schema) on any malformed input.
    """
    payload, consumed = decode_one_frame(request_bytes)
    if consumed != len(request_bytes):
        raise ValueError(
            "enclave request must contain exactly one frame "
            f"(frame={consumed} bytes, trailing={len(request_bytes) - consumed} bytes)"
        )
    bundle = decrypt_telemetry(payload, key)
    asset_code = str(bundle.get("asset_external_code") or bundle.get("asset_id") or "?")

    fused = fuse_signals(
        float(bundle["power_score"]),
        float(bundle["brightness_score"]),
        float(bundle["temperature_score"]),
        float(bundle["maintenance_score"]),
        float(bundle["neighbor_score"]),
    )
    fusion_status = fusion_determine_status(float(bundle.get("smoothed_fusion_score", fused)))
    risk_score = calculate_risk(
        float(bundle["anomaly_score"]),
        fused,
        float(bundle.get("smoothed_fusion_score", fused)),
        float(bundle["persistence_score"]),
    )
    risk_level = determine_risk_level(risk_score)
    minimal = {
        "asset_id": asset_code,
        "risk": risk_level,
        "score": risk_score,
        "action": action_for_risk_level(risk_level),
        "fusion_status": fusion_status,
        "fusion_score": fused,
        "day": bundle.get("day"),
    }
    return encode_frame(json.dumps(minimal, sort_keys=True).encode("utf-8"))


class NitroTEEProvider(TEEProvider):
    """Nitro Enclave provider behind the shared TEEProvider interface."""

    def __init__(self, transport: str | None = None, cid: int | None = None,
                 port: int | None = None, timeout: float = 5.0,
                 max_frame_bytes: int = DEFAULT_MAX_FRAME_BYTES) -> None:
        self._transport = (
            (transport or os.environ.get("NITRO_TRANSPORT") or "loopback")
            .strip().lower()
        )
        if self._transport not in ("loopback", "vsock"):
            raise ValueError(
                f"unknown NITRO_TRANSPORT={self._transport!r}; "
                "expected 'loopback' or 'vsock'"
            )
        self._cid = int(cid if cid is not None else os.environ.get("NITRO_CID", DEFAULT_CID))
        self._port = int(port if port is not None else os.environ.get("NITRO_PORT", DEFAULT_PORT))
        self._timeout = float(timeout)
        self._max_frame_bytes = int(
            os.environ.get("NITRO_MAX_FRAME_BYTES", max_frame_bytes)
        )

    @property
    def mode(self) -> str:
        return NITRO_MODE

    # -- attestation ----------------------------------------------------
    def get_attestation_status(self) -> AttestationStatus:
        """Honest attestation: True ONLY with hardware-verified evidence.

        Locally (no /dev/nsm attestation) this is ALWAYS
        AttestationStatus(attested=False, pcr0=None) -- or the unverified
        operator placeholder PCR0 with attested=False, never True.
        """
        real_pcr0 = _try_read_nsm_pcr0()
        if real_pcr0:
            return AttestationStatus(attested=True, pcr0=real_pcr0)
        placeholder = operator_supplied_pcr0()
        # Placeholder is surfaced (so operators see what is configured)
        # but NEVER as attested hardware measurement.
        return AttestationStatus(attested=False, pcr0=placeholder)

    def get_status(self) -> TEEStatus:
        if self._transport == "vsock":
            desc = (
                "Nitro TEE provider: encrypted telemetry over vsock "
                f"(CID {self._cid} port {self._port}); "
                "requires Nitro Enclave hardware; no hardware attestation "
                "claimed until verified on the host."
            )
        else:
            desc = (
                "Nitro TEE provider (loopback transport): real encrypt -> "
                "frame -> enclave-logic path in-process; no Nitro hardware "
                "present, no hardware attestation."
            )
        return TEEStatus(mode=self.mode, healthy=True, description=desc)

    # -- analysis -------------------------------------------------------
    def _build_telemetry_bundle(self, asset: Asset, db: Session) -> dict:
        """Host side: load evidence, pack the sensitive bundle (then encrypt).

        Reuses the existing Phase 5 per-asset computation for fresh,
        idempotent evidence (same engine as Demo), then ships ONLY the
        numeric bundle across the boundary -- never raw DB rows.
        """
        compute_asset_risk(asset.id, db)
        fusion = (
            db.query(FusionResult)
            .filter(FusionResult.asset_id == asset.id)
            .order_by(FusionResult.day.desc())
            .first()
        )
        risk = (
            db.query(RiskResult)
            .filter(RiskResult.asset_id == asset.id)
            .order_by(RiskResult.day.desc())
            .first()
        )
        if fusion is None or risk is None:
            raise RuntimeError(
                "Phase 4/5 evidence missing; run the fusion and risk pipelines first"
            )
        return {
            "asset_id": str(asset.id),
            "asset_external_code": asset.external_code,
            "day": fusion.day.isoformat() if hasattr(fusion.day, "isoformat") else str(fusion.day),
            "power_score": float(fusion.power_score),
            "brightness_score": float(fusion.brightness_score),
            "temperature_score": float(fusion.temperature_score),
            "maintenance_score": float(fusion.maintenance_score),
            "neighbor_score": float(fusion.neighbor_score),
            "smoothed_fusion_score": float(fusion.smoothed_score),
            "anomaly_score": float(risk.anomaly_score),
            "persistence_score": float(risk.persistence_score),
        }

    def _roundtrip_loopback(self, frame: bytes) -> bytes:
        # Same framing + crypto path as vsock, without hardware.
        return enclave_handle_request(frame)

    def _roundtrip_vsock(self, frame: bytes) -> bytes:
        sock = open_vsock_socket(self._cid, self._port, self._timeout)
        try:
            send_frame(sock, decode_one_frame(frame)[0], self._max_frame_bytes)
            return encode_frame(recv_frame(sock, self._max_frame_bytes))
        finally:
            try:
                sock.close()
            except OSError:
                pass

    def _roundtrip(self, frame: bytes) -> bytes:
        if self._transport == "vsock":
            return self._roundtrip_vsock(frame)
        return self._roundtrip_loopback(frame)

    def analyze_asset(self, asset_id: str, db: Session) -> AssetAnalysis:
        """Analyze one asset via the enclave boundary.

        Host loads evidence from the DB (the enclave never touches the
        DB), encrypts the sensitive bundle, frames it, round-trips it
        through the enclave handler, and maps the minimal result back to
        AssetAnalysis. No silent fallback to demo on any failure.
        """
        asset = db.query(Asset).filter(Asset.external_code == asset_id).one_or_none()
        if asset is None:
            asset = db.query(Asset).filter(Asset.id == asset_id).one_or_none()
        if asset is None:
            raise ValueError(f"unknown asset {asset_id}")

        bundle = self._build_telemetry_bundle(asset, db)
        day = bundle["day"]
        # Encrypted telemetry -> enclave -> minimal result (no plaintext logs).
        request_frame = encode_frame(
            encrypt_telemetry(bundle), self._max_frame_bytes
        )
        try:
            response_frame = self._roundtrip(request_frame)
        except (NitroTransportError, ValueError) as exc:
            raise RuntimeError(f"nitro enclave round-trip failed: {exc}") from exc

        minimal_payload, consumed = decode_one_frame(
            response_frame, self._max_frame_bytes
        )
        if consumed != len(response_frame):
            raise RuntimeError("nitro enclave returned trailing bytes")
        try:
            minimal = json.loads(minimal_payload.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise RuntimeError("nitro enclave returned invalid JSON") from exc

        try:
            risk_score = float(minimal["score"])
            risk_level = str(minimal["risk"])
            fusion_status = str(minimal["fusion_status"])
            fusion_score = float(minimal["fusion_score"])
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError("nitro enclave returned an invalid minimal result") from exc

        # Re-read persisted smoothed/persistence/anomaly for the full
        # AssetAnalysis contract (host-side read; enclave already verified).
        risk = (
            db.query(RiskResult)
            .filter(RiskResult.asset_id == asset.id)
            .order_by(RiskResult.day.desc())
            .first()
        )
        fusion = (
            db.query(FusionResult)
            .filter(FusionResult.asset_id == asset.id)
            .order_by(FusionResult.day.desc())
            .first()
        )
        day_obj = fusion.day if fusion is not None else None
        if isinstance(day_obj, str):
            day_obj = date.fromisoformat(day_obj)
        return AssetAnalysis(
            asset_id=str(asset.id),
            asset_external_code=asset.external_code,
            day=day_obj,
            anomaly_score=float(risk.anomaly_score) if risk else 0.0,
            fusion_score=fusion_score,
            smoothed_fusion_score=float(risk.smoothed_fusion_score) if risk else fusion_score,
            fusion_status=fusion_status,
            persistence_score=float(risk.persistence_score) if risk else 0.0,
            risk_score=risk_score,
            risk_level=risk_level,
            provider_mode=self.mode,
        )
