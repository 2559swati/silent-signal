# Phase 12 Nitro Enclave image for the SilentSignal trusted side.
#
# Build on a Linux host with the Nitro CLI (build-enclave is NOT supported
# on Windows -- build on Linux, then transfer the .eif to the parent):
#
#   docker build -f enclave/Dockerfile -t silentsignal-enclave:latest .
#   nitro-cli build-enclave \
#     --docker-uri silentsignal-enclave:latest \
#     --output-file silentsignal-enclave.eif
#
# The image contains NO database client config, NO AWS credentials and NO
# network egress: the enclave talks only vsock to the parent (port 5000).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    NITRO_PORT=5000

WORKDIR /srv/enclave

# Reuse the exact backend modules (tee framing/crypto, nitro trusted
# handler, fusion/risk pure functions) so the enclave never drifts from
# the host-side logic. `data/` is needed by fusion_engine (grid config).
COPY backend/requirements.txt /tmp/backend-requirements.txt
RUN pip install --no-cache-dir -r /tmp/backend-requirements.txt

COPY backend/ ./backend/
COPY data/ ./data/
COPY enclave/app/ ./enclave_app/

# enclave/app/main.py inserts ../../backend on sys.path itself, so it also
# runs outside Docker (local smoke tests). Inside Docker, PYTHONPATH covers
# the backend package for the reused app.tee / app.services modules.
ENV PYTHONPATH=/srv/enclave/backend:/srv/enclave

CMD ["python", "-m", "enclave_app.main"]
