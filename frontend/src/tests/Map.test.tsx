import { render, screen, waitFor, within, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, afterEach } from 'vitest'
import Map from '../pages/Map'
import type { MapAsset } from '../lib/types'

function asset(code: string, status = 'NORMAL', lat = 12.9716, lon = 77.5946): MapAsset {
  return {
    asset_id: `id-${code}`, external_code: code, latitude: lat, longitude: lon,
    status: 'healthy', fusion_status: status, fusion_score: 0.1,
    risk_level: 'LOW', risk_score: 0.1,
  }
}

function mockMapApi(assets: MapAsset[]) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ assets, total: assets.length }) }),
  )
}

describe('Map page (mocked /api/map)', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders one marker per API asset (dynamic count)', async () => {
    const assets = [
      asset('SL-1001'), asset('SL-1002', 'WATCH', 12.972, 77.595),
      asset('SL-1042', 'CRITICAL', 12.9788, 77.5968), asset('SL-1100', 'EMERGING', 12.988, 77.614),
    ]
    mockMapApi(assets)
    const { container } = render(<Map />)
    await waitFor(() => {
      expect(container.querySelectorAll('path.leaflet-interactive').length).toBe(assets.length)
    })
    expect(screen.getByText(/4 streetlights plotted live/)).toBeInTheDocument()
  })

  it('scales marker count with the API response (no hardcoded count)', async () => {
    const assets = [asset('SL-2001'), asset('SL-2002', 'CRITICAL', 12.98, 77.6)]
    mockMapApi(assets)
    const { container } = render(<Map />)
    await waitFor(() => {
      expect(container.querySelectorAll('path.leaflet-interactive').length).toBe(2)
    })
  })

  it('locates SL-1042 from API data and links its popup to the asset route', async () => {
    const assets = [asset('SL-1001'), asset('SL-1042', 'CRITICAL', 12.9788, 77.5968)]
    mockMapApi(assets)
    const { container } = render(<Map />)
    await waitFor(() => {
      expect(container.querySelectorAll('path.leaflet-interactive').length).toBe(2)
    })
    // Focus badge discovered from data (not hardcoded coordinates).
    expect(screen.getByLabelText(/Open focus asset SL-1042/)).toBeInTheDocument()
    // Open each marker popup (Leaflet shows one at a time) and verify the
    // dynamic detail link inside.
    const seen = new Set<string>()
    const paths = Array.from(container.querySelectorAll('path.leaflet-interactive'))
    for (const p of paths) {
      fireEvent.click(p)
      await waitFor(() => {
        expect(container.querySelector('.leaflet-popup-content a')).toBeInTheDocument()
      })
      const href = container.querySelector('.leaflet-popup-content a')?.getAttribute('href')
      if (href) seen.add(href)
    }
    expect(seen).toContain('#/asset/SL-1042')
    expect(seen).toContain('#/asset/SL-1001')
  })

  it('falls back gracefully when SL-1042 is absent', async () => {
    mockMapApi([asset('SL-3001'), asset('SL-3002')])
    const { container } = render(<Map />)
    await waitFor(() => {
      expect(container.querySelectorAll('path.leaflet-interactive').length).toBe(2)
    })
    expect(screen.queryByLabelText(/Open focus asset/)).toBeNull()
  })

  it('skips assets with missing coordinates without crashing', async () => {
    const bad = { ...asset('SL-4001'), latitude: null, longitude: null }
    mockMapApi([bad, asset('SL-4002')])
    const { container } = render(<Map />)
    await waitFor(() => {
      expect(container.querySelectorAll('path.leaflet-interactive').length).toBe(1)
    })
    expect(screen.getByText(/1 of 2 assets plotted/)).toBeInTheDocument()
  })

  it('shows legend, handles empty and error states', async () => {
    mockMapApi([])
    const { rerender } = render(<Map />)
    await waitFor(() => {
      expect(screen.getByText(/No mappable assets/)).toBeInTheDocument()
    })
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    rerender(<Map key="error-case" />)
    await waitFor(() => {
      expect(screen.getByText(/Unable to connect to SilentSignal backend/i)).toBeInTheDocument()
    })
  })

  it('legend matches the UI status vocabulary and colors', async () => {
    mockMapApi([asset('SL-5001')])
    render(<Map />)
    const legend = await screen.findByLabelText('Map legend')
    for (const label of ['Healthy', 'Watch', 'Emerging', 'Critical']) {
      expect(within(legend).getByText(label)).toBeInTheDocument()
    }
  })
})
