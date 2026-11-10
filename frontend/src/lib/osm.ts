// ---------------------------------------------------------------------------
// Public-map infrastructure layer (additive map feature). OpenStreetMap
// Overpass data is PUBLIC metadata, never telemetry: points are shown with
// neutral markers and an honest source label, and registering one creates
// a coordinate-only asset (no readings, no scores invented).
// ---------------------------------------------------------------------------

export interface InfraPoint {
  osmId: string;
  kind: 'street_lamp' | 'pole';
  label: string;
  lat: number;
  lon: number;
}

export interface RegisteredAsset {
  id: string;
  external_code: string;
  latitude: number | null;
  longitude: number | null;
  infra_type: string | null;
  infra_source: string | null;
  status: string;
}

const OVERPASS_URL = 'https://overpass-api.de/api/interpreter';
// Keep server load polite: never query more than a 5 km half-box, max 100 nodes.
const MAX_HALF_BOX_KM = 5;
const MAX_NODES = 100;

const cache = new Map<string, InfraPoint[]>();

export function clearInfraCache(): void {
  cache.clear();
}

function bbox(lat: number, lon: number, halfKm: number): string {
  // Equirectangular approximation is plenty for a <=5 km demo box.
  const dLat = halfKm / 111.32;
  const dLon = halfKm / (111.32 * Math.max(0.2, Math.cos((lat * Math.PI) / 180)));
  const south = lat - dLat;
  const north = lat + dLat;
  const west = lon - dLon;
  const east = lon + dLon;
  return `${south.toFixed(5)},${west.toFixed(5)},${north.toFixed(5)},${east.toFixed(5)}`;
}

interface OverpassNode {
  type?: string;
  id?: number;
  lat?: number;
  lon?: number;
  tags?: Record<string, string>;
}

function labelFor(tags: Record<string, string>): { kind: InfraPoint['kind']; label: string } | null {
  if (tags['highway'] === 'street_lamp' || tags['power'] === 'street_lamp') {
    return { kind: 'street_lamp', label: 'Street light' };
  }
  if (tags['power'] === 'pole') {
    return { kind: 'pole', label: 'Electric pole' };
  }
  return null;
}

/** Parse an Overpass JSON payload into infra points (pure, unit-tested). */
export function parseInfraResponse(payload: unknown): InfraPoint[] {
  if (!payload || typeof payload !== 'object') return [];
  const elements = (payload as { elements?: unknown }).elements;
  if (!Array.isArray(elements)) return [];
  const out: InfraPoint[] = [];
  for (const el of elements as OverpassNode[]) {
    if (el?.type !== 'node' || typeof el.id !== 'number') continue;
    if (typeof el.lat !== 'number' || typeof el.lon !== 'number') continue;
    const labelled = labelFor(el.tags ?? {});
    if (!labelled) continue;
    out.push({
      osmId: `osm:${el.id}`,
      kind: labelled.kind,
      label: labelled.label,
      lat: el.lat,
      lon: el.lon,
    });
    if (out.length >= MAX_NODES) break;
  }
  return out;
}

/** Fetch public infrastructure around a point (on explicit request only). */
export async function queryInfrastructure(
  lat: number,
  lon: number,
  radiusKm: number | null,
  signal?: AbortSignal,
): Promise<InfraPoint[]> {
  const half = Math.min(radiusKm ?? MAX_HALF_BOX_KM, MAX_HALF_BOX_KM);
  const key = `${lat.toFixed(4)},${lon.toFixed(4)},${half}`;
  const cached = cache.get(key);
  if (cached) return cached;
  const box = bbox(lat, lon, half);
  const ql = `[out:json][timeout:25];(node["highway"="street_lamp"](${box});node["power"="pole"](${box});node["power"="street_lamp"](${box}););out body ${MAX_NODES};`;
  const res = await fetch(OVERPASS_URL, {
    method: 'POST',
    signal,
    headers: { 'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8' },
    body: `data=${encodeURIComponent(ql)}`,
  });
  if (!res.ok) throw new Error(`Infrastructure lookup failed (HTTP ${res.status})`);
  const points = parseInfraResponse(await res.json());
  cache.set(key, points);
  return points;
}

export type TelemetryState = 'seeded' | 'not-connected' | 'simulated';

/**
 * Honest telemetry state derived from API fields (pure, unit-tested):
 * - seeded assets predate registration (no provenance, real demo dataset).
 * - registered assets without risk evidence: telemetry not connected.
 * - registered assets WITH risk evidence: evidence can only be simulated
 *   (physical sensors are never installed by this demo).
 */
export function telemetryState(asset: { infra_source?: string | null; risk_level?: string | null }): TelemetryState {
  if (!asset.infra_source) return 'seeded';
  if (!asset.risk_level) return 'not-connected';
  return 'simulated';
}

export const SIMULATED_LABEL = 'Simulated telemetry — demonstration only';

export interface DemoTelemetryResult {
  status: string;
  asset_external_code: string;
  mode: 'normal' | 'anomalous';
  readings_written: number;
  simulated: boolean;
  warning: string;
}

/** Enable deterministic simulated telemetry for a registered asset. */
export async function enableDemoTelemetry(
  externalCode: string,
  mode: 'normal' | 'anomalous',
): Promise<DemoTelemetryResult> {
  const res = await fetch(`/api/assets/${encodeURIComponent(externalCode)}/demo-telemetry`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mode }),
  });
  if (!res.ok) throw new Error(`Demo telemetry failed (HTTP ${res.status})`);
  return (await res.json()) as DemoTelemetryResult;
}

/** Register a public point via the additive backend endpoint. */
export async function registerInfraAsset(point: InfraPoint): Promise<RegisteredAsset> {
  const res = await fetch('/api/assets/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      latitude: point.lat,
      longitude: point.lon,
      infra_type: point.label,
      infra_source: point.osmId,
    }),
  });
  if (res.status === 409) throw new Error('already registered');
  if (!res.ok) throw new Error(`Registration failed (HTTP ${res.status})`);
  return (await res.json()) as RegisteredAsset;
}
