import { describe, it, expect, vi, afterEach } from 'vitest'
import {
  areaSummary,
  bandOf,
  clearGeocodeCache,
  haversineKm,
  nearbyAssets,
  searchLocations,
} from '../lib/geo'
import type { MapAsset } from '../lib/types'

function asset(code: string, lat: number, lon: number, risk = 'LOW', score = 0.1): MapAsset {
  return {
    asset_id: `id-${code}`, external_code: code, latitude: lat, longitude: lon,
    status: 'healthy', fusion_status: 'NORMAL', fusion_score: score,
    risk_level: risk, risk_score: score,
  }
}

describe('geo helpers (pure, real-data math)', () => {
  it('computes haversine distance accurately', () => {
    // ~1.11 km per 0.01 degrees latitude.
    expect(haversineKm(12.9716, 77.5946, 12.9816, 77.5946)).toBeCloseTo(1.11, 1)
    expect(haversineKm(12.5, 77.5, 12.5, 77.5)).toBe(0)
  })

  it('bands assets by live risk level with seed fallback', () => {
    expect(bandOf(asset('A', 0, 0, 'CRITICAL', 0.9))).toBe('CRITICAL')
    expect(bandOf(asset('B', 0, 0, 'LOW', 0.1))).toBe('LOW')
    expect(bandOf({ ...asset('C', 0, 0), risk_level: null, fusion_status: 'EMERGING' })).toBe('HIGH')
  })

  it('finds nearby assets sorted nearest-first within radius', () => {
    const assets = [
      asset('FAR', 13.5, 77.9, 'LOW', 0.1),
      asset('NEAR', 12.9726, 77.5956, 'HIGH', 0.6),
      asset('MID', 13.0, 77.6, 'MEDIUM', 0.4),
    ]
    const near = nearbyAssets(assets, 12.9716, 77.5946, 10)
    expect(near.map((n) => n.asset.external_code)).toEqual(['NEAR', 'MID'])
    expect(near[0].distanceKm).toBeLessThan(1)
    expect(nearbyAssets(assets, 12.9716, 77.5946, null)).toHaveLength(3)
    expect(nearbyAssets(assets, 12.9716, 77.5946, 0.01)).toHaveLength(0)
  })

  it('aggregates area summaries from actual nearby data', () => {
    const assets = [
      asset('C1', 12.972, 77.595, 'CRITICAL', 0.92),
      asset('H1', 12.973, 77.596, 'HIGH', 0.65),
      asset('L1', 12.974, 77.597, 'LOW', 0.08),
    ]
    const s = areaSummary(nearbyAssets(assets, 12.9716, 77.5946, 10))
    expect(s.total).toBe(3)
    expect(s.byBand).toMatchObject({ CRITICAL: 1, HIGH: 1, LOW: 1, MEDIUM: 0 })
    expect(s.overall).toBe('CRITICAL')
    expect(s.score).toBe(92)
    const empty = areaSummary([])
    expect(empty).toMatchObject({ total: 0, overall: null, score: null })
  })
})

describe('nominatim search (mocked fetch)', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    clearGeocodeCache()
  })

  it('parses results, caches, and rejects short queries', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve([
        { display_name: 'Noida Sector 62, Uttar Pradesh', name: 'Noida Sector 62', lat: '28.614', lon: '77.368' },
        { display_name: 'broken', lat: 'NaN', lon: 'NaN' },
      ]),
    })
    vi.stubGlobal('fetch', fetchMock)
    const first = await searchLocations('Noida Sector 62')
    expect(first).toHaveLength(1)
    expect(first[0]).toMatchObject({ name: 'Noida Sector 62', lat: 28.614, lon: 77.368 })
    const second = await searchLocations('Noida Sector 62')
    expect(second).toEqual(first)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    await expect(searchLocations('No')).resolves.toEqual([])
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('throws a safe error on geocoding failure', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 503 }))
    await expect(searchLocations('Delhi')).rejects.toThrow('Geocoding failed')
  })
})
