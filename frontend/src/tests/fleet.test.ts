import { describe, it, expect } from 'vitest'
import { computeFleetStats, formatPct, formatScore, gridPosition, riskRank } from '../lib/fleet'
import type { FleetEntry } from '../lib/fleet'

function entry(code: string, level: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL', score: number, fusion: 'NORMAL' | 'WATCH' | 'EMERGING' | 'CRITICAL'): FleetEntry {
  return {
    asset: { id: code, external_code: code, criticality: 3, public_exposure: 3, status: 'healthy' },
    risk: {
      asset_id: code, asset_external_code: code, day: '2024-01-30', anomaly_score: 0.5,
      fusion_score: score, smoothed_fusion_score: score, persistence_score: 0,
      risk_score: score, risk_level: level, model_version: 'risk_v1',
    },
    fusion: {
      asset_id: code, asset_external_code: code, day: '2024-01-30', power_score: 0,
      brightness_score: 0, temperature_score: 0, maintenance_score: 0, neighbor_score: 0,
      fusion_score: score, smoothed_fusion_score: score, status: fusion, model_version: 'fusion_v1',
    },
  }
}

describe('fleet helpers', () => {
  it('derives the documented 10x10 grid position from asset codes', () => {
    expect(gridPosition('SL-1001')).toEqual({ row: 0, col: 0 })
    expect(gridPosition('SL-1042')).toEqual({ row: 4, col: 1 })
    expect(gridPosition('SL-1100')).toEqual({ row: 9, col: 9 })
    expect(gridPosition('NOPE')).toBeNull()
    expect(gridPosition('SL-9999')).toBeNull()
  })

  it('ranks risk levels for sorting', () => {
    expect(riskRank('CRITICAL')).toBeGreaterThan(riskRank('HIGH'))
    expect(riskRank('HIGH')).toBeGreaterThan(riskRank('MEDIUM'))
    expect(riskRank('MEDIUM')).toBeGreaterThan(riskRank('LOW'))
    expect(riskRank(null)).toBe(-1)
  })

  it('computes fleet stats from live-shaped entries', () => {
    const entries = [
      entry('SL-1', 'CRITICAL', 0.9, 'CRITICAL'),
      entry('SL-2', 'HIGH', 0.6, 'EMERGING'),
      entry('SL-3', 'MEDIUM', 0.4, 'WATCH'),
      entry('SL-4', 'LOW', 0.1, 'NORMAL'),
    ]
    const stats = computeFleetStats(entries, 100)
    expect(stats).toMatchObject({ total: 100, critical: 1, high: 1, medium: 1, low: 1, emergingWatch: 2, withRisk: 4 })
  })

  it('formats scores', () => {
    expect(formatPct(0.91832)).toBe('91.8%')
    expect(formatScore(0.886207)).toBe('0.886')
  })
})
