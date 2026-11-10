import type { ReactNode } from 'react';
import {
  Activity,
  CalendarClock,
  Flame,
  Lightbulb,
  Plug,
  Users,
  Wrench,
} from 'lucide-react';
import {
  Card,
  CardSkeleton,
  EmptyState,
  ErrorState,
  FusionBadge,
  RiskBadge,
  RiskRing,
  ScoreBar,
  SectionHeader,
  SeverityBadge,
  StreakDots,
  UrgencyBadge,
} from '../components/ui';
import CostRecommendation from '../components/CostRecommendation';
import { AssetPipeline } from '../components/Pipeline';
import { useFleetContext } from '../state';
import { formatPct, formatScore, useAssetDetail } from '../lib/fleet';
import type { Severity } from '../lib/types';

const SIGNAL_ICON: Record<string, typeof Plug> = {
  power: Plug,
  brightness: Lightbulb,
  temperature: Flame,
  maintenance: Wrench,
  neighbor: Users,
  persistence: CalendarClock,
  risk: Activity,
};

function tone(score: number): 'ok' | 'watch' | 'bad' | 'info' {
  if (score >= 0.75) return 'bad';
  if (score >= 0.5) return 'bad';
  if (score >= 0.3) return 'watch';
  return 'ok';
}

const ACTION_ICON = ['Zap', 'Lightbulb', 'Thermometer', 'Wrench', 'MapPin', 'Timer'] as const;

function actionIcon(action: string, index: number): ReactNode {
  const a = action.toLowerCase();
  const Icon = a.includes('power') || a.includes('electrical')
    ? Plug
    : a.includes('lamp') || a.includes('led') || a.includes('brightness') || a.includes('dimming') || a.includes('optical')
      ? Lightbulb
      : a.includes('thermal') || a.includes('temperature')
        ? Flame
        : a.includes('maintenance') || a.includes('service inspection')
          ? Wrench
          : a.includes('adjacent') || a.includes('nearby')
            ? Users
            : a.includes('expedite') || a.includes('persist')
              ? CalendarClock
              : index === 0
                ? Activity
                : Wrench;
  void ACTION_ICON;
  return <Icon className="h-4 w-4 text-sky-600" aria-hidden />;
}

