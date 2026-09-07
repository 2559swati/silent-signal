# pyrefly: ignore [missing-import]
from fastapi import FastAPI
# pyrefly: ignore [missing-import]
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
import app.models  # noqa: F401 - register SQLAlchemy models
from app.api.assets import router as assets_router
from app.api.demo import router as demo_router
from app.api.fusion import router as fusion_router
from app.api.risk import router as risk_router
from app.api.explanation import router as explanation_router
from app.api.recommendation import router as recommendation_router
from app.api.alert import router as alert_router

app = FastAPI(title=settings.PROJECT_NAME, version=settings.VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
def health_check():
    return {"status": "ok"}


app.include_router(assets_router, prefix="/api")
app.include_router(demo_router, prefix="/api")
app.include_router(fusion_router, prefix="/api")
app.include_router(risk_router, prefix="/api")
app.include_router(explanation_router, prefix="/api")
app.include_router(recommendation_router, prefix="/api")
app.include_router(alert_router, prefix="/api")
from app.api.anomaly import router as anomaly_router
app.include_router(anomaly_router, prefix="/api")


