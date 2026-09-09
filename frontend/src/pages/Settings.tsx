import { useState, type ReactNode } from 'react';
import { api } from '../lib/api';
import { Card, ErrorState, SectionHeader } from '../components/ui';
import { useFleetContext } from '../state';
import { useHealth } from '../lib/fleet';

function Row({ label, value, mono = false }: { label: string; value: string; mono?: boolean }): ReactNode {
  return (
    <div className="flex items-center justify-between gap-4 border-b border-edge-soft py-2.5 text-sm last:border-0">
      <span className="text-slate-500">{label}</span>
      <span className={`text-right font-bold text-slate-800 ${mono ? 'font-mono' : ''}`}>{value}</span>
    </div>
  );
}

export default function Settings(): ReactNode {
  const { stats, reload } = useFleetContext();
  const { ok, refresh } = useHealth();
  const [resetting, setResetting] = useState(false);
  const [resetMsg, setResetMsg] = useState<string | null>(null);
  const [resetError, setResetError] = useState<string | null>(null);

  const doReset = async (): Promise<void> => {
    if (!window.confirm('Regenerate the deterministic demo dataset and recompute all pipelines?')) return;
    setResetting(true);
    setResetMsg(null);
    setResetError(null);
    try {
      const res = await api.reset();
      setResetMsg(
        `Dataset regenerated: ${res.assets} assets, ${res.sensor_readings} readings, ${res.maintenance_records} maintenance records.`,
      );
      reload();
      refresh();
    } catch (err) {
      setResetError(err instanceof Error ? err.message : 'Reset failed');
    } finally {
      setResetting(false);
    }
  };

  return (
    <div className="space-y-4 animate-rise">
      <div className="grid gap-4 xl:grid-cols-2">
        <Card className="p-5">
          <SectionHeader title="System status" subtitle="Live backend health." />
          <Row label="Backend API" value={ok === null ? 'Checking…' : ok ? 'OPERATIONAL' : 'OFFLINE'} />
          <Row label="API base URL" value={import.meta.env.VITE_API_URL ?? 'http://localhost:8000'} mono />
          <Row label="Assets in database" value={String(stats.total)} mono />
          <div className="pt-3">
            <button
              type="button"
              onClick={refresh}
              className="rounded-lg border border-edge bg-panel-2 px-4 py-2 text-sm font-semibold text-slate-900 transition hover:border-accent/60"
            >
              Refresh status
            </button>
          </div>
        </Card>
        <Card className="p-5">
          <SectionHeader title="Engine versions" subtitle="Deterministic model versions from live responses." />
          <Row label="Anomaly (IsolationForest)" value="isolation_forest_v1" mono />
          <Row label="Fusion" value="fusion_v1" mono />
          <Row label="Risk" value="risk_v1" mono />
          <Row label="Explanation" value="explain_v1" mono />
          <Row label="Recommendations" value="recommendation_v1" mono />
        </Card>
      </div>
      <Card className="p-5">
        <SectionHeader title="Demo controls" subtitle="Developer-only dataset regeneration." />
        <p className="mb-3 max-w-2xl text-xs leading-relaxed text-slate-500">
          Regenerates the deterministic synthetic dataset and recomputes the fusion, risk,
          explanation, and recommendation pipelines. Counts are identical after every reset.
        </p>
        <button
          type="button"
          onClick={doReset}
          disabled={resetting}
          className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-2 text-sm font-bold text-amber-300 transition hover:bg-amber-500/20 disabled:opacity-50"
        >
          {resetting ? 'Resetting…' : 'POST /api/demo/reset'}
        </button>
        {resetMsg ? <p className="mt-3 text-sm font-semibold text-emerald-600">{resetMsg}</p> : null}
        {resetError ? (
          <div className="mt-3">
            <ErrorState message={resetError} onRetry={doReset} />
          </div>
        ) : null}
      </Card>
    </div>
  );
}
