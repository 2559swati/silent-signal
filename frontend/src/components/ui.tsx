import type { CSSProperties, ReactNode } from 'react';
import {
  AlertOctagon,
  AlertTriangle,
  CheckCircle2,
  Eye,
  Info,
  Search,
} from 'lucide-react';
import type { FusionStatus, RiskLevel, Severity } from '../lib/types';
import { formatPct } from '../lib/fleet';

function baseBadge(className: string, children: ReactNode, label: string): ReactNode {
  return (
    <span
      role="status"
      aria-label={label}
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-semibold tracking-wide uppercase ${className}`}
    >
      {children}
    </span>
  );
}

const RISK_STYLE: Record<RiskLevel, string> = {
  LOW: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-600',
  MEDIUM: 'border-sky-500/30 bg-sky-500/10 text-sky-700',
  HIGH: 'border-amber-500/30 bg-amber-500/10 text-amber-700',
  CRITICAL: 'border-red-500/40 bg-red-500/10 text-red-600',
};

const RISK_DOT: Record<RiskLevel, string> = {
  LOW: 'bg-emerald-500',
  MEDIUM: 'bg-sky-500',
  HIGH: 'bg-amber-500 status-dot-calm',
  CRITICAL: 'bg-red-500 status-dot-calm',
};

export function RiskBadge({ level }: { level: RiskLevel }): ReactNode {
  const Icon =
    level === 'CRITICAL' ? AlertOctagon : level === 'HIGH' ? AlertTriangle : level === 'MEDIUM' ? Eye : CheckCircle2;
  return baseBadge(
    RISK_STYLE[level],
    <>
      <span className={`status-dot ${RISK_DOT[level]}`} aria-hidden />
      <Icon className="h-3 w-3" aria-hidden />
      {level}
    </>,
    `Risk level ${level}`,
  );
}

const FUSION_STYLE: Record<FusionStatus, string> = {
  NORMAL: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-600',
  WATCH: 'border-yellow-500/30 bg-yellow-500/10 text-yellow-700',
  EMERGING: 'border-orange-500/30 bg-orange-500/10 text-orange-700',
  CRITICAL: 'border-red-500/40 bg-red-500/10 text-red-600',
};

const FUSION_DOT: Record<FusionStatus, string> = {
  NORMAL: 'bg-emerald-500',
  WATCH: 'bg-yellow-500',
  EMERGING: 'bg-orange-500 status-dot-soft',
  CRITICAL: 'bg-red-500 status-dot-calm',
};

export function FusionBadge({ status }: { status: FusionStatus }): ReactNode {
  return baseBadge(
    FUSION_STYLE[status],
    <>
      <span className={`status-dot ${FUSION_DOT[status]}`} aria-hidden />
      {status}
    </>,
    `Fusion status ${status}`,
  );
}

const SEVERITY_STYLE: Record<Severity, string> = {
  low: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-600',
  medium: 'border-sky-500/30 bg-sky-500/10 text-sky-700',
  high: 'border-amber-500/30 bg-amber-500/10 text-amber-700',
  critical: 'border-red-500/40 bg-red-500/10 text-red-600',
};

export function SeverityBadge({ severity }: { severity: Severity }): ReactNode {
  return baseBadge(
    SEVERITY_STYLE[severity],
    <>{severity}</>,
    `Severity ${severity}`,
  );
}

export function UrgencyBadge({ urgency }: { urgency: string }): ReactNode {
  const escalated = urgency === 'escalated';
  return baseBadge(
    escalated
      ? 'border-red-500/40 bg-red-500/10 text-red-600'
      : 'border-slate-500/30 bg-slate-500/10 text-slate-600',
    <>
      {escalated ? <AlertTriangle className="h-3 w-3" aria-hidden /> : <Info className="h-3 w-3" aria-hidden />}
      {escalated ? 'ESCALATED' : 'NORMAL'}
    </>,
    `Urgency ${urgency}`,
  );
}

export function Card({
  children,
  className = '',
  hover = false,
  style,
}: {
  children: ReactNode;
  className?: string;
  hover?: boolean;
  style?: CSSProperties;
}): ReactNode {
  return (
    <div
      style={style}
      className={`rounded-2xl border border-edge bg-panel shadow-[0_8px_24px_rgba(15,23,42,0.10)] ${
        hover
          ? 'card-lift hover:-translate-y-0.5 hover:border-edge hover:bg-panel-2 hover:shadow-[0_12px_32px_rgba(15,23,42,0.16)]'
          : ''
      } ${className}`}
    >
      {children}
    </div>
  );
}

export function SectionHeader({
  title,
  subtitle,
  action,
}: {
  title: string;
  subtitle?: string;
  action?: ReactNode;
}): ReactNode {
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h2 className="text-lg font-bold tracking-tight text-slate-900">{title}</h2>
        {subtitle ? <p className="mt-0.5 text-sm text-slate-500">{subtitle}</p> : null}
      </div>
      {action}
    </div>
  );
}

export function Skeleton({ className = '' }: { className?: string }): ReactNode {
  return <div aria-hidden className={`skeleton rounded-xl ${className}`} />;
}

export function CardSkeleton({ lines = 3 }: { lines?: number; className?: string }): ReactNode {
  return (
    <Card className="p-5" >
      <Skeleton className="mb-3 h-5 w-1/3" />
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton key={i} className="mb-2 h-4 w-full last:mb-0" />
      ))}
    </Card>
  );
}

export function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}): ReactNode {
  const offline = /failed to fetch|network|abort|load failed/i.test(message);
  return (
    <Card className="flex flex-col items-center gap-3 p-10 text-center">
      <AlertOctagon className="h-10 w-10 text-red-400" aria-hidden />
      <h3 className="text-base font-bold text-slate-900">
        {offline ? 'Unable to connect to SilentSignal backend.' : 'Something went wrong.'}
      </h3>
      <p className="max-w-md text-sm text-slate-500">
        {offline
          ? 'The API at the configured backend URL is unreachable. Make sure the backend is running, then retry.'
          : message}
      </p>
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className="mt-1 rounded-lg border border-edge bg-panel-2 px-4 py-2 text-sm font-semibold text-slate-900 transition hover:border-accent/60 hover:text-accent"
        >
          Retry
        </button>
      ) : null}
    </Card>
  );
}

export function EmptyState({ message }: { message: string }): ReactNode {
  return (
    <Card className="flex flex-col items-center gap-2 p-10 text-center">
      <Search className="h-8 w-8 text-slate-600" aria-hidden />
      <p className="text-sm text-slate-500">{message}</p>
    </Card>
  );
}

export function ScoreBar({
  score,
  tone = 'accent',
}: {
  score: number;
  tone?: 'accent' | 'risk';
}): ReactNode {
  const pct = Math.max(0, Math.min(100, score * 100));
  const color =
    tone === 'risk'
      ? score >= 0.75
        ? 'bg-red-500'
        : score >= 0.5
          ? 'bg-amber-500'
          : score >= 0.3
            ? 'bg-sky-500'
            : 'bg-emerald-500'
      : 'bg-sky-500';
  return (
    <div
      className="h-1.5 w-full overflow-hidden rounded-full bg-slate-200"
      role="progressbar"
      aria-valuenow={Math.round(pct)}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={`Score ${formatPct(score)}`}
    >
      <div className={`bar-grow h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
    </div>
  );
}

