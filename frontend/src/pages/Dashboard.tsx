import { useEffect, useState, type CSSProperties, type ReactNode } from 'react';
import { AlertOctagon, ArrowRight, Bell, CheckCircle2, Gauge, Layers, Network } from 'lucide-react';
import { Card, EmptyState, ErrorState, FusionBadge, RiskBadge, RiskRing, SectionHeader, SeverityBadge } from '../components/ui';
import { PipelineExplainer, PipelineStages } from '../components/Pipeline';
import NetworkGrid from '../components/NetworkGrid';
import { useFleetContext } from '../state';
import { api } from '../lib/api';
import { formatPct } from '../lib/fleet';
import { healthyCount, lowRiskShare, sectorLabel, signalMeans, topRisk } from '../lib/ops';
import { staggerDelay, useCountUp } from '../lib/animate';
import { navigate } from '../lib/router';
import type { FleetAlertItem, Severity } from '../lib/types';

/** Backend alert severities mirror risk levels (upper-case); badges use lower-case. */
function normalizeSeverity(severity: string): Severity {
  const lowered = severity.toLowerCase();
  return lowered === 'low' || lowered === 'medium' || lowered === 'high' || lowered === 'critical'
    ? lowered
    : 'medium';
}

function Kpi({
  icon,
  label,
  value,
  hint,
  accent,
  loading,
  index,
  topline,
}: {
  icon: ReactNode;
  label: string;
  value: string;
  hint: string;
  accent: string;
  loading: boolean;
  index: number;
  topline?: string;
}): ReactNode {
  // Count up ONLY the real backend value (parsed from the provided string).
  const target = Number.parseInt(value, 10);
  const animated = useCountUp(Number.isFinite(target) ? target : 0);
  const display = loading || !Number.isFinite(target) ? value : String(Math.round(animated));
  return (
    <Card
      className="rise-item card-lift group kpi-topline p-5 hover:-translate-y-0.5"
      style={{ '--d': staggerDelay(index), '--kpi-accent': topline ?? '#0ea5e9' } as CSSProperties}
    >
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-bold tracking-[0.16em] text-slate-500">{label}</span>
        <span aria-hidden className="transition-transform duration-200 group-hover:scale-110">{icon}</span>
      </div>
      {loading ? (
        <div className="skeleton mt-2 h-10 w-24 rounded-lg" aria-hidden />
      ) : (
        <p className="tnum mt-1 text-4xl font-extrabold tracking-tight text-slate-900">{display}</p>
      )}
      <p className="mt-1 text-xs text-slate-500">{hint}</p>
      <span className="mt-3 block h-1 w-full overflow-hidden rounded-full bg-slate-200" aria-hidden>
        {!loading ? <span className={`bar-grow block h-full w-full ${accent}`} style={{ ['--d' as string]: `${index * 60}ms` }} /> : null}
      </span>
    </Card>
  );
}

