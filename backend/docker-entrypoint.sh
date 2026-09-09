#!/bin/sh
# Phase 15 backend entrypoint: wait for Postgres, migrate, seed-if-empty.
#
# - Waits until Postgres accepts connections (health-gated depends_on is not
#   enough on its own: the DB can be reachable but still initializing).
# - Runs `alembic upgrade head` so a clean machine gets the Phase 1 schema.
# - Seeds demo data ONLY when the assets table is empty, by calling the
#   EXISTING demo/reset pipeline (reset_and_generate + Phase 4/5/6/7/9
#   compute_all_* -- the same calls as POST /api/demo/reset). An already
#   populated database is never touched.
# - Finally execs the CMD (uvicorn app.main:app, unchanged business logic).
set -e

python - <<'EOF'
import os, socket, sys, time, urllib.parse
url = os.environ.get("DATABASE_URL", "")
parts = urllib.parse.urlparse(url or "postgresql://postgres:5432/postgres")
host, port = parts.hostname or "postgres", parts.port or 5432
deadline = time.time() + 90
while True:
    try:
        with socket.create_connection((host, port), timeout=2):
            print(f"[entrypoint] postgres reachable at {host}:{port}", flush=True)
            break
    except OSError as exc:
        if time.time() > deadline:
            print(f"[entrypoint] postgres not reachable: {exc}", flush=True)
            sys.exit(1)
        time.sleep(2)
EOF

alembic upgrade head

python - <<'EOF'
import sys
sys.path.insert(0, "/app")
from app.core.db import SessionLocal
from app.models.assets import Asset
import app.models  # noqa: F401 - register models
db = SessionLocal()
try:
    count = db.query(Asset).count()
finally:
    db.close()
if count == 0:
    print("[entrypoint] assets table empty: running demo seed pipeline", flush=True)
    import sys as _sys
    _sys.path.insert(0, "/")
    from data.generate_dataset import reset_and_generate
    from app.services.fusion_engine import compute_all_days
    from app.services.risk_engine import compute_all_risks
    from app.services.explain_engine import compute_all_explanations
    from app.services.recommend_engine import compute_all_recommendations
    from app.services.alert_engine import compute_all_alerts
    db = SessionLocal()
    try:
        reset_and_generate(db)
        compute_all_days(db)
        compute_all_risks(db)
        compute_all_explanations(db)
        compute_all_recommendations(db)
        compute_all_alerts(db)
    finally:
        db.close()
    print("[entrypoint] demo seed complete", flush=True)
else:
    print(f"[entrypoint] assets table has {count} rows: keeping existing data", flush=True)
EOF

exec "$@"