const RING_COLOR: Record<string, string> = {
  LOW: '#22c55e',
  MEDIUM: '#38bdf8',
  HIGH: '#f59e0b',
  CRITICAL: '#f04452',
};

export function RiskRing({
  score,
  level,
  size = 148,
}: {
  score: number;
  level: RiskLevel;
  size?: number;
}): ReactNode {
  const stroke = 12;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const filled = Math.max(0, Math.min(1, score)) * c;
  const color = RING_COLOR[level] ?? '#38bdf8';
  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90" aria-hidden>
        <circle cx={size / 2} cy={size / 2} r={r} stroke="#e2e8f0" strokeWidth={stroke} fill="none" />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          stroke={color}
          strokeWidth={stroke}
          fill="none"
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={c - filled}
          className="animate-ring transition-all duration-700"
          style={{ filter: `drop-shadow(0 0 8px ${color}66)` }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-3xl font-extrabold tracking-tight text-slate-900">{formatPct(score)}</span>
        <span className="text-[11px] font-bold tracking-widest" style={{ color }}>
          {level}
        </span>
      </div>
    </div>
  );
}

export function StreakDots({ days, max = 12 }: { days: number; max?: number }): ReactNode {
  const shown = Math.min(days, max);
  return (
    <div className="flex items-center gap-1.5" role="img" aria-label={`${days} consecutive elevated days`}>
      {Array.from({ length: shown }).map((_, i) => (
        <span
          key={i}
          className="pop-in h-2.5 w-2.5 rounded-full bg-amber-400 shadow-[0_0_6px_rgba(245,158,11,0.8)]"
          style={{ '--d': `${Math.min(i * 60, 480)}ms` } as CSSProperties}
        />
      ))}
      {days > max ? <span className="ml-1 text-xs font-bold text-amber-700">+{days - max}</span> : null}
    </div>
  );
}
