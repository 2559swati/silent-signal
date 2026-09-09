import sys
sys.path.append('d:/NEXTALERT/silent-signal/backend')

from app.core.db import SessionLocal
from app.models.assets import Asset
from app.models.sensor_readings import SensorReading
from app.models.anomalies import AnomalyResult
from ml.anomaly import _train_and_score
from ml.features import build_features
# pyrefly: ignore [missing-import]
from sqlalchemy import func

def main():
    db = SessionLocal()
    try:
        total_assets = db.query(func.count(Asset.id)).scalar()
        total_readings = db.query(func.count(SensorReading.id)).scalar()
        total_anomalies = db.query(func.count(AnomalyResult.id)).scalar()
        print('TOTAL_ASSETS', total_assets)
        print('TOTAL_READINGS', total_readings)
        print('TOTAL_ANOMALY_RESULTS', total_anomalies)
        features = build_features(db)
        print('FEATURE_COLUMNS', list(features.columns))
        scores_df = _train_and_score(features)
        print('SCORE_MIN', scores_df['score'].min())
        print('SCORE_MAX', scores_df['score'].max())
        print('SCORE_MEAN', scores_df['score'].mean())
        print('SCORE_MEDIAN', scores_df['score'].median())
        sl = scores_df[scores_df['asset_id'] == 'SL-1042']
        if not sl.empty:
            sl_score = sl['score'].iloc[0]
            rank = (scores_df['score'] > sl_score).sum() + 1
            percentile = rank / len(scores_df) * 100
            print('SL_SCORE', sl_score)
            print('SL_RANK', rank)
            print('SL_PERCENTILE', percentile)
        else:
            print('SL-1042 not found in scores')
    finally:
        db.close()

if __name__ == '__main__':
    main()
