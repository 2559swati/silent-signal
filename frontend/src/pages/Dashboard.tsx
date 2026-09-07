import type { ReactNode } from 'react';
import { AlertOctagon, ArrowRight, Gauge, Layers, Network } from 'lucide-react';
import { Card, EmptyState, ErrorState, FusionBadge, RiskBadge, SectionHeader } from '../components/ui';
import { PipelineExplainer, PipelineStages } from '../components/Pipeline';
import NetworkGrid from '../components/NetworkGrid';
import { useFleetContext } from '../state';
import { formatPct, riskRank } from '../lib/fleet';
import { navigate } from '../lib/router';

function Kpi({
  icon,
  label,
  value,
  hint,
  accent,
  loading,
}: {
  icon: ReactNode;
  label: string;
  value: string;
  hint: string;
  accent: string;
  loading: boolean;
}): ReactNode {
  return (
    <Card className="p-5">
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-bold tracking-[0.16em] text-slate-500">{label}</span>
        <span aria-hidden>{icon}</span>
      </div>
      {loading ? (
        <div className="skeleton mt-2 h-10 w-24 rounded-lg" aria-hidden />
      ) : (
        <p className="mt-1 text-4xl font-extrabold tracking-tight text-white animate-rise">{value}</p>
      )}
      <p className="mt-1 text-xs text-slate-500">{hint}</p>
      <span className="mt-3 block h-1 w-full overflow-hidden rounded-full bg-slate-800" aria-hidden>
        <span className={`block h-full w-full ${accent}`} />
      </span>
    </Card>
  );
}

