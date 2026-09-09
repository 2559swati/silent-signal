import { describe, it, expect } from 'vitest'
import { healthyCount, lowRiskShare, sectorLabel, signalMeans, topRisk } from '../lib/ops'
import type { FleetEntry } from '../lib/fleet'
import type { RiskLevel } from '../lib/types'

function entry(code: string, status: FleetEntry['asset']['status'], riskLevel?: RiskLevel, riskScore = 0.1, fusionScores?: number[]): FleetEntry {
  return {
    asset: { id: code, external_code: code, criticality: 2, public_exposure: 2, status },
    risk: riskLevel
      ? {
          asset_id: code, asset_external_code: code, day: '2024-01-30', anomaly_score: 0.1,
          fusion_score: 0.1, smoothed_fusion_score: 0.1, persistence_score: 0,
          risk_score: riskScore, risk_level: riskLevel,
          model_version: 'risk_v1',
        }
      : null,
    fusion: fusionScores
      ? {
          asset_id: code, asset_external_code: code, day: '2024-01-30',
          power_score: fusionScores[0], brightness_score: fusionScores[1],
          temperature_score: fusionScores[2], maintenance_score: fusionScores[3],
          neighbor_score: fusionScores[4], fusion_score: 0.1, smoothed_fusion_score: 0.1,
          status: 'NORMAL', model_version: 'fusion_v1',
        }
      : null,
  } as FleetEntry
}

describe('ops helpers (pure, real-data derivations)', () => {
  it('labels schematic sectors from asset codes', () => {
    expect(sectorLabel('SL-1042')).toBe('Sector R5·C2')
    expect(sectorLabel('SL-1001')).toBe('Sector R1·C1')
    expect(sectorLabel('NOPE')).toBe('Off-grid')
  })

  it('computes low-risk share and healthy counts', () => {
    const entries = [
      entry('SL-1001', 'healthy', 'LOW', 0.1),
      entry('SL-1042', 'emerging', 'CRITICAL', 0.9),
      entry('SL-1002', 'healthy'),
    ]
    expect(lowRiskShare(entries)).toBeCloseTo(0.5)
    expect(healthyCount(entries)).toBe(2)
    expect(lowRiskShare([])).toBe(0)
  })

  it('averages fusion signals across scored assets only', () => {
    const entries = [
      entry('SL-1001', 'healthy', 'LOW', 0.1, [0.2, 0.4, 0.6, 0.8, 1.0]),
      entry('SL-1002', 'healthy'),
    ]
    const means = signalMeans(entries)
    expect(means).toHaveLength(5)
    expect(means[0]).toMatchObject({ signal: 'Power', mean: 0.2, n: 1 })
    expect(signalMeans([]).every((m) => m.mean === 0)).toBe(true)
  })

  it('ranks top risk without fetching', () => {
    const entries = [
      entry('SL-1001', 'healthy', 'LOW', 0.1),
      entry('SL-1042', 'emerging', 'CRITICAL', 0.9),
      entry('SL-1043', 'watch', 'HIGH', 0.6),
    ]
    expect(topRisk(entries, 2).map((e) => e.asset.external_code)).toEqual(['SL-1042', 'SL-1043'])
  })
})
