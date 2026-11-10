import { useEffect, useState } from 'react';
import { api } from '../lib/api';
import type { CostResponse, CostUnavailable } from '../lib/types';
import { Card, CardSkeleton, EmptyState, ErrorState, SectionHeader } from '../components/ui';
import { formatPct } from '../lib/fleet';

interface Props {
  assetId: string;
}

export default function CostRecommendation({ assetId }: Props) {
  const [data, setData] = useState<CostResponse | CostUnavailable | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api
      .cost(assetId)
      .then((res) => {
        if (!cancelled) {
          setData(res);
          setError(null);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : String(err));
          setData(null);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [assetId]);

  if (loading) {
    return <CardSkeleton lines={4} className="p-5" />;
  }

  if (error) {
    return (
      <ErrorState
        message={`Failed to load cost data: ${error}`}
        onRetry={() => {
          setLoading(true);
          setError(null);
        }}
      />
    );
  }

  if (!data) {
    return null;
  }

  // Handle unavailable case
  if (!('cost_data_available' in data) || data.cost_data_available === false) {
    const detail = (data as CostUnavailable).detail ?? 'Cost data not available for this asset.';
    return <EmptyState message={detail} />;
  }

  const cost = data as CostResponse;

  const decisionBadge = (
    <span
      className={`inline-block rounded-full px-3 py-1 text-sm font-medium ${
        cost.decision === 'ACT_NOW' ? 'bg-teal-100 text-teal-800' : 'bg-amber-100 text-amber-800'
      }`}
    >
      {cost.decision.replace('_', ' ')}
    </span>
  );

  return (
    <section aria-label="Cost-aware recommendation" className="rise-item" style={{ '--d': '200ms' } as React.CSSProperties}>
      <SectionHeader title="Cost‑Aware Decision" subtitle="Economic impact of acting now vs waiting" />
      <Card className="mt-4 p-5">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-slate-900">Decision</h3>
          {decisionBadge}
        </div>
        <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
          <div>
            <dt className="font-medium text-slate-600">Risk Score</dt>
            <dd className="text-slate-800">{formatPct(cost.risk_score)}</dd>
          </div>
          <div>
            <dt className="font-medium text-slate-600">Immediate Cost (ACT NOW)</dt>
            <dd className="text-slate-800">₹{cost.cost_now.toLocaleString()}</dd>
          </div>
          <div>
            <dt className="font-medium text-slate-600">Inspection Cost</dt>
            <dd className="text-slate-800">₹{cost.inspection_cost.toLocaleString()}</dd>
          </div>
          <div>
            <dt className="font-medium text-slate-600">Planned Repair Cost</dt>
            <dd className="text-slate-800">₹{cost.planned_repair_cost.toLocaleString()}</dd>
          </div>
          <div>
            <dt className="font-medium text-slate-600">Failure Consequence Cost</dt>
            <dd className="text-slate-800">₹{cost.failure_consequence_cost.toLocaleString()}</dd>
          </div>
          <div>
            <dt className="font-medium text-slate-600">Expected Cost of Waiting</dt>
            <dd className="text-slate-800">₹{cost.expected_waiting_cost.toLocaleString()}</dd>
          </div>
          <div>
            <dt className="font-medium text-slate-600">Expected Saving</dt>
            <dd className="text-slate-800">₹{cost.expected_saving.toLocaleString()}</dd>
          </div>
          <div className="col-span-2">
            <dt className="font-medium text-slate-600">Assumptions</dt>
            <dd className="text-slate-600 italic">{cost.assumption_note}</dd>
          </div>
        </dl>
      </Card>
    </section>
  );
}
