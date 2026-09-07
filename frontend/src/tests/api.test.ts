import { describe, it, expect, vi, afterEach } from 'vitest'
import { ApiError, api, isNotFound, isOffline } from '../lib/api'

describe('api client', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('classifies errors', () => {
    expect(isNotFound(new ApiError(404, 'nope'))).toBe(true)
    expect(isNotFound(new ApiError(500, 'err'))).toBe(false)
    expect(isOffline(new ApiError(0, 'fetch failed'))).toBe(true)
    expect(isOffline(new ApiError(200, 'ok'))).toBe(false)
  })

  it('builds asset-scoped URLs and parses JSON', async () => {
    const payload = { status: 'ok' }
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(payload),
    })
    vi.stubGlobal('fetch', fetchMock)
    await expect(api.health()).resolves.toEqual(payload)
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringMatching(/\/api\/health$/),
      expect.objectContaining({}),
    )
  })

  it('encodes asset identifiers in paths', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({}) })
    vi.stubGlobal('fetch', fetchMock)
    await api.risk('SL-1042')
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringMatching(/\/api\/assets\/SL-1042\/risk$/),
      expect.objectContaining({}),
    )
  })

  it('throws ApiError with backend detail on failure', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      statusText: 'Not Found',
      json: () => Promise.resolve({ detail: 'Asset not found' }),
    })
    vi.stubGlobal('fetch', fetchMock)
    const err = await api.fusion('NOPE').catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect((err as ApiError).status).toBe(404)
    expect((err as ApiError).message).toBe('Asset not found')
  })

  it('throws status-0 ApiError when the backend is unreachable', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    const err = await api.health().catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect((err as ApiError).status).toBe(0)
    expect(isOffline(err)).toBe(true)
  })
})
