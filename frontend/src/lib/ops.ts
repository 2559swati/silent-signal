import { gridPosition, type FleetEntry } from './fleet';

/**
 * Schematic sector label derived from the asset code's documented 10x10
 * grid position (e.g. SL-1042 -> "Sector R4·C2"). Presentation-only:
 * the grid is explicitly stylized, never GPS.
 */
export function sectorLabel(externalCode: string): string {
  const pos = gridPosition(externalCode);
  if (!pos) return 'Off-grid';
  return `Sector R${pos.row + 1}·C${pos.col + 1}`;
}

/** Share of scored assets currently at LOW risk (0..1 fleet-health signal). */
export function lowRiskShare(entries: FleetEntry[]): number {
  const scored = entries.filter((e) => e.risk);
  if (scored.length === 0) return 0;
  return scored.filter((e) => e.risk?.risk_level === 'LOW').length / scored.length;
}

/** Count of seed-healthy assets in the loaded fleet entries. */
export function healthyCount(entries: FleetEntry[]): number {
  return entries.filter((e) => e.asset.status === 'healthy').length;
}

/** Fleet-mean abnormality per fusion signal (0..1), over assets with fusion. */
export function signalMeans(entries: FleetEntry[]): { signal: string; mean: number; n: number }[] {
  const rows = entries.filter((e) => e.fusion);
  const keys = [
    'power_score',
    'brightness_score',
    'temperature_score',
    'maintenance_score',
    'neighbor_score',
  ] as const;
  const labels: Record<(typeof keys)[number], string> = {
    power_score: 'Power',
    brightness_score: 'Brightness',
    temperature_score: 'Temperature behavior',
    maintenance_score: 'Maintenance',
    neighbor_score: 'Neighbor correlation',
  };
  return keys.map((k) => ({
    signal: labels[k],
    mean: rows.length === 0 ? 0 : rows.reduce((s, e) => s + (e.fusion?.[k] ?? 0), 0) / rows.length,
    n: rows.length,
  }));
}

/** Top-N entries by risk severity then score (pure, no fetching). */
export function topRisk(entries: FleetEntry[], n: number): FleetEntry[] {
  const rank: Record<string, number> = { LOW: 0, MEDIUM: 1, HIGH: 2, CRITICAL: 3 };
  return [...entries]
    .filter((e) => e.risk)
    .sort(
      (a, b) =>
        (rank[b.risk?.risk_level ?? 'LOW'] ?? 0) - (rank[a.risk?.risk_level ?? 'LOW'] ?? 0) ||
        (b.risk?.risk_score ?? -1) - (a.risk?.risk_score ?? -1),
    )
    .slice(0, n);
}
