# SilentSignal Real-World Infrastructure Demo (Hackathon Flow)

End-to-end judge path: **location → public infrastructure → register →
simulated telemetry → existing anomaly/risk pipeline → alert/recommendation.**
No phase of the existing pipeline was changed for this flow.

## 1. Location search

Map page search box → **Nominatim** (`lib/geo.ts`), debounced 400 ms,
minimum 3 characters, results cached in memory, abortable. Selecting a
result flies the Leaflet map there (existing map, OSM tiles). "Use my
location" uses browser geolocation on click only; coordinates stay in
memory, never stored or logged. OSM is **never** queried automatically.

## 2. OSM infrastructure discovery

Explicit **"Load public infrastructure"** button → **Overpass API**
(`lib/osm.ts`, `power=pole`, `highway/power=street_lamp`) with a ≤5 km
half-box cap, 100-node cap, per-point cache. Markers are neutral gray
squares, popups show type, lat/lon, `Source: OpenStreetMap (osm:<id>)`.
Empty areas honestly report no mapped infrastructure. Overpass outages
degrade to a warning; the SilentSignal map keeps working.

## 3. Registration

Popup → **Register as SilentSignal Asset** → `POST /api/assets/register`
(`backend/app/api/assets.py`). Backend assigns UUID + `SL-EXT-*` code,
neutral defaults (criticality/exposure 3, status `watch`), stores real
lat/lon + `infra_source=osm:<id>` (unique: duplicates get HTTP 409).
**No telemetry is created** — analysis endpoints 404 until readings exist,
and the UI reads *"Telemetry not connected."*

## 4. Why no physical sensors are needed

The demo evaluates the **analysis pipeline**, not sensing hardware. A
registered asset carries coordinates + provenance only. For the demo it can
opt into deterministic **simulated** readings (below); nothing ever claims
a sensor was installed.

## 5. Simulated telemetry

Popup → **Simulate normal / Simulate anomaly** → tries
`POST /api/assets/{code}/demo-telemetry` (`app/services/demo_telemetry.py`):
deterministic readings (seeded by asset code + mode) reusing Phase 2
physics — operating hours, setback dimming, 52 W / 96 % baselines, physical
bounds — 720 rows over the existing 30-day window, then the **existing**
`compute_all_*` pipeline runs (identical calls to `/api/demo/reset`).
Every response carries `simulated: true` plus a warning; the UI labels it
*"Simulated telemetry — demonstration only"* everywhere. Seeded assets
reject demo telemetry (HTTP 400) so the frozen dataset is never disturbed.

Plausible channels: power draw, brightness output (the project's two
metered signals), with gradual drift in anomalous mode. No random anomalies:
identical input always yields identical rows (re-enabling is idempotent).

## 6. Triggering demo conditions

- **Normal:** Simulate normal → fusion NORMAL, risk LOW (monitoring).
- **Anomalous:** Simulate anomaly → 2× hero-rate drift from day 9 →
  fusion EMERGING/CRITICAL, risk HIGH/CRITICAL, `EMERGING_ANOMALY` alert,
  urgent/prioritized inspection recommendation — all through unchanged
  Phase 4–9 thresholds.

## 7. How the pipeline processes the evidence

Written readings are ordinary `sensor_readings` rows, so ML anomaly
(IsolationForest), 5-signal fusion, EMA smoothing, persistence, risk,
explanations, recommendations, and alerts all run exactly as for seeded
assets. The only demo-specific code is the clearly-marked writer +
endpoint; no formula, weight, or threshold was touched.

## 8. Real vs simulated (judge transparency)

> Public infrastructure locations are sourced from OpenStreetMap.
> Telemetry shown in this hackathon demo is simulated because physical
> sensors are not connected.

| Real | Simulated |
|---|---|
| Map tiles, Nominatim search, Overpass points | Sensor readings for registered assets |
| Registration identity/coords/provenance | Fusion/risk/alert values *derived from* simulated readings (via the real pipeline) |
| Seeded 100-asset fleet + SL-1042 scenario | — |

Never claimed: "live sensor", "real sensor", "sensor installed".

## 9. Limitations

- Overpass/Nominatim are free public services: rate limits and gaps in
  mapped infrastructure are expected; the app degrades gracefully.
- Fleet schematic coordinates (seeded grid) are demo layout, not GPS.
- `POST /api/demo/reset` wipes registered assets + simulated readings
  (existing reset semantics); re-register afterwards.
