import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api } from './api';
import type {
  AnomalyResult,
  Asset,
  ExplanationResult,
  FusionResult,
  RecommendationResult,
  RiskLevel,
  RiskResult,
} from './types';

// ---------------------------------------------------------------------------
// Street-grid derivation. The Phase 2 dataset lays 100 streetlights out on a
// documented 10x10 row-major grid (SL-1001..SL-1100, index = code - 1001).
// This powers the stylized network visualization only -- no GPS or real
// geography is claimed anywhere in the UI.
// ---------------------------------------------------------------------------

export function gridPosition(externalCode: string): { row: number; col: number } | null {
  const match = /^SL-(\d+)$/.exec(externalCode);
  if (!match) return null;
  const idx = parseInt(match[1], 10) - 1001;
  if (idx < 0 || idx >= 100) return null;
  return { row: Math.floor(idx / 10), col: idx % 10 };
}

async function mapLimit<T, R>(items: T[], limit: number, fn: (item: T) => Promise<R>): Promise<R[]> {
  const out: R[] = new Array(items.length);
  let next = 0;
  const workers = new Array(Math.min(limit, items.length)).fill(0).map(async () => {
    while (next < items.length) {
      const i = next;
      next += 1;
      out[i] = await fn(items[i]);
    }
  });
  await Promise.all(workers);
  return out;
}

export interface FleetEntry {
  asset: Asset;
  risk: RiskResult | null;
  fusion: FusionResult | null;
}

export interface FleetState {
  entries: FleetEntry[];
  total: number;
  loading: boolean;
  error: string | null;
  reload: () => void;
}

const RISK_RANK: Record<RiskLevel, number> = { LOW: 0, MEDIUM: 1, HIGH: 2, CRITICAL: 3 };

export function riskRank(level: RiskLevel | null | undefined): number {
  if (!level) return -1;
  return RISK_RANK[level];
}

export function useFleet(): FleetState {
  const [entries, setEntries] = useState<FleetEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);
  const cancelled = useRef(false);

  const reload = useCallback(() => setNonce((n) => n + 1), []);

  useEffect(() => {
    cancelled.current = false;
    setLoading(true);
    setError(null);
    (async () => {
      try {
        const page = await api.assets(1, 100);
        const loaded = await mapLimit(page.items, 12, async (asset) => {
          const [risk, fusion] = await Promise.all([
            api.risk(asset.external_code).catch(() => null),
            api.fusion(asset.external_code).catch(() => null),
          ]);
          return { asset, risk, fusion };
        });
        if (cancelled.current) return;
        loaded.sort(
          (a, b) =>
            riskRank(b.risk?.risk_level) - riskRank(a.risk?.risk_level) ||
            (b.risk?.risk_score ?? -1) - (a.risk?.risk_score ?? -1) ||
            a.asset.external_code.localeCompare(b.asset.external_code),
        );
        setEntries(loaded);
        setTotal(page.total);
      } catch (err) {
        if (!cancelled.current) {
          setError(err instanceof Error ? err.message : 'Failed to load fleet data');
        }
      } finally {
        if (!cancelled.current) setLoading(false);
      }
    })();
    return () => {
      cancelled.current = true;
    };
  }, [nonce]);

  return useMemo(
    () => ({ entries, total, loading, error, reload }),
    [entries, total, loading, error, reload],
  );
}

export interface FleetStats {
  total: number;
  critical: number;
  high: number;
  medium: number;
  low: number;
  emergingWatch: number;
  withRisk: number;
}

export function computeFleetStats(entries: FleetEntry[], total: number): FleetStats {
  let critical = 0;
  let high = 0;
  let medium = 0;
  let low = 0;
  let emergingWatch = 0;
  let withRisk = 0;
  for (const e of entries) {
    if (e.risk) {
      withRisk += 1;
      if (e.risk.risk_level === 'CRITICAL') critical += 1;
      else if (e.risk.risk_level === 'HIGH') high += 1;
      else if (e.risk.risk_level === 'MEDIUM') medium += 1;
      else low += 1;
    }
    if (e.fusion && (e.fusion.status === 'EMERGING' || e.fusion.status === 'WATCH')) {
      emergingWatch += 1;
    }
  }
  return { total, critical, high, medium, low, emergingWatch, withRisk };
}

export interface AssetDetail {
  asset: Asset | null;
  fusion: FusionResult | null;
  risk: RiskResult | null;
  explanation: ExplanationResult | null;
  recommendations: RecommendationResult | null;
  anomaly: AnomalyResult | null;
  loading: boolean;
  error: string | null;
  notFound: boolean;
}

export function useAssetDetail(code: string, assets: Asset[]): AssetDetail {
  const [state, setState] = useState<Omit<AssetDetail, 'asset'>>({
    fusion: null,
    risk: null,
    explanation: null,
    recommendations: null,
    anomaly: null,
    loading: true,
    error: null,
    notFound: false,
  });

  const asset = useMemo(
    () => assets.find((a) => a.external_code === code) ?? null,
    [assets, code],
  );

  useEffect(() => {
    let cancelled = false;
    setState((s) => ({ ...s, loading: true, error: null, notFound: false }));
    if (!asset && assets.length > 0) {
      setState((s) => ({ ...s, loading: false, notFound: true }));
      return () => {
        cancelled = true;
      };
    }
    if (!asset) return () => {};
    (async () => {
      try {
        const [fusion, risk, explanation, recommendations] = await Promise.all([
          api.fusion(asset.external_code).catch(() => null),
          api.risk(asset.external_code).catch(() => null),
          api.explanation(asset.external_code).catch(() => null),
          api.recommendations(asset.external_code).catch(() => null),
        ]);
        // The anomaly endpoint requires the UUID and needs a persisted
        // anomaly row, which may not exist (Phase 3 verifies in-memory).
        // It is optional enrichment: any failure degrades to the anomaly
        // score already present in the risk evidence -- never the page.
        let anomaly: AnomalyResult | null = null;
        try {
          anomaly = await api.anomaly(asset.id);
        } catch {
          anomaly = null;
        }
        if (!cancelled) {
          setState({
            fusion,
            risk,
            explanation,
            recommendations,
            anomaly,
            loading: false,
            error: null,
            notFound: false,
          });
        }
      } catch (err) {
        if (!cancelled) {
          setState((s) => ({
            ...s,
            loading: false,
            error: err instanceof Error ? err.message : 'Failed to load asset detail',
          }));
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [asset, assets.length]);

  return useMemo(() => ({ asset, ...state }), [asset, state]);
}

export function useHealth(): { ok: boolean | null; refresh: () => void } {
  const [ok, setOk] = useState<boolean | null>(null);
  const [nonce, setNonce] = useState(0);
  useEffect(() => {
    let cancelled = false;
    api
      .health()
      .then((h) => {
        if (!cancelled) setOk(h.status === 'ok');
      })
      .catch(() => {
        if (!cancelled) setOk(false);
      });
    return () => {
      cancelled = true;
    };
  }, [nonce]);
  const refresh = useCallback(() => setNonce((n) => n + 1), []);
  return { ok, refresh };
}

export function formatPct(score: number): string {
  return `${(score * 100).toFixed(1)}%`;
}

export function formatScore(score: number): string {
  return score.toFixed(3);
}
