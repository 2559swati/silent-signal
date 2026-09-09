import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, afterEach } from 'vitest'
import Security from '../pages/Security'

const DEMO_STATUS = { mode: 'demo', healthy: true, description: 'Demo TEE provider' }
const DEMO_ATTESTATION = { attested: false, pcr0: null }

function mockSecurity() {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((url: string) => {
      if (url.includes('/api/security/tee-status')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(DEMO_STATUS) })
      }
      if (url.includes('/api/security/attestation')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(DEMO_ATTESTATION) })
      }
      throw new Error(`unexpected ${url}`)
    }),
  )
}

const FORBIDDEN = ['TEE Verified', 'Hardware Attested', 'Secure Enclave Verified', 'Trusted Hardware']

describe('Security page (demo provider)', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders the DEMO MODE badge when the backend reports mode demo', async () => {
    mockSecurity()
    render(<Security />)
    const badge = await screen.findByRole('alert', { name: /demo mode warning/i })
    expect(badge).toBeInTheDocument()
    expect(withinBadge(badge)).toContain('DEMO MODE')
    expect(screen.getByText(/NOT ATTESTED/)).toBeInTheDocument()
  })

  it('never implies real hardware-backed verification in demo mode', async () => {
    mockSecurity()
    const { container } = render(<Security />)
    await screen.findByRole('alert', { name: /demo mode warning/i })
    const text = container.textContent ?? ''
    for (const phrase of FORBIDDEN) {
      expect(text).not.toContain(phrase)
    }
  })

  it('surfaces provider status and attestation state from the API', async () => {
    mockSecurity()
    render(<Security />)
    await waitFor(() => expect(screen.getByText('demo')).toBeInTheDocument())
    expect(screen.getByText('null')).toBeInTheDocument()
  })
})

function withinBadge(badge: HTMLElement): string {
  return badge.textContent ?? ''
}
