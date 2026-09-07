import pandas as pd
from sqlalchemy.orm import Session
from datetime import timedelta
from app.models.sensor_readings import SensorReading
from data import config

def build_features(db: Session) -> pd.DataFrame:
    """Build fleet‑wide features for anomaly detection.
    Returns a DataFrame with one row per asset and columns:
    mean_power, std_power, mean_brightness, std_brightness,
    recent_power_mean, recent_brightness_mean,
    power_trend, brightness_trend.
    """
    start = config.FIXED_START
    end = start + timedelta(days=config.DATASET_DAYS)
    # Query all sensor readings within the period
    readings = (
        db.query(SensorReading)
        .filter(SensorReading.recorded_at >= start, SensorReading.recorded_at < end)
        .all()
    )
    if not readings:
        raise RuntimeError("No sensor data found for the configured period")
    # Convert ORM objects to a DataFrame for easy manipulation
    rows = [
        {
            "asset_id": r.asset_id,
            "timestamp": r.recorded_at,
            "sensor_type": r.sensor_type,
            "value": r.value,
        }
        for r in readings
    ]
    df = pd.DataFrame(rows)
    # Separate the two sensor types used in the project
    power = df[df.sensor_type == config.SENSOR_POWER]
    brightness = df[df.sensor_type == config.SENSOR_BRIGHTNESS]
    # Basic statistics per asset
    power_stats = (
        power.groupby("asset_id")
        .value.agg(["mean", "std"])
        .rename(columns={"mean": "mean_power", "std": "std_power"})
    )
    brightness_stats = (
        brightness.groupby("asset_id")
        .value.agg(["mean", "std"])
        .rename(columns={"mean": "mean_brightness", "std": "std_brightness"})
    )
    # Recent 7‑day means to capture short‑term drift
    recent_start = end - timedelta(days=7)
    recent_power = power[(power.timestamp >= recent_start) & (power.timestamp < end)]
    recent_brightness = brightness[(brightness.timestamp >= recent_start) & (brightness.timestamp < end)]
    recent_power_mean = recent_power.groupby("asset_id").value.mean().rename("recent_power_mean")
    recent_brightness_mean = recent_brightness.groupby("asset_id").value.mean().rename("recent_brightness_mean")
    # Linear trend (slope) for each asset using a simple least‑squares formula
    def _slope(series: pd.Series) -> float:
        if series.empty:
            return 0.0
        # TimedeltaIndex has no float dtype: go via int64 nanoseconds first
        # (values identical to the intended float-nanosecond representation).
        # Numpy arrays are used because pandas 3 removed Index.mean().
        x = (series.index - series.index.min()).astype("int64").astype(float).to_numpy()
        y = series.to_numpy(dtype=float)
        if x.max() == x.min():
            return 0.0
        xc = x - x.mean()
        yc = y - y.mean()
        denom = (xc ** 2).sum()
        if denom == 0:
            return 0.0
        return float((xc * yc).sum() / denom)

    power_trend = (
        power.groupby("asset_id")
        .apply(lambda g: _slope(g.set_index("timestamp").sort_index().value))
        .rename("power_trend")
    )
    brightness_trend = (
        brightness.groupby("asset_id")
        .apply(lambda g: _slope(g.set_index("timestamp").sort_index().value))
        .rename("brightness_trend")
    )
    # Combine all feature columns into a single DataFrame
    features = (
        power_stats.join(brightness_stats)
        .join(recent_power_mean)
        .join(recent_brightness_mean)
        .join(power_trend)
        .join(brightness_trend)
    )
    # Fill any missing values with the median of the column (robust default)
    features = features.fillna(features.median())
    features.reset_index(inplace=True)
    return features
