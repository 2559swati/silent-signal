import type { ReactNode } from 'react';
import { Card, EmptyState, ErrorState, RiskBadge, SectionHeader, UrgencyBadge } from '../components/ui';
import { useFleetContext } from '../state';
import { api } from '../lib/api';
import { formatPct, riskRank } from '../lib/fleet';
import { navigate } from '../lib/router';
import { useEffect, useState } from 'react';
import type { RecommendationResult, RiskLevel } from '../lib/types';

const GROUPS: { level: RiskLevel; title: string; hint: string }[] = [
  { level: 'CRITICAL', title: 'Urgent', hint: 'Urgent preventive inspection' },
  { level: 'HIGH', title: 'Prioritize', hint: 'Prioritized inspection' },
  { level: 'MEDIUM', title: 'Planned', hint: 'Planned inspection' },
  { level: 'LOW', title: 'Routine monitoring', hint: 'Continue monitoring' },
];

function GroupSection({ level, title, hint }: { level: RiskLevel; title: string; hint: string }): ReactNode {
  const { entries } = useFleetContext();
  const [details, setDetails] = useState<Record<string, RecommendationResult | null>>({});
  const list = entries.filter((e) => e.risk?.risk_level === level).slice(0, level === 'LOW' ? 4 : 8);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const out: Record<string, RecommendationResult | null> = {};
      await Promise.all(
        list.map(async ({ asset }) => {
          try {
            out[asset.external_code] = await api.recommendations(asset.external_code);
          } catch {
            out[asset.external_code] = null;
          }
        }),
      );
      if (!cancelled) setDetails(out);
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [entries.length, level]);

  if (list.length === 0) return null;
  return (
    <section aria-label={`${title} actions`}>
      <SectionHeader title={`${title} (${list.length}${level === 'LOW' ? ' shown' : ''})`} subtitle={hint} />
      <ul className="grid gap-3 md:grid-cols-2">
        {list.map(({ asset, risk }) => {
          const rec = details[asset.external_code];
          return (
            <li key={asset.id}>
              <Card className="p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    onClick={() => navigate({ name: 'asset', code: asset.external_code })}
                    className="font-mono text-sm font-extrabold text-white hover:text-sky-300"
                  >
                    {asset.external_code}
                  </button>
                  {risk ? <RiskBadge level={risk.risk_level} /> : null}
                  {rec ? <UrgencyBadge urgency={rec.urgency} /> : null}
                  <span className="ml-auto font-mono text-sm font-bold text-slate-300">
                    {risk ? formatPct(risk.risk_score) : '—'}
                  </span>
                </div>
                {rec ? (
                  <ul className="mt-3 space-y-1.5">
                    {rec.recommendations.slice(0, 3).map((r, i) => (
                      <li key={i} className="rounded-lg border border-edge-soft bg-panel-2/60 px-2.5 py-2 text-xs">
                        <span className="block font-bold text-slate-200">{r.action}</span>
                        {i === 0 ? null : <span className="mt-0.5 block text-slate-500">{r.reason}</span>}
                      </li>
                    ))}
                    {rec.recommendations.length > 3 ? (
                      <li className="text-[11px] font-semibold text-sky-400">
                        +{rec.recommendations.length - 3} more actions — open asset detail
                      </li>
                    ) : null}
                  </ul>
                ) : (
                  <p className="mt-3 text-xs text-slate-600">Loading actions…</p>
                )}
                <p className="mt-2 text-[11px] text-slate-500">
                  Priority: <span className="font-bold text-slate-300">{rec ? rec.priority : '…'}</span>
                  {risk ? ` · sustained ${risk.persistence_score.toFixed(2)}` : ''}
                </p>
              </Card>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

export default function Actions(): ReactNode {
  const { entries, loading, error, reload } = useFleetContext();
  const ranked = [...entries].sort(
    (a, b) => riskRank(b.risk?.risk_level) - riskRank(a.risk?.risk_level) || (b.risk?.risk_score ?? 0) - (a.risk?.risk_score ?? 0),
  );
  const top = ranked[0];

  return (
    <div className="space-y-6 animate-rise">
      <div>
        <h2 className="text-xl font-extrabold tracking-tight text-white sm:text-2xl">PREVENTIVE ACTION CENTER</h2>
        <p className="mt-1 max-w-3xl text-sm text-slate-400">
          Operational queue generated live from the recommendation engine — critical first, every
          action backed by evidence.
        </p>
      </div>
      {loading ? (
        <Card className="p-4">
          {[0, 1, 2].map((i) => (
            <div key={i} className="skeleton mb-2 h-16 w-full rounded-xl last:mb-0" />
          ))}
        </Card>
      ) : error ? (
        <ErrorState message={error} onRetry={reload} />
      ) : ranked.length === 0 ? (
        <EmptyState message="No recommendation data available." />
      ) : (
        <>
          {top?.risk ? (
            <Card className="border-red-500/30 p-5">
              <div className="flex flex-wrap items-center gap-3">
                <RiskBadge level={top.risk.risk_level} />
                <button
                  type="button"
                  onClick={() => navigate({ name: 'asset', code: top.asset.external_code })}
                  className="font-mono text-xl font-extrabold text-white hover:text-sky-300"
                >
                  {top.asset.external_code}
                </button>
                <span className="font-mono text-xl font-extrabold text-red-300">
                  {formatPct(top.risk.risk_score)}
                </span>
                <span className="ml-auto text-xs text-slate-500">Highest risk right now — start here.</span>
              </div>
            </Card>
          ) : null}
          {GROUPS.map((g) => (
            <GroupSection key={g.level} level={g.level} title={g.title} hint={g.hint} />
          ))}
        </>
      )}
    </div>
  );
}
