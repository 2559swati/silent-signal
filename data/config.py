"""Phase 2 deterministic synthetic dataset configuration (Blueprint Section 5).

All generator constants live here. Nothing in generate_dataset.py should
hardcode these values. Phase 1 schema is frozen, so grid coordinates are
computed deterministically from the 10x10 layout and used for neighbor
selection / environmental correlation even though the Phase 1 assets table
has no lat/lon columns (see deviations in final report).
"""

from datetime import datetime

# Deterministic RNG seed. Generator must use numpy.random.default_rng(RANDOM_SEED).
RANDOM_SEED = 42
SEED = RANDOM_SEED  # backwards-compatible alias

# Asset population: 10x10 grid, codes SL-1001..SL-1100.
NUM_ASSETS = 100
GRID_ROWS = 10
GRID_COLS = 10
FIRST_CODE = 1001  # external codes SL-1001 .. SL-1100

# Deterministic municipal-style local grid (degrees). Row-major layout:
# index i -> row = i // 10, col = i % 10.
BASE_LAT = 12.9716
BASE_LON = 77.5946
GRID_STEP_LAT = 0.0018
GRID_STEP_LON = 0.0022

# Dataset duration: 30 days of hourly timestamps from a fixed anchor
# (never datetime.now(); reproducibility requirement).
DATASET_DAYS = 30
DAYS = DATASET_DAYS  # alias
FIXED_START = datetime(2024, 1, 1, 0, 0, 0)

# Category mix: exact counts for the 100 assets.
CATEGORY_MIX = {
    "healthy": 70,
    "watch": 15,
    "emerging": 10,
    "critical": 5,
}

# Hero demo asset + its two correlated neighbors. With row-major codes,
# SL-1042 is row 4 / col 1; SL-1041 (row 4 / col 0) and SL-1043
# (row 4 / col 2) are geographically adjacent on the same street segment.
SL_1042_CODE = "SL-1042"
SL_1042_ID_STR = SL_1042_CODE  # alias used by existing tests
NEIGHBORS = ["SL-1041", "SL-1043"]
NEIGHBOR_CODES = NEIGHBORS  # alias

# SL-1042 scripted gradual degradation, applied from DRIFT_START_DAY
# (0-based day index 9 ~= "day 10") through end of window, operating
# hours only. Gradual: no catastrophic failure.
DRIFT_START_DAY_INDEX = 9
POWER_DRIFT_W_PER_DAY = 0.5
BRIGHTNESS_DRIFT_PP_PER_DAY = -0.5
NEIGHBOR_DRIFT_FRACTION = 0.5  # neighbors show weaker correlated drift

# Nighttime / operating hours for streetlights (lamps ON). Hours not in
# this set are off-hours: no readings are generated for them, and drift
# is never applied to them.
ACTIVE_HOUR_START = 18
ACTIVE_HOUR_END = 5
OPERATING_HOURS = frozenset([18, 19, 20, 21, 22, 23, 0, 1, 2, 3, 4, 5])

# Night setback (dimming) window inside operating hours.
SETBACK_HOURS = frozenset([1, 2, 3, 4])

# EAV sensor types stored in Phase 1 sensor_readings.sensor_type.
SENSOR_POWER = "power_watts"
SENSOR_BRIGHTNESS = "brightness_pct"
SENSOR_COMPLAINT = "complaint_received"

# Baseline operating points + plausible physical bounds.
BASE_POWER_W = 52.0
BASE_BRIGHTNESS_PCT = 96.0
POWER_MIN_W = 20.0
POWER_MAX_W = 90.0
BRIGHTNESS_MIN_PCT = 50.0
BRIGHTNESS_MAX_PCT = 100.0

# Complaint events on non-hero assets: small, sparse, deterministic.
OTHER_COMPLAINT_COUNT = 6
