import { useEffect, useState, type CSSProperties, type ReactNode } from 'react';
import { api } from '../lib/api';
import { Card, EmptyState, ErrorState, RiskBadge, SectionHeader, SeverityBadge, Skeleton } from '../components/ui';
import { useFleetContext } from '../state';
import { formatPct, riskRank } from '../lib/fleet';
import { navigate } from '../lib/router';
import type { ExplanationResult, Severity } from '../lib/types';

export default function Explanations(): ReactNode {
  const { entries, loading, error, reload } = useFleetContext();
  const ranked = [...entries]
    .filter((e) => e.risk)
    .sort((a, b) => riskRank(b.risk?.risk_level) - riskRank(a.risk?.risk_level) || (b.risk?.risk_score ?? 0) - (a.risk?.risk_score ?? 0));
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<ExplanationResult | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  useEffect(() => {
    if (!selected) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    setDetailLoading(true);
    setDetailError(null);
    api
      .explanation(selected)
      .then((d) => {
        if (!cancelled) setDetail(d);
      })
      .catch((err: unknown) => {
        if (!cancelled) setDetailError(err instanceof Error ? err.message : 'Failed to load explanation');
      })
      .finally(() => {
        if (!cancelled) setDetailLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selected]);

  return (
    <div className="space-y-4 animate-rise">
      <div>
        <h2 className="text-xl font-extrabold tracking-tight text-slate-900 sm:text-2xl">
          WHY IS SILENTSIGNAL FLAGGING THESE ASSETS?
        </h2>
        <p className="mt-1 max-w-3xl text-sm text-slate-500">
          Rule-based explanations over live Phase 3–5 evidence. Select an asset to read its full
          evidence trail — written for operators, not data scientists.
        </p>
      </div>
      <div className="grid gap-4 xl:grid-cols-5">
        <Card className="max-h-[640px] overflow-y-auto scroll-thin p-2 xl:col-span-2">
          {loading ? (
            <div className="space-y-2 p-2">
              {[0, 1, 2, 3, 4, 5].map((i) => (
                <Skeleton key={i} className="h-14 w-full" />
              ))}
            </div>
          ) : error ? (
            <div className="p-2">
              <ErrorState message={error} onRetry={reload} />
            </div>
          ) : ranked.length === 0 ? (
            <div className="p-2">
              <EmptyState message="No assets to explain." />
            </div>
          ) : (
            <ul className="space-y-1" aria-label="Assets ranked by risk">
              {ranked.map(({ asset, risk }) => {
                const isSel = selected === asset.external_code;
                return (
                  <li key={asset.id}>
                    <button
                      type="button"
                      onClick={() => setSelected(asset.external_code)}
                      aria-pressed={isSel}
                      className={`flex w-full items-center justify-between gap-2 rounded-xl border px-3 py-2.5 text-left transition ${
                        isSel ? 'border-sky-500/50 bg-sky-500/10' : 'border-transparent hover:bg-slate-900/[0.04]'
                      }`}
                    >
                      <span>
                        <span className="block font-mono text-sm font-bold text-slate-900">{asset.external_code}</span>
                        <span className="block text-[11px] text-slate-500">
                          {risk ? `${formatPct(risk.risk_score)} risk` : 'no risk data'}
                        </span>
                      </span>
                      {risk ? <RiskBadge level={risk.risk_level} /> : null}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </Card>
        <div className="xl:col-span-3">
          {!selected ? (
            <EmptyState message="Select an asset on the left to read its explanation." />
          ) : detailLoading ? (
            <Card className="p-5">
              <Skeleton className="mb-2 h-6 w-1/2" />
              <Skeleton className="mb-2 h-4 w-full" />
              <Skeleton className="h-4 w-2/3" />
            </Card>
          ) : detailError || !detail ? (
            <ErrorState message={detailError ?? 'Explanation unavailable.'} onRetry={() => setSelected((s) => (s ? `${s}` : s))} />
          ) : (
            <Card className="page-enter p-5" key={selected}>
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={() => navigate({ name: 'asset', code: detail.asset_external_code })}
                  className="font-mono text-lg font-extrabold text-slate-900 hover:text-sky-700"
                >
                  {detail.asset_external_code}
                </button>
                <RiskBadge level={detail.risk_level} />
                <span className="ml-auto font-mono text-sm font-bold text-slate-600">
                  {formatPct(detail.risk_score)}
                </span>
              </div>
              <p className="mt-3 border-l-2 border-sky-500/60 pl-3 text-sm leading-relaxed text-slate-600">
                {detail.summary}
              </p>
              <SectionHeader title="Contributing factors" subtitle="Deterministic rules, live scores." />
              <ul className="space-y-2">
                {detail.factors.map((f, i) => (
                  <li
                    key={f.signal}
                    className="rise-item rounded-xl border border-edge bg-panel-2/60 p-3"
                    style={{ '--d': `${Math.min(i * 70, 350)}ms` } as CSSProperties}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs font-bold tracking-widest text-slate-500 uppercase">
                        {f.signal === 'temperature' ? 'Temperature behavior' : f.signal === 'neighbor' ? 'Neighbor correlation' : f.signal}
                      </span>
                      <SeverityBadge severity={f.severity as Severity} />
                    </div>
                    <p className="mt-1 font-mono text-lg font-extrabold text-slate-900">{formatPct(f.score)}</p>
                    <p className="mt-1 text-xs leading-relaxed text-slate-500">{f.reason}</p>
                  </li>
                ))}
              </ul>
              <div className="mt-4 grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
                <div className="rounded-xl border border-edge p-2.5">
                  <p className="text-slate-500">Persistence</p>
                  <p className="font-mono font-bold text-slate-900">
                    {typeof detail.evidence.persistence_score === 'number'
                      ? (detail.evidence.persistence_score as number).toFixed(2)
                      : '—'}
                  </p>
                </div>
                <div className="rounded-xl border border-edge p-2.5">
                  <p className="text-slate-500">Streak</p>
                  <p className="font-mono font-bold text-slate-900">
                    {String(detail.evidence.elevated_streak_days ?? '—')} days
                  </p>
                </div>
                <div className="rounded-xl border border-edge p-2.5">
                  <p className="text-slate-500">Fusion status</p>
                  <p className="font-mono font-bold text-slate-900">{String(detail.evidence.fusion_status ?? '—')}</p>
                </div>
                <div className="rounded-xl border border-edge p-2.5">
                  <p className="text-slate-500">Model</p>
                  <p className="font-mono font-bold text-slate-900">{detail.model_version}</p>
                </div>
              </div>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
