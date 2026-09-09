"""Phase 12 Nitro Enclave application (runs INSIDE the enclave).

Trust boundary: this process is the trusted side. It receives framed,
Fernet-encrypted telemetry bundles over vsock, decrypts them IN MEMORY,
runs the EXISTING Phase 4/5 pure functions (no copies, no reimplementation)
and returns ONLY the framed minimal result:

    {"asset_id": ..., "risk": <level>, "score": <risk_score>,
     "action": <ACTION code>, "fusion_status": ..., "fusion_score": ...,
     "day": ...}

Enclave restrictions enforced (see module docstring of app.tee.nitro):
- NO database access (no DB session, no queries, no DATABASE_URL needed).
- NO internet / external APIs / HTTP / KMS calls. KMS-authorized decryption
  (Phase 13) is performed by the PARENT instance through its vsock proxy:
  the parent obtains the data key via KMS attestation-gated Decrypt and
  the enclave only ever sees the data-key-encrypted telemetry envelope.
  No AWS credentials exist inside the enclave.
- NO plaintext telemetry logging: errors carry frame sizes only.
- Business logic is REUSED via app.tee.nitro.enclave_handle_request
  (which itself reuses app.services.fusion_engine / risk_engine pure
  functions). This file is only the vsock server loop around it.

Run (inside the enclave image, see enclave/Dockerfile):
    python -m app.main            # from /srv/enclave on PYTHONPATH
Env:
    NITRO_PORT (default 5000)     # vsock listen port inside the enclave
"""

import os
import socket
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../backend")))

from app.tee.nitro import enclave_handle_request  # noqa: E402 -- reused trusted logic
from app.tee.vsock import DEFAULT_PORT, recv_frame, send_frame  # noqa: E402

# AF_VSOCK CID_ANY: listen on all local CIDs inside the enclave.
CID_ANY = 4294967295


def serve_forever(port: int) -> None:
    """Accept vsock connections and serve one framed request per connection."""
    listener = socket.socket(socket.AF_VSOCK, socket.SOCK_STREAM)
    listener.bind((CID_ANY, port))
    listener.listen(8)
    print(f"[enclave] listening on vsock port {port}", flush=True)
    while True:
        conn, _addr = listener.accept()
        try:
            try:
                payload = recv_frame(conn)
            except Exception as exc:
                # Framing failure: sizes only, never payload bytes.
                print(f"[enclave] bad frame ({type(exc).__name__}); closing", flush=True)
                continue
            try:
                from app.tee.vsock import encode_frame

                response = enclave_handle_request(encode_frame(payload))
            except Exception as exc:
                print(f"[enclave] request rejected ({type(exc).__name__}); closing", flush=True)
                continue
            try:
                # enclave_handle_request returns a frame; unwrap once and
                # re-send through the partial-write-safe path.
                from app.tee.vsock import decode_one_frame

                result_payload, _ = decode_one_frame(response)
                send_frame(conn, result_payload)
            except Exception as exc:
                print(f"[enclave] send failed ({type(exc).__name__})", flush=True)
        finally:
            try:
                conn.close()
            except OSError:
                pass


if __name__ == "__main__":
    serve_forever(int(os.environ.get("NITRO_PORT", DEFAULT_PORT)))
