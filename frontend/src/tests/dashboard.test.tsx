import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, afterEach } from 'vitest'
import App from '../App'

function makeRisk(code: string, level: 'LOW' | 'CRITICAL', score: number) {
  return {
    asset_id: code, asset_external_code: code, day: '2024-01-30', anomaly_score: score,
    fusion_score: score, smoothed_fusion_score: score, persistence_score: score,
    risk_score: score, risk_level: level, model_version: 'risk_v1',
  }
}

function makeFusion(code: string, status: 'NORMAL' | 'CRITICAL', score: number) {
  return {
    asset_id: code, asset_external_code: code, day: '2024-01-30', power_score: score,
    brightness_score: score, temperature_score: score, maintenance_score: 0, neighbor_score: 0,
    fusion_score: score, smoothed_fusion_score: score, status, model_version: 'fusion_v1',
  }
}

const ASSETS = {
  total: 3, page: 1, page_size: 100,
  items: [
    { id: 'u1', external_code: 'SL-1042', criticality: 3, public_exposure: 3, status: 'emerging' },
    { id: 'u2', external_code: 'SL-1001', criticality: 2, public_exposure: 2, status: 'healthy' },
    { id: 'u3', external_code: 'SL-1002', criticality: 2, public_exposure: 2, status: 'healthy' },
  ],
}

function route(url: string): unknown {
  if (url.includes('/api/assets?')) return ASSETS
  if (url.includes('/SL-1042/risk')) return makeRisk('SL-1042', 'CRITICAL', 0.918)
  if (url.includes('/SL-1042/fusion')) return makeFusion('SL-1042', 'CRITICAL', 0.886)
  if (url.includes('/risk')) return makeRisk('X', 'LOW', 0.08)
  if (url.includes('/fusion')) return makeFusion('X', 'NORMAL', 0.05)
  if (url.includes('/api/health')) return { status: 'ok' }
  throw new Error(`unexpected ${url}`)
}

describe('dashboard integration (mocked API, live shapes)', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    window.location.hash = '#/'
  })

  it('renders live fleet KPIs, pipeline and attention list', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) =>
      Promise.resolve({ ok: true, json: () => Promise.resolve(route(url)) }),
    ))
    render(<App />)
    await waitFor(() => expect(screen.getByText('SL-1042')).toBeInTheDocument())
    expect(screen.getByText('TOTAL ASSETS')).toBeInTheDocument()
    expect(screen.getByText('The SilentSignal pipeline')).toBeInTheDocument()
    expect(screen.getByText('Streetlight network')).toBeInTheDocument()
    expect(screen.getByText('Assets requiring attention')).toBeInTheDocument()
  })

  it('shows the backend-offline state when fetch fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    render(<App />)
    await waitFor(() => {
      const matches = screen.getAllByText(/Unable to connect to SilentSignal backend/i)
      expect(matches.length).toBeGreaterThanOrEqual(1)
    })
  })
})