export default function AssetDetail({ code }: { code: string }): ReactNode {
  const { entries } = useFleetContext();
  const assets = entries.map((e) => e.asset);
  const detail = useAssetDetail(code, assets);
  const { asset, fusion, risk, explanation, recommendations, anomaly } = detail;

  if (!detail.loading && detail.notFound) {
    return (
      <div className="space-y-4 animate-rise">
        <h2 className="text-2xl font-extrabold text-slate-900">Asset not found.</h2>
        <EmptyState message={`No asset "${code}" exists in the monitored fleet.`} />
        <a href="#/assets" className="inline-block text-sm font-bold text-sky-600 hover:text-sky-700">
          ← Back to assets
        </a>
      </div>
    );
  }

  if (detail.loading) {
    return (
      <div className="space-y-4">
        <CardSkeleton lines={2} />
        <div className="grid gap-4 xl:grid-cols-3">
          <CardSkeleton /> <CardSkeleton /> <CardSkeleton />
        </div>
      </div>
    );
  }

  if (detail.error || !asset || !risk) {
    return (
      <div className="space-y-4">
        <ErrorState
          message={detail.error ?? 'Live evidence for this asset is unavailable.'}
          onRetry={() => window.location.reload()}
        />
        <a href="#/assets" className="inline-block text-sm font-bold text-sky-600 hover:text-sky-700">
          ← Back to assets
        </a>
      </div>
    );
  }

  const streak = Number(explanation?.evidence?.elevated_streak_days ?? 0);

  return (
    <div className="space-y-6 animate-rise">
      {/* Header */}
      <div className="flex flex-wrap items-center gap-4">
        <div className="min-w-0 flex-1">
          <p className="text-[11px] font-bold tracking-[0.22em] text-slate-500">
            STREETLIGHT · DAY {risk.day}
          </p>
          <h2 className="font-mono text-3xl font-extrabold tracking-tight text-slate-900 sm:text-4xl">
            {asset.external_code}
          </h2>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <RiskBadge level={risk.risk_level} />
            {fusion ? <FusionBadge status={fusion.status} /> : null}
            {recommendations ? <UrgencyBadge urgency={recommendations.urgency} /> : null}
          </div>
        </div>
        <Card className="flex items-center gap-5 p-5">
          <RiskRing score={risk.risk_score} level={risk.risk_level} />
          <div className="space-y-2 text-xs">
            <p className="font-bold tracking-widest text-slate-500">RISK SCORE</p>
            <Contrib label="Anomaly" value={risk.anomaly_score} />
            <Contrib label="Fusion" value={risk.fusion_score} />
            <Contrib label="Smoothed" value={risk.smoothed_fusion_score} />
            <Contrib label="Persistence" value={risk.persistence_score} />
            <p className="pt-1 text-[10px] text-slate-600">Live Phase 3–5 evidence</p>
          </div>
        </Card>
      </div>

      <p className="border-l-2 border-sky-500/60 pl-3 text-sm font-semibold text-slate-600">
        {risk.risk_level === 'CRITICAL'
          ? 'Immediate preventive attention recommended.'
          : risk.risk_level === 'HIGH'
            ? 'Preventive inspection should be prioritized.'
            : risk.risk_level === 'MEDIUM'
              ? 'A planned inspection is advisable.'
              : 'Routine monitoring is sufficient.'}
      </p>

      {/* Per-asset pipeline */}
      <section aria-label="Asset pipeline progression">
        <SectionHeader title="Signal path for this asset" subtitle="How this asset progressed through the six stages." />
        <AssetPipeline
          stages={[
            {
              title: 'Weak Signals', values: [
                { label: 'Power', value: fusion ? formatScore(fusion.power_score) : '—', tone: fusion ? tone(fusion.power_score) : 'info' },
                { label: 'Brightness', value: fusion ? formatScore(fusion.brightness_score) : '—', tone: fusion ? tone(fusion.brightness_score) : 'info' },
                { label: 'Neighbor', value: fusion ? formatScore(fusion.neighbor_score) : '—', tone: fusion ? tone(fusion.neighbor_score) : 'info' },
              ],
            },
            {
              title: 'Signal Fusion', values: [
                { label: 'Raw', value: fusion ? formatScore(fusion.fusion_score) : '—', tone: fusion ? tone(fusion.fusion_score) : 'info' },
                { label: 'Smoothed', value: fusion ? formatScore(fusion.smoothed_fusion_score) : '—', tone: fusion ? tone(fusion.smoothed_fusion_score) : 'info' },
              ],
            },
            {
              title: 'Anomaly', values: [
                { label: 'IsolationForest', value: anomaly ? formatScore(anomaly.score) : risk.anomaly_score.toFixed(2), tone: (anomaly?.score ?? risk.anomaly_score) >= 0.5 ? 'bad' : 'ok' },
              ],
            },
            {
              title: 'Risk', values: [
                { label: 'Score', value: formatPct(risk.risk_score), tone: risk.risk_level === 'LOW' ? 'ok' : risk.risk_level === 'MEDIUM' ? 'watch' : 'bad' },
                { label: 'Persist', value: risk.persistence_score.toFixed(2), tone: tone(risk.persistence_score) },
              ],
            },
            {
              title: 'Explanation', values: [
                { label: 'Factors', value: explanation ? String(explanation.factors.length) : '—', tone: 'info' },
                { label: 'Model', value: explanation?.model_version ?? '—', tone: 'info' },
              ],
            },
            {
              title: 'Action', values: [
                { label: 'Priority', value: recommendations ? recommendations.priority : '—', tone: recommendations && recommendations.urgency === 'escalated' ? 'bad' : 'info' },
                { label: 'Steps', value: recommendations ? String(recommendations.recommendations.length) : '—', tone: 'info' },
              ],
            },
          ]}
        />
      </section>

      {/* WHY hero */}
      <section aria-label="Why is this asset at risk" className="rise-item" style={{ '--d': '120ms' } as React.CSSProperties}>
        <h2 className="text-xl font-extrabold tracking-tight text-slate-900 sm:text-2xl">WHY IS THIS ASSET AT RISK?</h2>
        <p className="mt-1 max-w-3xl text-sm text-slate-500">
          SilentSignal combines multiple weak signals instead of relying on a single abnormal reading.
          {explanation ? ` ${explanation.summary}` : ''}
        </p>
        <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {explanation ? (
            explanation.factors.map((f, i) => {
              const Icon = SIGNAL_ICON[f.signal] ?? Activity;
              return (
                <Card key={f.signal} className="rise-item card-lift p-4 hover:-translate-y-0.5" style={{ '--d': `${Math.min(i * 70, 350)}ms` } as React.CSSProperties}>
                  <div className="flex items-center justify-between gap-2">
                    <span className="flex items-center gap-2">
                      <span className="flex h-8 w-8 items-center justify-center rounded-lg border border-edge bg-panel-2">
                        <Icon className="h-4 w-4 text-sky-600" aria-hidden />
                      </span>
                      <span className="text-xs font-bold tracking-widest text-slate-500 uppercase">
                        {f.signal === 'temperature' ? 'Temperature behavior' : f.signal === 'neighbor' ? 'Neighbor correlation' : f.signal}
                      </span>
                    </span>
                    <SeverityBadge severity={f.severity as Severity} />
                  </div>
                  <p className="mt-2 font-mono text-2xl font-extrabold text-slate-900">{formatPct(f.score)}</p>
                  <ScoreBar score={f.score} tone="risk" />
                  <p className="mt-2 text-xs leading-relaxed text-slate-500">{f.reason}</p>
                </Card>
              );
            })
          ) : (
            <EmptyState message="Explanation evidence is unavailable for this asset." />
          )}
        </div>
      </section>

      {/* Persistence */}
      <Card className="rise-item p-5" style={{ '--d': '180ms' } as React.CSSProperties}>
        <SectionHeader title="Sustained behavior" subtitle="Elevated behavior over consecutive days (live evidence)." />
        {explanation ? (
          <div className="flex flex-wrap items-center gap-4">
            <StreakDots days={streak} />
            <p className="text-sm text-slate-600">
              Elevated behavior sustained for{' '}
              <span className="font-extrabold text-slate-900">{streak} day{streak === 1 ? '' : 's'}</span>
              {risk.persistence_score > 0 ? (
                <span className="text-slate-500"> · persistence score {risk.persistence_score.toFixed(2)}</span>
              ) : null}
            </p>
          </div>
        ) : (
          <EmptyState message="Persistence evidence is unavailable." />
        )}
      </Card>

      {/* Cost-Aware Recommendation */}
      <CostRecommendation assetId={asset.id} />

      {/* Preventive action hero */}
      <section aria-label="Preventive action" className="rise-item" style={{ '--d': '240ms' } as React.CSSProperties}>
        <h2 className="text-xl font-extrabold tracking-tight text-slate-900 sm:text-2xl">PREVENTIVE ACTION</h2>
        <p className="mt-1 text-sm text-slate-500">What should the maintenance team do next?</p>
        {recommendations ? (
          <Card className="mt-4 border-sky-500/25 p-5">
            <div className="flex flex-wrap items-center gap-2">
              <RiskBadge level={risk.risk_level} />
              <span className="text-sm font-bold text-slate-900">
                Priority: {recommendations.priority}
              </span>
              <UrgencyBadge urgency={recommendations.urgency} />
              <span className="ml-auto text-[11px] text-slate-500">{recommendations.model_version}</span>
            </div>
            <ul className="mt-4 space-y-2.5">
              {recommendations.recommendations.map((rec, i) => (
                <li
                  key={i}
                  className={`rise-item flex items-start gap-3 rounded-xl border p-3 ${
                    i === 0 ? 'border-sky-500/30 bg-sky-500/[0.07]' : 'border-edge bg-panel-2/60'
                  }`}
                  style={{ '--d': `${Math.min(i * 60, 300)}ms` } as React.CSSProperties}
                >
                  <span className="mt-0.5">{actionIcon(rec.action, i)}</span>
                  <span>
                    <span className="block text-sm font-bold text-slate-900">{rec.action}</span>
                    <span className="mt-0.5 block text-xs leading-relaxed text-slate-500">{rec.reason}</span>
                  </span>
                </li>
              ))}
            </ul>
          </Card>
        ) : (
          <div className="mt-4">
            <EmptyState message="Recommendation evidence is unavailable for this asset." />
          </div>
        )}
      </section>

      <a href="#/assets" className="inline-block text-sm font-bold text-sky-600 hover:text-sky-700">
        ← Back to assets
      </a>
    </div>
  );
}

function Contrib({ label, value }: { label: string; value: number }): React.ReactNode {
  return (
    <div className="flex items-center justify-between gap-6">
      <span className="text-slate-500">{label}</span>
      <span className="font-mono font-bold text-slate-700">{formatPct(value)}</span>
    </div>
  );
}
