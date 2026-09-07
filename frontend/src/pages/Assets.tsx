import { useMemo, useState, type ReactNode } from 'react';
import { ArrowUpDown } from 'lucide-react';
import { Card, EmptyState, ErrorState, FusionBadge, RiskBadge, SectionHeader } from '../components/ui';
import { useFleetContext } from '../state';
import { formatPct } from '../lib/fleet';
import { navigate } from '../lib/router';
import type { RiskLevel } from '../lib/types';

const FILTERS: { key: string; label: string; test: (l?: RiskLevel) => boolean }[] = [
  { key: 'all', label: 'All', test: () => true },
  { key: 'CRITICAL', label: 'Critical', test: (l) => l === 'CRITICAL' },
  { key: 'HIGH', label: 'High', test: (l) => l === 'HIGH' },
  { key: 'MEDIUM', label: 'Medium', test: (l) => l === 'MEDIUM' },
  { key: 'LOW', label: 'Low', test: (l) => l === 'LOW' },
];

export default function Assets({ query }: { query: string }): ReactNode {
  const { entries, loading, error, reload } = useFleetContext();
  const [filter, setFilter] = useState('all');
  const [sortDesc, setSortDesc] = useState(true);

  const rows = useMemo(() => {
    const f = FILTERS.find((x) => x.key === filter) ?? FILTERS[0];
    const q = query.trim().toLowerCase();
    const filtered = entries.filter(
      (e) =>
        f.test(e.risk?.risk_level) &&
        (q === '' || e.asset.external_code.toLowerCase().includes(q)),
    );
    return [...filtered].sort((a, b) =>
      sortDesc
        ? (b.risk?.risk_score ?? -1) - (a.risk?.risk_score ?? -1)
        : (a.risk?.risk_score ?? -1) - (b.risk?.risk_score ?? -1),
    );
  }, [entries, filter, query, sortDesc]);

  return (
    <div className="space-y-4 animate-rise">
      <SectionHeader title={`${rows.length} streetlights`} subtitle="Search, filter by risk level, sort by live risk score." />
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex flex-wrap gap-1.5" role="group" aria-label="Filter by risk level">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              type="button"
              onClick={() => setFilter(f.key)}
              aria-pressed={filter === f.key}
              className={`rounded-full border px-3 py-1.5 text-xs font-bold transition ${
                filter === f.key
                  ? 'border-sky-500/60 bg-sky-500/15 text-white'
                  : 'border-edge bg-panel text-slate-400 hover:text-white'
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
        <button
          type="button"
          onClick={() => setSortDesc((d) => !d)}
          className="ml-auto inline-flex items-center gap-1.5 rounded-full border border-edge bg-panel px-3 py-1.5 text-xs font-bold text-slate-300 hover:text-white"
          aria-label={sortDesc ? 'Sort ascending by risk' : 'Sort descending by risk'}
        >
          <ArrowUpDown className="h-3.5 w-3.5" aria-hidden />
          Risk {sortDesc ? '↓' : '↑'}
        </button>
      </div>

      {loading ? (
        <Card className="p-4">
          {[0, 1, 2, 3, 4].map((i) => (
            <div key={i} className="skeleton mb-2 h-12 w-full rounded-xl last:mb-0" />
          ))}
        </Card>
      ) : error ? (
        <ErrorState message={error} onRetry={reload} />
      ) : rows.length === 0 ? (
        <EmptyState message="No assets match your filters." />
      ) : (
        <Card className="overflow-hidden">
          <div className="overflow-x-auto scroll-thin">
            <table className="w-full min-w-[760px] text-left text-sm">
              <thead>
                <tr className="border-b border-edge text-[11px] uppercase tracking-widest text-slate-500">
                  {['Asset', 'Risk', 'Score', 'Anomaly', 'Fusion', 'Persistence', ''].map((h) => (
                    <th key={h} scope="col" className="px-4 py-3 font-bold">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map(({ asset, risk, fusion }) => (
                  <tr
                    key={asset.id}
                    className="cursor-pointer border-b border-edge-soft transition last:border-0 hover:bg-white/[0.03]"
                    onClick={() => navigate({ name: 'asset', code: asset.external_code })}
                    tabIndex={0}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') navigate({ name: 'asset', code: asset.external_code });
                    }}
                    aria-label={`Open ${asset.external_code}`}
                  >
                    <td className="px-4 py-3 font-mono font-bold text-white">{asset.external_code}</td>
                    <td className="px-4 py-3">{risk ? <RiskBadge level={risk.risk_level} /> : <span className="text-slate-600">—</span>}</td>
                    <td className="px-4 py-3 font-extrabold text-white">{risk ? formatPct(risk.risk_score) : '—'}</td>
                    <td className="px-4 py-3 text-slate-300">{risk ? risk.anomaly_score.toFixed(2) : '—'}</td>
                    <td className="px-4 py-3">{fusion ? <FusionBadge status={fusion.status} /> : <span className="text-slate-600">—</span>}</td>
                    <td className="px-4 py-3 text-slate-300">{risk ? risk.persistence_score.toFixed(2) : '—'}</td>
                    <td className="px-4 py-3 text-right text-xs font-bold text-sky-400">Open →</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}
