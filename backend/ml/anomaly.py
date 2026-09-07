import uuid
from datetime import datetime
from typing import List

import pandas as pd
from sklearn.ensemble import IsolationForest

from app.core.db import SessionLocal
from app.models.anomalies import AnomalyResult
from .features import build_features

MODEL_VERSION = "isolation_forest_v1"

def _train_and_score(features: pd.DataFrame) -> pd.DataFrame:
    """Train IsolationForest and return DataFrame with asset_id and normalized score."""
    X = features.drop(columns=["asset_id"]).values
    model = IsolationForest(
        n_estimators=100,
        contamination=0.05,
        random_state=42,
        max_samples="auto",
    )
    model.fit(X)
    raw = model.decision_function(X)
    anomaly = -raw
    min_a, max_a = anomaly.min(), anomaly.max()
    if max_a > min_a:
        norm = (anomaly - min_a) / (max_a - min_a)
    else:
        norm = [0.0] * len(anomaly)
    scores = pd.Series(norm, index=features["asset_id"], name="score")
    return pd.DataFrame({"asset_id": scores.index, "score": scores.values})

def run_anomaly_pipeline(db_session=None) -> List[AnomalyResult]:
    """Build features, train model, persist AnomalyResult rows.
    Returns list of ORM objects that were upserted.
    """
    close_own = False
    if db_session is None:
        db_session = SessionLocal()
        close_own = True
    try:
        features = build_features(db_session)
        scores_df = _train_and_score(features)
        now = datetime.utcnow()
        results = []
        for _, row in scores_df.iterrows():
            ar = AnomalyResult(
                asset_id=row["asset_id"],
                scored_at=now,
                score=row["score"],
                model_version=MODEL_VERSION,
            )
            db_session.merge(ar)
            results.append(ar)
        db_session.commit()
        return results
    finally:
        if close_own:
            db_session.close()
