import { describe, it, expect, vi, afterEach } from 'vitest'
import {
  SIMULATED_LABEL,
  clearInfraCache,
  enableDemoTelemetry,
  parseInfraResponse,
  queryInfrastructure,
  registerInfraAsset,
  telemetryState,
} from '../lib/osm'

const OVERPASS_OK = {
  elements: [
    { type: 'node', id: 101, lat: 21.19, lon: 81.35, tags: { highway: 'street_lamp' } },
    { type: 'node', id: 102, lat: 21.2, lon: 81.36, tags: { power: 'pole' } },
    { type: 'node', id: 103, lat: 21.21, lon: 81.37, tags: { power: 'street_lamp' } },
    { type: 'node', id: 104, lat: 21.22, lon: 81.38, tags: { amenity: 'cafe' } },
    { type: 'way', id: 105 },
    { type: 'node', id: 106, tags: { power: 'pole' } },
  ],
}

describe('osm helpers (mocked network)', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    clearInfraCache()
  })

  it('parses only lamp/pole nodes with valid coordinates', () => {
    const points = parseInfraResponse(OVERPASS_OK)
    expect(points.map((p) => p.osmId)).toEqual(['osm:101', 'osm:102', 'osm:103'])
    expect(points[0]).toMatchObject({ label: 'Street light', lat: 21.19, lon: 81.35 })
    expect(points[1]).toMatchObject({ label: 'Electric pole' })
  })

  it('returns empty for empty/invalid payloads', () => {
    expect(parseInfraResponse({ elements: [] })).toEqual([])
    expect(parseInfraResponse({})).toEqual([])
    expect(parseInfraResponse(null)).toEqual([])
  })

  it('queries overpass once per point and caches', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(OVERPASS_OK) })
    vi.stubGlobal('fetch', fetchMock)
    const first = await queryInfrastructure(21.19, 81.35, 10)
    expect(first).toHaveLength(3)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toContain('overpass-api.de')
    expect(String(init.body)).toContain('street_lamp')
    await queryInfrastructure(21.19, 81.35, 10)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('surfaces overpass failures without crashing', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 504 }))
    await expect(queryInfrastructure(21.19, 81.35, 5)).rejects.toThrow('HTTP 504')
  })

  it('labels telemetry states honestly', () => {
    expect(telemetryState({})).toBe('seeded')
    expect(telemetryState({ infra_source: 'osm:1' })).toBe('not-connected')
    expect(telemetryState({ infra_source: 'osm:1', risk_level: 'LOW' })).toBe('simulated')
    expect(telemetryState({ infra_source: 'osm:1', risk_level: 'CRITICAL' })).toBe('simulated')
    expect(SIMULATED_LABEL).toMatch(/Simulated telemetry/)
  })

  it('enables demo telemetry with an explicit simulated flag', async () => {
    const payload = {
      status: 'ok', asset_external_code: 'SL-EXT-OSM-101', mode: 'anomalous',
      readings_written: 720, simulated: true, warning: 'Simulated telemetry',
    }
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(payload) })
    vi.stubGlobal('fetch', fetchMock)
    const res = await enableDemoTelemetry('SL-EXT-OSM-101', 'anomalous')
    expect(res.simulated).toBe(true)
    expect(res.readings_written).toBe(720)
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toContain('/demo-telemetry')
    expect(String(init.body)).toContain('anomalous')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 400 }))
    await expect(enableDemoTelemetry('SL-1001', 'normal')).rejects.toThrow('HTTP 400')
  })

  it('registers a point and maps duplicate registration', async () => {
    const created = {
      id: 'uuid-1', external_code: 'SL-EXT-OSM-101', latitude: 21.19, longitude: 81.35,
      infra_type: 'Street light', infra_source: 'osm:101', status: 'watch',
    }
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, status: 201, json: () => Promise.resolve(created) })
      .mockResolvedValueOnce({ ok: false, status: 409 })
    vi.stubGlobal('fetch', fetchMock)
    await expect(
      registerInfraAsset({ osmId: 'osm:101', kind: 'street_lamp', label: 'Street light', lat: 21.19, lon: 81.35 }),
    ).resolves.toMatchObject({ external_code: 'SL-EXT-OSM-101' })
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(init.method).toBe('POST')
    expect(String(init.body)).toContain('osm:101')
    await expect(
      registerInfraAsset({ osmId: 'osm:101', kind: 'street_lamp', label: 'Street light', lat: 21.19, lon: 81.35 }),
    ).rejects.toThrow('already registered')
  })
})