function Distribution({ counts }: { counts: { label: string; count: number; color: string }[] }): ReactNode {
  const total = counts.reduce((s, c) => s + c.count, 0) || 1;
  return (
    <div>
      <div
        className="flex h-4 w-full overflow-hidden rounded-full border border-edge bg-panel-2"
        role="img"
        aria-label={`Fleet health: ${counts.map((c) => `${c.label} ${c.count}`).join(', ')}`}
      >
        {counts.map((c) => (
          <span
            key={c.label}
            style={{ width: `${(c.count / total) * 100}%`, background: c.color }}
            title={`${c.label}: ${c.count}`}
          />
        ))}
      </div>
      <ul className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
        {counts.map((c) => (
          <li key={c.label} className="flex items-center gap-2 text-xs">
            <span className="h-2.5 w-2.5 rounded-full" style={{ background: c.color }} aria-hidden />
            <span className="font-semibold text-slate-300">{c.label}</span>
            <span className="ml-auto font-extrabold text-white">{c.count}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function Dashboard(): ReactNode {
  const { entries, stats, loading, error, reload } = useFleetContext();
  const attention = entries.filter((e) => e.risk && riskRank(e.risk.risk_level) >= 2).slice(0, 6);

  return (
    <div className="space-y-6 animate-rise">
      {/* Hero */}
      <div>
        <p className="text-[11px] font-bold tracking-[0.22em] text-sky-400">SILENTSIGNAL AI</p>
        <h2 className="mt-1 text-2xl font-extrabold tracking-tight text-white sm:text-3xl">
          From weak signals to preventive action.
        </h2>
        <p className="mt-1 max-w-2xl text-sm text-slate-400">
          AI-powered early warning for urban infrastructure. Every number below is computed live
          from backend evidence — nothing is hardcoded.
        </p>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        <Kpi
          icon={<Network className="h-4 w-4 text-sky-400" aria-hidden />}
          label="TOTAL ASSETS"
          value={loading ? '' : String(stats.total)}
          hint="Streetlights under monitoring"
          accent="bg-sky-500/70"
          loading={loading}
        />
        <Kpi
          icon={<AlertOctagon className="h-4 w-4 text-red-400" aria-hidden />}
          label="CRITICAL"
          value={loading ? '' : String(stats.critical)}
          hint="Require immediate attention"
          accent="bg-red-500/80"
          loading={loading}
        />
        <Kpi
          icon={<Gauge className="h-4 w-4 text-amber-400" aria-hidden />}
          label="HIGH RISK"
          value={loading ? '' : String(stats.high)}
          hint="Prioritized inspections"
          accent="bg-amber-500/80"
          loading={loading}
        />
        <Kpi
          icon={<Layers className="h-4 w-4 text-yellow-300" aria-hidden />}
          label="EMERGING / WATCH"
          value={loading ? '' : String(stats.emergingWatch)}
          hint="Abnormal fusion behavior"
          accent="bg-yellow-400/80"
          loading={loading}
        />
      </div>

      {/* Pipeline */}
      <section aria-label="SilentSignal pipeline">
        <SectionHeader
          title="The SilentSignal pipeline"
          subtitle="Six deterministic stages turn faint infrastructure symptoms into maintenance actions."
        />
        <PipelineStages />
        <div className="mt-2">
          <PipelineExplainer />
        </div>
      </section>

      {/* Network + health */}
      <div className="grid gap-4 xl:grid-cols-5">
        <Card className="p-5 xl:col-span-3">
          <SectionHeader title="Streetlight network" subtitle="Live fusion status per asset. Select any node." />
          {loading ? (
            <div className="skeleton aspect-square w-full rounded-xl" aria-label="Loading network" />
          ) : error ? (
            <ErrorState message={error} onRetry={reload} />
          ) : (
            <NetworkGrid entries={entries} />
          )}
        </Card>
        <div className="space-y-4 xl:col-span-2">
          <Card className="p-5">
            <SectionHeader title="Fleet health overview" subtitle="Live risk distribution." />
            {loading ? (
              <div className="skeleton h-24 w-full rounded-xl" aria-hidden />
            ) : (
              <Distribution
                counts={[
                  { label: 'Low', count: stats.low, color: '#22c55e' },
                  { label: 'Medium', count: stats.medium, color: '#38bdf8' },
                  { label: 'High', count: stats.high, color: '#f59e0b' },
                  { label: 'Critical', count: stats.critical, color: '#f04452' },
                ]}
              />
            )}
            <p className="mt-3 text-xs text-slate-500">Critical assets require immediate attention.</p>
          </Card>
          <Card className="p-5">
            <SectionHeader title="Fusion watch" subtitle="Emerging vs watch behavior right now." />
            {loading ? (
              <div className="skeleton h-10 w-full rounded-xl" aria-hidden />
            ) : (
              <p className="text-sm text-slate-300">
                <span className="text-2xl font-extrabold text-white">{stats.emergingWatch}</span>{' '}
                assets show emerging or watch fusion behavior.
              </p>
            )}
          </Card>
        </div>
      </div>

      {/* Attention list */}
      <section aria-label="Assets requiring attention">
        <SectionHeader
          title="Assets requiring attention"
          subtitle="Highest live risk scores across the fleet."
          action={
            <a
              href="#/assets"
              className="inline-flex items-center gap-1 text-xs font-bold text-sky-400 hover:text-sky-300"
            >
              View all <ArrowRight className="h-3.5 w-3.5" aria-hidden />
            </a>
          }
        />
        {loading ? (
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {[0, 1, 2].map((i) => (
              <Card key={i} className="p-4">
                <div className="skeleton h-5 w-2/3 rounded" />
                <div className="skeleton mt-2 h-4 w-full rounded" />
              </Card>
            ))}
          </div>
        ) : error ? (
          <ErrorState message={error} onRetry={reload} />
        ) : attention.length === 0 ? (
          <EmptyState message="No elevated-risk assets right now." />
        ) : (
          <ul className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {attention.map(({ asset, risk, fusion }) => (
              <li key={asset.id}>
                <button
                  type="button"
                  onClick={() => navigate({ name: 'asset', code: asset.external_code })}
                  className="block w-full text-left"
                >
                  <Card hover className="p-4">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono text-sm font-bold text-white">{asset.external_code}</span>
                      {risk ? <RiskBadge level={risk.risk_level} /> : null}
                    </div>
                    <div className="mt-2 flex items-center justify-between text-xs text-slate-400">
                      <span>
                        Risk <span className="font-extrabold text-white">{risk ? formatPct(risk.risk_score) : '—'}</span>
                      </span>
                      <span>
                        Anomaly <span className="font-bold text-slate-200">{risk ? risk.anomaly_score.toFixed(2) : '—'}</span>
                      </span>
                      <span>
                        Persist <span className="font-bold text-slate-200">{risk ? risk.persistence_score.toFixed(2) : '—'}</span>
                      </span>
                    </div>
                    <div className="mt-2 flex items-center justify-between">
                      {fusion ? <FusionBadge status={fusion.status} /> : <span />}
                      <span className="text-[11px] font-semibold text-sky-400">Open detail →</span>
                    </div>
                  </Card>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
