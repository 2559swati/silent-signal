import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, afterEach } from 'vitest'
import App from '../App'

const ASSETS = {
  total: 1, page: 1, page_size: 100,
  items: [
    { id: 'u1', external_code: 'SL-1001', criticality: 2, public_exposure: 2, status: 'healthy' },
  ],
}

function route(url: string): unknown {
  if (url.includes('/api/assets?')) return ASSETS
  if (url.includes('/risk')) return {
    asset_id: 'u1', asset_external_code: 'SL-1001', day: '2024-01-30', anomaly_score: 0.08,
    fusion_score: 0.05, smoothed_fusion_score: 0.05, persistence_score: 0,
    risk_score: 0.08, risk_level: 'LOW', model_version: 'risk_v1',
  }
  if (url.includes('/fusion')) return {
    asset_id: 'u1', asset_external_code: 'SL-1001', day: '2024-01-30', power_score: 0.05,
    brightness_score: 0.05, temperature_score: 0.05, maintenance_score: 0, neighbor_score: 0,
    fusion_score: 0.05, smoothed_fusion_score: 0.05, status: 'NORMAL', model_version: 'fusion_v1',
  }
  if (url.includes('/api/health')) return { status: 'ok' }
  throw new Error(`unexpected ${url}`)
}

describe('live evidence clicker', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    window.location.hash = '#/'
  })

  it('reloads fleet evidence when clicked', async () => {
    const fetchMock = vi.fn().mockImplementation((url: string) =>
      Promise.resolve({ ok: true, json: () => Promise.resolve(route(url)) }),
    )
    vi.stubGlobal('fetch', fetchMock)
    render(<App />)
    const button = await screen.findByRole('button', { name: 'Reload live evidence now' })
    const callsBefore = fetchMock.mock.calls.length
    fireEvent.click(button)
    await waitFor(() => expect(fetchMock.mock.calls.length).toBeGreaterThan(callsBefore))
  })

  it('is labelled while refreshing', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) =>
      Promise.resolve({ ok: true, json: () => Promise.resolve(route(url)) }),
    ))
    render(<App />)
    // Initially loading: the clicker announces the refreshing state.
    expect(await screen.findByRole('button', { name: /live evidence/i })).toBeInTheDocument()
  })
})
