import { useContext, useState, type ReactNode } from 'react';
import {
  Activity,
  FileText,
  Gauge,
  LayoutDashboard,
  Map as MapIcon,
  Menu,
  Network,
  Search,
  Settings,
  ShieldCheck,
  Siren,
  X,
  Zap,
} from 'lucide-react';
import { routeHref, type Route } from '../lib/router';
import { useHealth, useTeeMode } from '../lib/fleet';
import { FleetContext } from '../state';

const NAV: { route: Route; label: string; icon: typeof LayoutDashboard; desc: string }[] = [
  { route: { name: 'dashboard' }, label: 'Dashboard', icon: LayoutDashboard, desc: 'Fleet overview' },
  { route: { name: 'assets' }, label: 'Assets', icon: Network, desc: 'Streetlight inventory' },
  { route: { name: 'risk' }, label: 'Risk Monitor', icon: Gauge, desc: 'Risk distribution' },
  { route: { name: 'explanations' }, label: 'Explanations', icon: FileText, desc: 'Why assets are risky' },
  { route: { name: 'actions' }, label: 'Preventive Actions', icon: Siren, desc: 'Maintenance actions' },
  { route: { name: 'map' }, label: 'Map', icon: MapIcon, desc: 'Fleet geography' },
  { route: { name: 'security' }, label: 'Security', icon: ShieldCheck, desc: 'TEE & attestation' },
];

const TITLES: Record<string, { title: string; subtitle: string }> = {
  dashboard: { title: 'Operations Dashboard', subtitle: 'Live fleet status across the SilentSignal pipeline.' },
  assets: { title: 'Assets', subtitle: 'Every monitored streetlight, ranked by live risk.' },
  asset: { title: 'Asset Detail', subtitle: 'Full evidence trail for one asset.' },
  risk: { title: 'Risk Monitor', subtitle: 'Where is failure risk concentrated right now?' },
  explanations: { title: 'Explanations', subtitle: 'Why is SilentSignal flagging these assets?' },
  actions: { title: 'Preventive Action Center', subtitle: 'What should the maintenance team do next?' },
  map: { title: 'Infrastructure Map', subtitle: 'Fleet geography with live status.' },
  security: { title: 'Security', subtitle: 'TEE provider status and attestation state.' },
  settings: { title: 'Settings & System Status', subtitle: 'Backend health, engine versions, demo controls.' },
};

function Wordmark(): ReactNode {
  return (
    <a href="#/" className="flex items-center gap-2.5" aria-label="SilentSignal AI home">
      <span className="brand-tile flex h-9 w-9 items-center justify-center rounded-xl">
        <Zap className="h-5 w-5 text-white" aria-hidden />
      </span>
      <span className="leading-tight">
        <span className="block text-[15px] font-extrabold tracking-tight text-slate-900">SilentSignal AI</span>
        <span className="block text-[10px] font-medium tracking-[0.18em] text-slate-500 uppercase">Ops Center</span>
      </span>
    </a>
  );
}

