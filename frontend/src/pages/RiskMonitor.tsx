import type { CSSProperties, ReactNode } from 'react';
import { Card, EmptyState, ErrorState, RiskBadge, SectionHeader, Skeleton } from '../components/ui';
import { useFleetContext } from '../state';
import { formatPct, riskRank } from '../lib/fleet';
import { navigate } from '../lib/router';
import type { RiskLevel } from '../lib/types';

const BUCKETS = [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0];

export default function RiskMonitor(): ReactNode {
  const { entries, stats, loading, error, reload } = useFleetContext();

  const histogram = BUCKETS.slice(0, -1).map((lo, i) => {
    const hi = BUCKETS[i + 1];
    const count = entries.filter(
      (e) => e.risk && e.risk.risk_score >= lo && (e.risk.risk_score < hi || hi === 1.0),
    ).length;
    return { lo, hi, count };
  });
  const maxBucket = Math.max(1, ...histogram.map((h) => h.count));
  const ranked = [...entries].sort(
    (a, b) => riskRank(b.risk?.risk_level) - riskRank(a.risk?.risk_level) || (b.risk?.risk_score ?? -1) - (a.risk?.risk_score ?? -1),
  );
  const groups: { level: RiskLevel; title: string; hint: string }[] = [
    { level: 'CRITICAL', title: 'Critical assets', hint: 'Urgent preventive inspection' },
    { level: 'HIGH', title: 'High-risk assets', hint: 'Prioritized inspection' },
    { level: 'MEDIUM', title: 'Medium-risk assets', hint: 'Planned inspection' },
  ];

  return (
    <div className="space-y-6 animate-rise">
      <div className="grid gap-4 xl:grid-cols-2">
        <Card className="p-5">
          <SectionHeader title="Risk score distribution" subtitle="Live fleet histogram (10 buckets)." />
          {loading ? (
            <div className="skeleton h-44 w-full rounded-xl" aria-hidden />
          ) : (
            <div className="flex h-44 items-end gap-1.5" role="img" aria-label="Risk score histogram">
              {histogram.map((h, i) => (
                <div key={h.lo} className="group relative flex-1" title={`${h.lo.toFixed(1)}–${h.hi.toFixed(1)}: ${h.count}`}>
                  <div
                    className="col-grow w-full rounded-t-md bg-sky-500/70 transition group-hover:bg-sky-400"
                    style={{ height: `${Math.max(4, (h.count / maxBucket) * 160)}px`, '--d': `${i * 45}ms` } as CSSProperties}
                  />
                  <span className="mt-1 block text-center text-[9px] text-slate-600">{h.lo.toFixed(1)}</span>
                </div>
              ))}
            </div>
          )}
        </Card>
        <Card className="p-5">
          <SectionHeader title="Concentration" subtitle="Where risk sits right now." />
          {loading ? (
            <Skeleton className="h-6 w-2/3" />
          ) : (
            <ul className="space-y-3">
              {[
                { label: 'Critical', n: stats.critical, color: 'bg-red-500', pct: stats.total ? (stats.critical / stats.total) * 100 : 0 },
                { label: 'High', n: stats.high, color: 'bg-amber-500', pct: stats.total ? (stats.high / stats.total) * 100 : 0 },
                { label: 'Medium', n: stats.medium, color: 'bg-sky-500', pct: stats.total ? (stats.medium / stats.total) * 100 : 0 },
                { label: 'Low', n: stats.low, color: 'bg-emerald-500', pct: stats.total ? (stats.low / stats.total) * 100 : 0 },
              ].map((r) => (
                <li key={r.label}>
                  <div className="mb-1 flex justify-between text-xs">
                    <span className="font-bold text-slate-600">{r.label}</span>
                    <span className="font-mono font-bold text-slate-900">{r.n} · {r.pct.toFixed(1)}%</span>
                  </div>
                  <div className="h-2 overflow-hidden rounded-full bg-slate-200">
                    <div className={`bar-grow h-full rounded-full ${r.color}`} style={{ width: `${r.pct}%` }} />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      {loading ? (
        <Card className="p-4">
          {[0, 1, 2].map((i) => (
            <div key={i} className="skeleton mb-2 h-12 w-full rounded-xl last:mb-0" />
          ))}
        </Card>
      ) : error ? (
        <ErrorState message={error} onRetry={reload} />
      ) : (
        groups.map((g) => {
          const list = ranked.filter((e) => e.risk?.risk_level === g.level).slice(0, 8);
          if (list.length === 0) return null;
          return (
            <section key={g.level} aria-label={g.title}>
              <SectionHeader title={g.title} subtitle={`${list.length} shown · ${g.hint}`} />
              <ul className="grid gap-2 md:grid-cols-2 xl:grid-cols-4">
                {list.map(({ asset, risk }, i) => (
                  <li key={asset.id} className="rise-item" style={{ '--d': `${Math.min(i * 50, 320)}ms` } as CSSProperties}>
                    <button type="button" onClick={() => navigate({ name: 'asset', code: asset.external_code })} className="block w-full text-left">
                      <Card hover className="flex items-center justify-between gap-2 p-3.5">
                        <span>
                          <span className="block font-mono text-sm font-bold text-slate-900">{asset.external_code}</span>
                          <span className="mt-0.5 block text-xs text-slate-500">
                            persist {risk?.persistence_score.toFixed(2) ?? '—'} · anomaly {risk?.anomaly_score.toFixed(2) ?? '—'}
                          </span>
                        </span>
                        <span className="text-right">
                          <span className="block font-mono text-lg font-extrabold text-slate-900">
                            {risk ? formatPct(risk.risk_score) : '—'}
                          </span>
                          {risk ? <RiskBadge level={risk.risk_level} /> : null}
                        </span>
                      </Card>
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          );
        })
      )}
      {!loading && !error && ranked.length === 0 ? <EmptyState message="No risk data available." /> : null}
    </div>
  );
}
