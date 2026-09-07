import type { ReactNode } from 'react';
import {
  Activity,
  Eye,
  FileText,
  Gauge,
  Radio,
  Siren,
  Waves,
} from 'lucide-react';
import { Card } from './ui';

const STAGES = [
  { key: 'signals', icon: Radio, title: 'Weak Signals', desc: 'Power, brightness, maintenance & neighboring behavior' },
  { key: 'fusion', icon: Waves, title: 'Signal Fusion', desc: 'Combines multiple weak signals' },
  { key: 'anomaly', icon: Activity, title: 'Emerging Anomaly', desc: 'Detects abnormal asset behavior' },
  { key: 'risk', icon: Gauge, title: 'Risk', desc: 'Quantifies failure risk' },
  { key: 'why', icon: Eye, title: 'Explanation', desc: 'Shows why the asset is risky' },
  { key: 'action', icon: Siren, title: 'Preventive Action', desc: 'Suggests what maintenance should do' },
] as const;

export function PipelineStages({ compact = false }: { compact?: boolean }): ReactNode {
  return (
    <ol className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-6" aria-label="SilentSignal pipeline">
      {STAGES.map((stage, i) => {
        const Icon = stage.icon;
        return (
          <li key={stage.key} className="relative">
            <Card
              className={`h-full p-3.5 ${compact ? '' : 'animate-rise'}`}
            >
              <div className="flex items-center gap-2">
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-sky-500/25 bg-sky-500/10">
                  <Icon className="h-4 w-4 text-sky-400" aria-hidden />
                </span>
                <span className="text-[10px] font-bold tracking-widest text-slate-500">
                  STAGE {i + 1}
                </span>
              </div>
              <p className="mt-2 text-sm font-bold text-white">{stage.title}</p>
              <p className="mt-0.5 text-[11px] leading-snug text-slate-500">{stage.desc}</p>
            </Card>
            {i < STAGES.length - 1 ? (
              <span
                aria-hidden
                className="absolute top-1/2 -right-2 z-10 hidden h-4 w-4 translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border border-edge bg-panel text-[9px] text-sky-400 xl:flex"
              >
                ›
              </span>
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}

export interface AssetStageValue {
  label: string;
  value: string;
  tone: 'ok' | 'watch' | 'bad' | 'info';
}

const TONE_DOT: Record<AssetStageValue['tone'], string> = {
  ok: 'bg-emerald-400',
  watch: 'bg-yellow-400',
  bad: 'bg-red-400',
  info: 'bg-sky-400',
};

export function AssetPipeline({ stages }: { stages: { title: string; values: AssetStageValue[] }[] }): ReactNode {
  return (
    <ol className="grid gap-2 sm:grid-cols-2 xl:grid-cols-6" aria-label="Asset pipeline progression">
      {stages.map((stage, i) => (
        <li key={stage.title} className="relative">
          <Card className="h-full p-3.5">
            <p className="text-[10px] font-bold tracking-widest text-slate-500">
              STAGE {i + 1} · {stage.title.toUpperCase()}
            </p>
            <ul className="mt-2 space-y-1.5">
              {stage.values.map((v) => (
                <li key={v.label} className="flex items-center justify-between gap-2 text-xs">
                  <span className="flex items-center gap-1.5 text-slate-400">
                    <span className={`h-1.5 w-1.5 rounded-full ${TONE_DOT[v.tone]}`} aria-hidden />
                    {v.label}
                  </span>
                  <span className="font-bold text-slate-100">{v.value}</span>
                </li>
              ))}
            </ul>
          </Card>
        </li>
      ))}
    </ol>
  );
}

export function PipelineExplainer(): ReactNode {
  return (
    <p className="flex items-start gap-2 text-xs leading-relaxed text-slate-500">
      <FileText className="mt-0.5 h-3.5 w-3.5 shrink-0 text-sky-500" aria-hidden />
      Every stage is computed live by the backend engines — nothing on this page is hardcoded.
    </p>
  );
}
