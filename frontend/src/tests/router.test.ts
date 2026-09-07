import { describe, it, expect } from 'vitest'
import { parseHash, routeHref } from '../lib/router'

describe('hash router', () => {
  it('parses known routes', () => {
    expect(parseHash('#/')).toEqual({ name: 'dashboard' })
    expect(parseHash('#/assets')).toEqual({ name: 'assets' })
    expect(parseHash('#/asset/SL-1042')).toEqual({ name: 'asset', code: 'SL-1042' })
    expect(parseHash('#/risk')).toEqual({ name: 'risk' })
    expect(parseHash('#/explanations')).toEqual({ name: 'explanations' })
    expect(parseHash('#/actions')).toEqual({ name: 'actions' })
    expect(parseHash('#/settings')).toEqual({ name: 'settings' })
  })

  it('falls back to dashboard for unknown hashes', () => {
    expect(parseHash('#/nope')).toEqual({ name: 'dashboard' })
    expect(parseHash('')).toEqual({ name: 'dashboard' })
  })

  it('round-trips routes through hrefs', () => {
    expect(routeHref({ name: 'asset', code: 'SL-1042' })).toBe('#/asset/SL-1042')
    expect(parseHash(routeHref({ name: 'asset', code: 'SL-1042' }))).toEqual({
      name: 'asset',
      code: 'SL-1042',
    })
    expect(parseHash(routeHref({ name: 'risk' }))).toEqual({ name: 'risk' })
  })
})
