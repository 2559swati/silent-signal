import type { MapAsset } from './types';

// ---------------------------------------------------------------------------
// Area-risk intelligence helpers (Phase 11). Pure functions over the EXISTING
// Phase 10 /api/map dataset -- no fake assets, no invented coordinates.
// Distances are real haversine computations on the API-returned lat/lon.
// ---------------------------------------------------------------------------

export interface GeocodeResult {
  name: string;
  displayName: string;
  lat: number;
  lon: number;
}

export type RiskBand = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';

export const RISK_BANDS: RiskBand[] = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'];

export const RADII_KM = [1, 5, 10, 25] as const;

/** Great-circle distance in kilometres between two WGS84 points. */
export function haversineKm(aLat: number, aLon: number, bLat: number, bLon: number): number {
  const rad = (d: number): number => (d * Math.PI) / 180;
  const earthKm = 6371;
  const dLat = rad(bLat - aLat);
  const dLon = rad(bLon - aLon);
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(rad(aLat)) * Math.cos(rad(bLat)) * Math.sin(dLon / 2) ** 2;
  return 2 * earthKm * Math.asin(Math.sqrt(h));
}

/** Risk band for a map asset: live risk level, falling back to seed status. */
export function bandOf(asset: MapAsset): RiskBand {
  const level = (asset.risk_level ?? '').toUpperCase();
  if (level === 'CRITICAL' || level === 'HIGH' || level === 'MEDIUM' || level === 'LOW') {
    return level;
  }
  const seed = (asset.fusion_status ?? asset.status ?? '').toUpperCase();
  if (seed === 'CRITICAL') return 'CRITICAL';
  if (seed === 'EMERGING' || seed === 'HIGH') return 'HIGH';
  if (seed === 'WATCH' || seed === 'MEDIUM') return 'MEDIUM';
  return 'LOW';
}

export interface NearbyAsset {
  asset: MapAsset;
  distanceKm: number;
  band: RiskBand;
}

/** Assets within radiusKm of a point, sorted nearest-first. radiusKm null = all. */
export function nearbyAssets(
  assets: MapAsset[],
  lat: number,
  lon: number,
  radiusKm: number | null,
): NearbyAsset[] {
  const out: NearbyAsset[] = [];
  for (const asset of assets) {
    if (typeof asset.latitude !== 'number' || typeof asset.longitude !== 'number') continue;
    const distanceKm = haversineKm(lat, lon, asset.latitude, asset.longitude);
    if (radiusKm !== null && distanceKm > radiusKm) continue;
    out.push({ asset, distanceKm, band: bandOf(asset) });
  }
  out.sort((a, b) => a.distanceKm - b.distanceKm);
  return out;
}

export interface AreaSummary {
  total: number;
  byBand: Record<RiskBand, number>;
  overall: RiskBand | null;
  score: number | null;
}

/** Aggregate an area summary purely from the nearby list (no hardcoding). */
export function areaSummary(nearby: NearbyAsset[]): AreaSummary {
  const byBand: Record<RiskBand, number> = { CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0 };
  let maxScore: number | null = null;
  for (const n of nearby) {
    byBand[n.band] += 1;
    if (typeof n.asset.risk_score === 'number') {
      maxScore = maxScore === null ? n.asset.risk_score : Math.max(maxScore, n.asset.risk_score);
    }
  }
  const overall =
    byBand.CRITICAL > 0 ? 'CRITICAL'
    : byBand.HIGH > 0 ? 'HIGH'
    : byBand.MEDIUM > 0 ? 'MEDIUM'
    : nearby.length > 0 ? 'LOW'
    : null;
  return {
    total: nearby.length,
    byBand,
    overall,
    score: maxScore === null ? null : Math.round(maxScore * 100),
  };
}

// ---------------------------------------------------------------------------
// Nominatim geocoding (OpenStreetMap-compatible, no API key, no new deps).
// Polite usage: debounced by callers, limit 5, in-memory cache, abortable.
// ---------------------------------------------------------------------------

const geocodeCache = new Map<string, GeocodeResult[]>();

export function clearGeocodeCache(): void {
  geocodeCache.clear();
}

interface NominatimItem {
  display_name?: string;
  name?: string;
  lat?: string;
  lon?: string;
}

export async function searchLocations(query: string, signal?: AbortSignal): Promise<GeocodeResult[]> {
  const key = query.trim().toLowerCase();
  if (key.length < 3) return [];
  const cached = geocodeCache.get(key);
  if (cached) return cached;
  const url = `https://nominatim.openstreetmap.org/search?format=jsonv2&limit=5&q=${encodeURIComponent(query.trim())}`;
  const res = await fetch(url, {
    signal,
    headers: { Accept: 'application/json' },
  });
  if (!res.ok) throw new Error(`Geocoding failed (HTTP ${res.status})`);
  const items = (await res.json()) as NominatimItem[];
  const out: GeocodeResult[] = [];
  for (const item of items ?? []) {
    const lat = Number(item.lat);
    const lon = Number(item.lon);
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) continue;
    out.push({
      name: item.name || (item.display_name ?? '').split(',')[0] || query.trim(),
      displayName: item.display_name ?? query.trim(),
      lat,
      lon,
    });
  }
  geocodeCache.set(key, out);
  return out;
}