function HealthPill(): ReactNode {
  const { ok } = useHealth();
  const label = ok === null ? 'CHECKING' : ok ? 'API CONNECTED' : 'BACKEND OFFLINE';
  const cls =
    ok === null
      ? 'border-slate-500/30 bg-slate-500/10 text-slate-500'
      : ok
        ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-600'
        : 'border-red-500/40 bg-red-500/10 text-red-600';
  return (
    <span
      role="status"
      aria-label={ok === null ? 'Checking backend status' : ok ? 'Backend connected' : 'Backend offline'}
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] font-bold tracking-widest ${cls}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${ok ? 'bg-emerald-400 animate-pulse-dot' : ok === null ? 'bg-slate-400' : 'bg-red-400'}`} />
      {label}
    </span>
  );
}

function LiveEvidenceClicker(): ReactNode {
  // Null-safe: Shell is normally inside FleetProvider (see App.tsx), but the
  // button degrades to a health-only refresh wherever the context is absent.
  const fleet = useContext(FleetContext);
  const { refresh } = useHealth();
  const loading = fleet?.loading ?? false;
  return (
    <button
      type="button"
      onClick={() => {
        fleet?.reload();
        refresh();
      }}
      title="Reload live evidence now"
      aria-label={loading ? 'Refreshing live evidence' : 'Reload live evidence now'}
      aria-live="polite"
      className="hidden cursor-pointer items-center gap-1.5 rounded-full border border-edge bg-panel px-3 py-1.5 text-[11px] font-semibold text-slate-500 transition hover:border-indigo-500/40 hover:text-slate-900 md:inline-flex"
    >
      <Activity
        className={`h-3.5 w-3.5 text-sky-600 ${loading ? 'animate-spin' : ''}`}
        aria-hidden
      />
      {loading ? 'REFRESHING…' : 'LIVE EVIDENCE'}
    </button>
  );
}

function HeaderStatusCluster(): ReactNode {
  // Live operational facts only: fleet critical count + backend TEE mode.
  // Null-safe outside FleetProvider; pills simply hide until data arrives.
  const fleet = useContext(FleetContext);
  const mode = useTeeMode();
  const critical = fleet?.stats.critical;
  return (
    <span className="hidden items-center gap-2 lg:inline-flex">
      {typeof critical === 'number' ? (
        <a
          href="#/actions"
          title="Assets at critical risk right now (live)"
          aria-label={`${critical} assets at critical risk`}
          className="inline-flex items-center gap-1.5 rounded-full border border-edge bg-panel px-3 py-1.5 text-[11px] font-semibold text-slate-500 transition hover:text-slate-900"
        >
          <span className={`status-dot ${critical > 0 ? 'bg-red-500 status-dot-calm' : 'bg-emerald-500'}`} aria-hidden />
          {critical} CRITICAL
        </a>
      ) : null}
      {mode ? (
        <a
          href="#/security"
          title="Live TEE provider mode from the backend"
          aria-label={`TEE mode ${mode}`}
          className="inline-flex items-center gap-1.5 rounded-full border border-edge bg-panel px-3 py-1.5 text-[11px] font-semibold text-slate-500 transition hover:text-slate-900"
        >
          <span className="status-dot bg-indigo-500" aria-hidden />
          TEE · {mode.toUpperCase()}
        </a>
      ) : null}
    </span>
  );
}

function SidebarContent({ route, onNavigate }: { route: Route; onNavigate: () => void }): ReactNode {
  const active = (name: string): boolean =>
    route.name === name || (name === 'assets' && route.name === 'asset');
  return (
    <div className="flex h-full flex-col">
      <div className="px-5 pt-5">
        <Wordmark />
      </div>
      <nav className="scroll-fade scroll-thin mt-6 min-h-0 flex-1 space-y-1 overflow-y-auto px-3 pb-4" aria-label="Primary">
        {NAV.map((item) => {
          const isActive =
            item.route.name === route.name || (item.route.name === 'assets' && route.name === 'asset');
          const Icon = item.icon;
          return (
            <a
              key={item.label}
              href={routeHref(item.route)}
              onClick={onNavigate}
              aria-current={isActive ? 'page' : undefined}
              className={`group flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition-all duration-200 ease-out ${
                isActive
                  ? 'nav-active nav-enter text-slate-900'
                  : 'border border-transparent text-slate-500 hover:bg-slate-900/[0.04] hover:text-slate-900'
              }`}
            >
              <Icon
                className={`h-[18px] w-[18px] transition-transform duration-200 ease-out group-hover:translate-x-0.5 group-hover:scale-110 ${
                  isActive ? 'text-sky-600' : 'text-slate-500 group-hover:text-slate-700'
                }`}
                aria-hidden
              />
              <span className="leading-tight">
                <span className="block font-semibold transition-colors duration-200 group-hover:text-slate-900">{item.label}</span>
                <span className="block text-[11px] font-normal text-slate-500 transition-colors duration-200 group-hover:text-slate-600">{item.desc}</span>
              </span>
            </a>
          );
        })}
        {/* Spacer lets the list scroll naturally past the viewport. */}
        <div className="px-3 pt-2 text-[10px] leading-relaxed text-slate-500">
          SilentSignal pipeline
          <br />
          signals → fusion → risk
        </div>
      </nav>
      <div className="space-y-3 px-5 pb-5">
        <a
          href="#/settings"
          onClick={onNavigate}
          className={`flex items-center gap-2 text-xs font-semibold transition ${active('settings') ? 'text-slate-900' : 'text-slate-500 hover:text-slate-600'}`}
        >
          <Settings className="h-3.5 w-3.5" aria-hidden /> Settings / System Status
        </a>
        <HealthPill />
        <p className="text-[10px] leading-relaxed text-slate-600">
          Phases 3–7 engines live.
          <br />
          Evidence: real API data only.
        </p>
      </div>
    </div>
  );
}

export default function Shell({
  route,
  onSearch,
  searchValue,
  children,
}: {
  route: Route;
  onSearch?: (value: string) => void;
  searchValue?: string;
  children: ReactNode;
}): ReactNode {
  const [open, setOpen] = useState(false);
  const meta = TITLES[route.name] ?? TITLES.dashboard;
  return (
    <div className="min-h-screen bg-abyss text-slate-700">
      {/* Desktop sidebar */}
      <aside className="fixed inset-y-0 left-0 hidden w-64 border-r border-edge bg-panel/80 backdrop-blur lg:block">
        <SidebarContent route={route} onNavigate={() => {}} />
      </aside>
      {/* Mobile drawer */}
      {open ? (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="Navigation">
          <div className="absolute inset-0 bg-black/70" onClick={() => setOpen(false)} />
          <aside className="absolute inset-y-0 left-0 w-72 border-r border-edge bg-panel">
            <div className="flex justify-end p-3">
              <button
                type="button"
                onClick={() => setOpen(false)}
                aria-label="Close navigation"
                className="rounded-lg p-2 text-slate-500 hover:bg-slate-900/5 hover:text-slate-900"
              >
                <X className="h-5 w-5" aria-hidden />
              </button>
            </div>
            <SidebarContent route={route} onNavigate={() => setOpen(false)} />
          </aside>
        </div>
      ) : null}

      <div className="lg:pl-64">
        <header className="sticky top-0 z-30 border-b border-edge bg-abyss/85 backdrop-blur">
          <div className="mx-auto flex max-w-7xl items-center gap-3 px-4 py-3 sm:px-6">
            <button
              type="button"
              className="rounded-lg p-2 text-slate-500 hover:bg-slate-900/5 hover:text-slate-900 lg:hidden"
              onClick={() => setOpen(true)}
              aria-label="Open navigation"
            >
              <Menu className="h-5 w-5" aria-hidden />
            </button>
            <div className="min-w-0 flex-1">
              <h1 className="truncate text-base font-bold tracking-tight text-slate-900 sm:text-lg">{meta.title}</h1>
              <p className="hidden truncate text-xs text-slate-500 sm:block">{meta.subtitle}</p>
            </div>
            {onSearch ? (
              <label className="relative hidden items-center sm:flex" aria-label="Search assets">
                <Search className="pointer-events-none absolute left-3 h-4 w-4 text-slate-500" aria-hidden />
                <input
                  value={searchValue ?? ''}
                  onChange={(e) => onSearch(e.target.value)}
                  placeholder="Search SL-…"
                  className="w-44 rounded-xl border border-edge bg-panel py-2 pl-9 pr-3 text-sm text-slate-900 placeholder:text-slate-600 focus:border-sky-500/60 focus:outline-none"
                />
              </label>
            ) : null}
            <HeaderStatusCluster />
            <LiveEvidenceClicker />
          </div>
        </header>
        <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
          <div key={route.name === 'asset' ? `asset-${route.code}` : route.name} className="page-enter">
            {children}
          </div>
        </main>
      </div>
    </div>
  );
}