function RiskDonut({ counts }: { counts: { label: string; count: number; color: string }[] }): ReactNode {
  const total = counts.reduce((s, c) => s + c.count, 0) || 1;
  const size = 132;
  const stroke = 18;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  let acc = 0;
  const segs = counts.map((s) => {
    const frac = s.count / total;
    const seg = { ...s, dash: frac * c, offset: acc };
    acc += frac * c;
    return seg;
  });
  return (
    <div className="flex items-center gap-5">
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        className="donut-enter shrink-0 -rotate-90"
        role="img"
        aria-label={`Risk distribution: ${counts.map((x) => `${x.label} ${x.count}`).join(', ')}`}
      >
        <circle cx={size / 2} cy={size / 2} r={r} stroke="#e8edf5" strokeWidth={stroke} fill="none" />
        {segs.map((s) => (
          <circle
            key={s.label}
            cx={size / 2}
            cy={size / 2}
            r={r}
            stroke={s.color}
            strokeWidth={stroke}
            fill="none"
            strokeLinecap="butt"
            strokeDasharray={`${s.dash} ${c - s.dash}`}
            strokeDashoffset={-s.offset}
            className="donut-seg"
          >
            <title>{`${s.label}: ${s.count}`}</title>
          </circle>
        ))}
      </svg>
      <ul className="min-w-0 flex-1 space-y-2.5">
        {segs.map((s, i) => (
          <li key={s.label}>
            <div className="mb-1 flex items-center gap-2 text-xs">
              <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: s.color }} aria-hidden />
              <span className="font-semibold text-slate-600">{s.label}</span>
              <span className="tnum ml-auto font-extrabold text-slate-900">{s.count}</span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-slate-200">
              <div
                className="bar-grow h-full rounded-full"
                style={{ width: `${(s.count / total) * 100}%`, background: s.color, '--d': `${i * 90}ms` } as CSSProperties}
              />
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}



export default function Dashboard(): ReactNode {
  const { entries, stats, loading, error, reload } = useFleetContext();
  const attention = topRisk(entries, 6);
  const [alerts, setAlerts] = useState<{ day: string; items: FleetAlertItem[]; total: number } | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .alerts()
      .then((res) => {
        if (!cancelled) setAlerts({ day: res.day, items: res.alerts.slice(0, 6), total: res.total_alerts });
      })
      .catch(() => {
        if (!cancelled) setAlerts(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const healthShare = lowRiskShare(entries);
  const animatedHealth = useCountUp(loading ? 0 : healthShare);
  const healthy = healthyCount(entries);
  const signals = signalMeans(entries);

  return (
    <div className="space-y-6 animate-rise">
      {/* Hero */}
      <div className="relative overflow-hidden rounded-2xl">
        <div className="hero-motif pointer-events-none absolute inset-0" aria-hidden />
        <div className="relative py-1">
          <p className="text-[11px] font-bold tracking-[0.22em] text-sky-600">
            SILENT SIGNAL AI · PREDICTIVE STREETLIGHT OPERATIONS
          </p>
          <h2 className="mt-1 text-2xl font-extrabold tracking-tight sm:text-3xl">
            <span className="text-brand-gradient">Predictive Streetlight Operations</span>
          </h2>
          <p className="mt-1 max-w-2xl text-sm text-slate-500">
            Monitor fleet health, detect emerging anomalies, and identify maintenance risks
            before failures occur. Every number below is computed live from backend
            evidence — nothing is hardcoded.
          </p>
        </div>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6">
        <Kpi
          icon={<Network className="h-4 w-4 text-sky-600" aria-hidden />}
          label="TOTAL ASSETS"
          value={loading ? '' : String(stats.total)}
          hint="Streetlights under monitoring"
          accent="bg-sky-500/70"
          loading={loading}
          index={0}
          topline="#0ea5e9"
        />
        <Kpi
          icon={<CheckCircle2 className="h-4 w-4 text-emerald-600" aria-hidden />}
          label="HEALTHY"
          value={loading ? '' : String(healthy)}
          hint="No abnormal behavior"
          accent="bg-emerald-500/70"
          loading={loading}
          index={1}
          topline="#10b981"
        />
        <Kpi
          icon={<AlertOctagon className="h-4 w-4 text-red-400" aria-hidden />}
          label="CRITICAL"
          value={loading ? '' : String(stats.critical)}
          hint="Require immediate attention"
          accent="bg-red-500/80"
          loading={loading}
          index={2}
          topline="#f04452"
        />
        <Kpi
          icon={<Gauge className="h-4 w-4 text-amber-400" aria-hidden />}
          label="HIGH RISK"
          value={loading ? '' : String(stats.high)}
          hint="Prioritized inspections"
          accent="bg-amber-500/80"
          loading={loading}
          index={3}
          topline="#f59e0b"
        />
        <Kpi
          icon={<Layers className="h-4 w-4 text-yellow-300" aria-hidden />}
          label="EMERGING / WATCH"
          value={loading ? '' : String(stats.emergingWatch)}
          hint="Abnormal fusion behavior"
          accent="bg-yellow-400/80"
          loading={loading}
          index={4}
          topline="#eab308"
        />
        <Kpi
          icon={<Bell className="h-4 w-4 text-orange-500" aria-hidden />}
          label="OPEN ALERTS"
          value={loading || !alerts ? '' : String(alerts.total)}
          hint={alerts ? `Latest evidence day ${alerts.day}` : 'Live fleet alert feed'}
          accent="bg-orange-500/80"
          loading={loading || !alerts}
          index={5}
          topline="#f97316"
        />
      </div>

      {/* Pipeline */}
      <section aria-label="SilentSignal pipeline" className="rise-item" style={{ '--d': '120ms' } as CSSProperties}>
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
      <div className="rise-item grid gap-4 xl:grid-cols-5" style={{ '--d': '180ms' } as CSSProperties}>
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
          <Card className="rise-item p-5" style={{ '--d': '60ms' } as CSSProperties}>
            <SectionHeader title="Fleet health" subtitle="Share of scored assets at low risk." />
            {loading ? (
              <div className="skeleton h-24 w-full rounded-xl" aria-hidden />
            ) : (
              <div className="flex items-center gap-4">
                <RiskRing score={animatedHealth} level="LOW" size={112} />
                <div>
                  <p className="tnum text-3xl font-extrabold tracking-tight text-slate-900">
                    {Math.round(animatedHealth * 100)}%
                  </p>
                  <p className="mt-1 text-xs text-slate-500">
                    {stats.low} of {stats.withRisk} scored assets stable.
                  </p>
                </div>
              </div>
            )}
          </Card>
          <Card className="p-5">
            <SectionHeader title="Fleet health overview" subtitle="Live risk distribution." />
            {loading ? (
              <div className="skeleton h-24 w-full rounded-xl" aria-hidden />
            ) : (
              <RiskDonut
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
              <p className="text-sm text-slate-600">
                <span className="text-2xl font-extrabold text-slate-900">{stats.emergingWatch}</span>{' '}
                assets show emerging or watch fusion behavior.
              </p>
            )}
          </Card>
        </div>
      </div>

      {/* Signal health + recent alerts */}
      <div className="rise-item grid gap-4 xl:grid-cols-5" style={{ '--d': '200ms' } as CSSProperties}>
        <Card className="p-5 xl:col-span-3">
          <SectionHeader
            title="Signal health"
            subtitle={`Fleet-mean abnormality per fusion signal (0–1) across ${signals[0]?.n ?? 0} scored assets.`}
          />
          {loading ? (
            <div className="skeleton h-24 w-full rounded-xl" aria-hidden />
          ) : (
            <ul className="space-y-3">
              {signals.map((s, i) => (
                <li key={s.signal}>
                  <div className="mb-1 flex items-center justify-between gap-2 text-xs">
                    <span className="font-semibold text-slate-600">{s.signal}</span>
                    <span className="tnum font-mono font-bold text-slate-900">{s.mean.toFixed(2)}</span>
                  </div>
                  <div className="h-2 overflow-hidden rounded-full bg-slate-200">
                    <div
                      className="bar-grow h-full rounded-full bg-indigo-500"
                      style={{ width: `${Math.min(100, s.mean * 100)}%`, '--d': `${i * 80}ms` } as CSSProperties}
                    />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card className="p-5 xl:col-span-2">
          <SectionHeader
            title="Recent alerts"
            subtitle={alerts ? `Latest evidence day ${alerts.day}.` : 'Live fleet alert feed.'}
            action={
              <a
                href="#/actions"
                className="inline-flex items-center gap-1 text-xs font-bold text-sky-600 hover:text-sky-700"
              >
                All actions <ArrowRight className="h-3.5 w-3.5" aria-hidden />
              </a>
            }
          />
          {alerts === null ? (
            <div className="skeleton h-24 w-full rounded-xl" aria-hidden />
          ) : alerts.items.length === 0 ? (
            <p className="text-sm text-slate-500">No alerts on the latest day.</p>
          ) : (
            <ul className="space-y-2">
              {alerts.items.map((a, i) => (
                <li
                  key={`${a.asset_external_code}-${a.alert_type}`}
                  className={i === 0 ? 'attention-ring rounded-xl text-sky-600' : undefined}
                >
                  <button
                    type="button"
                    onClick={() => navigate({ name: 'asset', code: a.asset_external_code })}
                    className="rise-item group flex w-full items-center gap-2.5 rounded-xl border border-edge bg-panel-2/60 px-3 py-2.5 text-left transition hover:border-indigo-500/40"
                    style={{ '--d': `${Math.min(i * 60, 300)}ms` } as CSSProperties}
                  >
                    <SeverityBadge severity={normalizeSeverity(a.severity)} />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-mono text-xs font-bold text-slate-900">
                        {a.asset_external_code} · {sectorLabel(a.asset_external_code)}
                      </span>
                      <span className="block truncate text-[11px] text-slate-500">{a.title}</span>
                    </span>
                    <span className="tnum shrink-0 font-mono text-xs font-extrabold text-slate-900">
                      {(a.risk_score * 100).toFixed(1)}%
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      {/* Attention list */}
      <section aria-label="Assets requiring attention" className="rise-item" style={{ '--d': '240ms' } as CSSProperties}>
        <SectionHeader
          title="Assets requiring attention"
          subtitle="Highest live risk scores across the fleet."
          action={
            <a
              href="#/assets"
              className="inline-flex items-center gap-1 text-xs font-bold text-sky-600 hover:text-sky-700"
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
            {attention.map(({ asset, risk, fusion }, i) => (
              <li key={asset.id} className="rise-item" style={{ '--d': staggerDelay(i, 50) } as CSSProperties}>
                <button
                  type="button"
                  onClick={() => navigate({ name: 'asset', code: asset.external_code })}
                  className="group block w-full text-left"
                >
                  <Card hover className="p-4">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono text-sm font-bold text-slate-900">{asset.external_code}</span>
                      {risk ? <RiskBadge level={risk.risk_level} /> : null}
                    </div>
                    <p className="mt-1 text-[11px] font-semibold text-slate-500">
                      {sectorLabel(asset.external_code)} · {asset.status.toUpperCase()} seed class
                    </p>
                    <div className="tnum mt-2 flex items-center justify-between text-xs text-slate-500">
                      <span>
                        Risk <span className="font-extrabold text-slate-900">{risk ? formatPct(risk.risk_score) : '—'}</span>
                      </span>
                      <span>
                        Anomaly <span className="font-bold text-slate-700">{risk ? risk.anomaly_score.toFixed(2) : '—'}</span>
                      </span>
                      <span>
                        Persist <span className="font-bold text-slate-700">{risk ? risk.persistence_score.toFixed(2) : '—'}</span>
                      </span>
                    </div>
                    <div className="mt-2 flex items-center justify-between">
                      {fusion ? <FusionBadge status={fusion.status} /> : <span />}
                      <span className="text-[11px] font-semibold text-sky-600 transition-transform duration-200 group-hover:translate-x-0.5">Open detail →</span>
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
