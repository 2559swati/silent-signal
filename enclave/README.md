# SilentSignal Enclave Application (Phase 12 trusted side)

`app/main.py` is the vsock server that runs INSIDE the Nitro Enclave.

## Trust boundary

- Listens on vsock (`CID_ANY`, port `NITRO_PORT`, default `5000`).
- One framed request per connection: framed **encrypted** telemetry bundle.
- Decrypts in memory, runs the EXISTING Phase 4/5 pure functions via
  `app.tee.nitro.enclave_handle_request` (no logic copied into the enclave).
- Returns ONLY the framed minimal result
  (`asset_id / risk / score / action / fusion_status / fusion_score / day`).

## Restrictions (enforced, see `app/main.py`)

- No database access, no `DATABASE_URL`, no queries.
- No internet, no external APIs, no HTTP, no KMS calls, no AWS credentials.
  Phase 13 KMS decryption is performed by the PARENT through its vsock
  proxy; the enclave only sees the data-key-encrypted envelope.
- No plaintext telemetry in logs (error lines carry sizes/exception types).

## Build & run (EC2 Nitro parent, Linux)

```bash
# 1. Build the Docker image (repo root as build context)
docker build -f enclave/Dockerfile -t silentsignal-enclave:latest .

# 2. Convert to an enclave image file (Linux only)
nitro-cli build-enclave \
  --docker-uri silentsignal-enclave:latest \
  --output-file silentsignal-enclave.eif

# 3. Read the real measurements (PCR0 pins the approved image, Phase 13)
nitro-cli describe-eif --eif-path silentsignal-enclave.eif

# 4. Run the enclave (CID 16 matches the backend default NITRO_CID)
nitro-cli run-enclave \
  --cpu-count 2 --memory 512 \
  --enclave-cid 16 \
  --eif-path silentsignal-enclave.eif

# 5. Verify / stop
nitro-cli describe-enclaves
nitro-cli terminate-enclave --enclave-id <EnclaveID>
```

All `nitro-cli` flags above are from the AWS Nitro Enclaves CLI reference
(`build-enclave --docker-uri/--output-file`, `describe-eif --eif-path`,
`run-enclave --cpu-count/--memory/--eif-path/--enclave-cid`,
`describe-enclaves`, `terminate-enclave --enclave-id`).
