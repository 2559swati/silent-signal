import { useEffect, useState, type ReactNode } from 'react';
import { ShieldAlert, ShieldCheck } from 'lucide-react';
import { Card, ErrorState } from '../components/ui';
import { api } from '../lib/api';
import type { AttestationStatus, TEEStatus } from '../lib/types';

function Row({ label, value, mono = false }: { label: string; value: string; mono?: boolean }): ReactNode {
  return (
    <div className="flex items-center justify-between gap-4 border-b border-edge-soft py-2.5 text-sm last:border-0">
      <span className="text-slate-500">{label}</span>
      <span className={`text-right font-bold text-slate-800 ${mono ? 'font-mono' : ''}`}>{value}</span>
    </div>
  );
}

export default function Security(): ReactNode {
  const [status, setStatus] = useState<TEEStatus | null>(null);
  const [attestation, setAttestation] = useState<AttestationStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.teeStatus(), api.attestation()])
      .then(([s, a]) => {
        if (!cancelled) {
          setStatus(s);
          setAttestation(a);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load security status');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const isDemo = status?.mode === 'demo';

  return (
    <div className="space-y-4 animate-rise">
      <div>
        <h2 className="text-xl font-extrabold tracking-tight text-slate-900 sm:text-2xl">Security</h2>
        <p className="mt-1 max-w-3xl text-sm text-slate-500">
          Trusted-execution status for the SilentSignal analysis plane, served live by the backend
          TEE provider abstraction.
        </p>
      </div>

      {loading ? (
        <Card className="p-5">
          <div className="skeleton mb-2 h-8 w-1/3 rounded-xl" aria-hidden />
          <div className="skeleton h-4 w-full rounded" aria-hidden />
        </Card>
      ) : error || !status || !attestation ? (
        <ErrorState message={error ?? 'Security status is unavailable.'} onRetry={() => window.location.reload()} />
      ) : (
        <>
          {isDemo ? (
            <div
              role="alert"
              aria-label="Demo mode warning"
              className="rise-item flex items-center gap-3 rounded-2xl border-2 border-amber-400 bg-amber-500/15 px-5 py-4 shadow-[0_8px_24px_rgba(245,158,11,0.25)]"
            >
              <ShieldAlert className="h-8 w-8 shrink-0 text-amber-600" aria-hidden />
              <div>
                <p className="text-2xl font-extrabold tracking-[0.12em] text-amber-700">DEMO MODE</p>
                <p className="mt-0.5 text-sm font-semibold text-amber-800">
                  Attestation: NOT ATTESTED — this environment is running the Demo TEE provider.
                  Real hardware-backed attestation is not active.
                </p>
              </div>
            </div>
          ) : null}

          <div className="grid gap-4 xl:grid-cols-2">
            <Card className="p-5">
              <h3 className="mb-1 flex items-center gap-2 text-base font-bold text-slate-900">
                <ShieldCheck className="h-4 w-4 text-sky-600" aria-hidden />
                Provider status
              </h3>
              <Row label="Mode" value={status.mode} mono />
              <Row label="Healthy" value={status.healthy ? 'Yes' : 'No'} />
              <Row label="Details" value={status.description} />
            </Card>
            <Card className="p-5">
              <h3 className="mb-1 text-base font-bold text-slate-900">Attestation state</h3>
              <Row label="Attested" value={attestation.attested ? 'Yes' : 'No'} mono />
              <Row label="PCR0" value={attestation.pcr0 ?? 'null'} mono />
              {attestation.attested ? (
                <p className="mt-3 flex items-center gap-2 text-sm font-bold text-emerald-600">
                  <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden>
                    <circle cx="10" cy="10" r="9" stroke="currentColor" strokeWidth="2" opacity="0.35" />
                    <path
                      className="check-draw"
                      d="M6.5 10.2l2.4 2.4 4.6-5"
                      stroke="currentColor"
                      strokeWidth="2.2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                  Hardware attested
                </p>
              ) : (
                <p className="mt-3 flex items-center gap-2 text-sm font-semibold text-slate-500">
                  <ShieldAlert className="h-4 w-4 text-amber-500" aria-hidden />
                  Not attested — no hardware verification claimed.
                </p>
              )}
              <p className="mt-3 text-xs leading-relaxed text-slate-500">
                Provider health means the analysis adapter is functioning. It does not imply
                hardware-backed trust. Only a hardware attested environment may report attested
                status.
              </p>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
