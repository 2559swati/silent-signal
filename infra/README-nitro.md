# Phase 12 — Nitro Enclave Runbook (EC2 parent)

Local development uses `NITRO_TRANSPORT=loopback` (same encrypt → frame →
decrypt → compute path in-process, no hardware). Everything below needs a
Nitro-enabled EC2 parent. Flag syntax follows the AWS Nitro CLI reference.

## 0. Prerequisites (parent instance)

- Nitro-enabled EC2 instance (e.g. `m5.xlarge` or similar Nitro-system
  instance) with the Nitro Enclaves CLI installed:
  `sudo dnf install aws-nitro-enclaves-cli` (AL2023) and the vsock proxy
  for KMS (`vsock-proxy`, see Phase 13 doc) if KMS is used.
- Allocator memory configured (`/etc/nitro_enclaves/allocator.yaml`),
  then `sudo systemctl start nitro-enclaves-allocator.service`.

## 1. Build the enclave image (Linux only)

`build-enclave` is NOT supported on Windows: build on Linux, then copy
the `.eif` to the parent if needed.

```bash
# From the repo root:
docker build -f enclave/Dockerfile -t silentsignal-enclave:latest .

nitro-cli build-enclave \
  --docker-uri silentsignal-enclave:latest \
  --output-file silentsignal-enclave.eif
```

## 2. Check enclave status

```bash
nitro-cli describe-enclaves
```

## 3. Start the enclave

```bash
nitro-cli run-enclave \
  --cpu-count 2 --memory 512 \
  --enclave-cid 16 \
  --eif-path silentsignal-enclave.eif
```

`--enclave-cid 16` matches the backend default `NITRO_CID=16`.
(CPU/memory sizing: 2 vCPU / 512 MiB is the documented hello-world
baseline; raise `--memory` if the enclave OOMs on pandas/sklearn load.)

## 4. Obtain the enclave CID

```bash
nitro-cli describe-enclaves
# "EnclaveCID": 16  -> export NITRO_CID=16 on the parent backend.
```

## 5. Vsock communication

Wire format: `[4-byte big-endian length][payload]` (`app/tee/vsock.py`).
The backend (`NitroTEEProvider`, `NITRO_TRANSPORT=vsock`) opens
`AF_VSOCK` to `(NITRO_CID, NITRO_PORT=5000)`, sends the framed Fernet
envelope, and reads one framed minimal-result envelope back. Partial
reads/writes are looped; oversized/malformed/truncated frames are
rejected before use.

```bash
# Backend on the parent talks to the enclave:
TEE_MODE=nitro NITRO_TRANSPORT=vsock NITRO_CID=16 NITRO_PORT=5000 \
  uvicorn app.main:app
curl localhost:8000/api/security/tee-status
```

## 6. Required parent-side proxy

The enclave has no network. Anything leaving the box (Phase 13 KMS)
goes through the parent's vsock proxy (`vsock-proxy` service on the
parent, KMS endpoint allow-listed). Telemetry/result traffic needs no
proxy — it is direct parent↔enclave vsock.

## 7. Testing encrypted communication

```bash
# Loopback (any machine, no hardware): full encrypt->enclave->result path
NITRO_TRANSPORT=loopback pytest backend/tests/test_phase12.py -q

# On the parent with a running enclave (spot-check one asset):
TEE_MODE=nitro NITRO_TRANSPORT=vsock python - <<'EOF'
from app.core.db import SessionLocal
from app.tee.factory import get_provider
db = SessionLocal()
print(get_provider().analyze_asset("SL-1042", db))
EOF
```

## 8. Stopping the enclave

```bash
nitro-cli terminate-enclave --enclave-id <EnclaveID from describe-enclaves>
```

## 9. Safety rules

- `TEE_MODE=nitro` NEVER falls back to demo: transport/attestation
  failures are loud errors (HTTP 500 / raised `NitroTransportError`).
- No plaintext telemetry in logs on either side; ciphertext is
  authenticated (Fernet AEAD): tampered envelopes are rejected.
- Without hardware, attestation is honestly `attested=False, pcr0=None`
  (or the UNVERIFIED `NITRO_PCR0` placeholder with `attested=False`).
