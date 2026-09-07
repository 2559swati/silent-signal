import type { ReactNode } from 'react';
import { gridPosition, type FleetEntry } from '../lib/fleet';
import type { FusionStatus } from '../lib/types';
import { navigate } from '../lib/router';

const NODE_FILL: Record<FusionStatus, string> = {
  NORMAL: '#22c55e',
  WATCH: '#eab308',
  EMERGING: '#f97316',
  CRITICAL: '#f04452',
};

function statusOf(entry: FleetEntry): FusionStatus {
  return entry.fusion?.status ?? 'NORMAL';
}

// Stylized streetlight network: the documented 10x10 row-major grid
// (SL-1001..SL-1100). Honest schematic -- no GPS claims.
export default function NetworkGrid({
  entries,
  highlight,
}: {
  entries: FleetEntry[];
  highlight?: string;
}): ReactNode {
  const byCode = new Map(entries.map((e) => [e.asset.external_code, e]));
  const cells: { code: string; row: number; col: number; entry: FleetEntry | undefined }[] = [];
  for (let n = 1001; n <= 1100; n++) {
    const code = `SL-${n}`;
    const pos = gridPosition(code);
    if (!pos) continue;
    cells.push({ code, row: pos.row, col: pos.col, entry: byCode.get(code) });
  }
  const size = 560;
  const pad = 18;
  const step = (size - pad * 2) / 9;
  const criticalCount = cells.filter((c) => c.entry && statusOf(c.entry) === 'CRITICAL').length;

  return (
    <div>
      <svg
        viewBox={`0 0 ${size} ${size}`}
        className="h-auto w-full"
        role="img"
        aria-label={`Streetlight network schematic, 100 assets, ${criticalCount} critical`}
      >
        {/* street lines */}
        {Array.from({ length: 10 }).map((_, i) => (
          <g key={i} stroke="#1a2230" strokeWidth={i % 3 === 0 ? 3 : 1.2}>
            <line x1={pad} y1={pad + i * step} x2={size - pad} y2={pad + i * step} />
            <line x1={pad + i * step} y1={pad} x2={pad + i * step} y2={size - pad} />
          </g>
        ))}
        {cells.map(({ code, row, col, entry }) => {
          const cx = pad + col * step;
          const cy = pad + row * step;
          const st = entry ? statusOf(entry) : 'NORMAL';
          const fill = NODE_FILL[st];
          const isHl = highlight === code;
          const risk = entry?.risk?.risk_score ?? 0;
          const r = 5 + risk * 5;
          return (
            <g key={code}>
              {st === 'CRITICAL' ? (
                <circle cx={cx} cy={cy} r={r + 5} fill={fill} opacity={0.18}>
                  <animate attributeName="opacity" values="0.25;0.08;0.25" dur="2.2s" repeatCount="indefinite" />
                </circle>
              ) : null}
              <a
                href={`#/asset/${code}`}
                onClick={(e) => {
                  e.preventDefault();
                  navigate({ name: 'asset', code });
                }}
                aria-label={`${code}, fusion ${st}${entry?.risk ? `, risk ${entry.risk.risk_level} ${Math.round(entry.risk.risk_score * 100)} percent` : ''}`}
              >
                <circle
                  cx={cx}
                  cy={cy}
                  r={isHl ? r + 2 : r}
                  fill={fill}
                  opacity={entry ? 0.95 : 0.35}
                  stroke={isHl ? '#fff' : 'rgba(0,0,0,0.5)'}
                  strokeWidth={isHl ? 2 : 1}
                  style={{ cursor: 'pointer' }}
                >
                  <title>{`${code} · ${st}`}</title>
                </circle>
              </a>
            </g>
          );
        })}
      </svg>
      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] font-semibold text-slate-400" aria-label="Legend">
        {(['NORMAL', 'WATCH', 'EMERGING', 'CRITICAL'] as FusionStatus[]).map((s) => (
          <span key={s} className="inline-flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full" style={{ background: NODE_FILL[s] }} aria-hidden />
            {s}
          </span>
        ))}
        <span className="text-slate-600">Node size = live risk score · Stylized street grid, not GPS</span>
      </div>
    </div>
  );
}
