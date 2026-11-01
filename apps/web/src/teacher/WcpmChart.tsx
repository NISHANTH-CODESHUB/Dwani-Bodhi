import { useState } from 'react';
import { formatDay } from '../i18n/hi';

/**
 * Words-correct-per-minute history: one series, 2px line, 8px markers, recessive baseline/benchmark,
 * direct label on the latest point, tap-a-point tooltip, and a screen-reader text alternative.
 */
export function WcpmChart({ points, benchmark }: { points: [string, number][]; benchmark?: number }) {
  const [active, setActive] = useState<number | null>(null);
  if (points.length === 0) return null;
  const W = 320;
  const H = 140;
  const pad = { l: 30, r: 40, t: 14, b: 22 };
  const maxV = Math.max(10, benchmark ?? 0, ...points.map((p) => p[1])) * 1.1;
  const x = (i: number) => pad.l + (points.length === 1 ? (W - pad.l - pad.r) / 2 : (i * (W - pad.l - pad.r)) / (points.length - 1));
  const y = (v: number) => pad.t + (1 - v / maxV) * (H - pad.t - pad.b);
  const path = points.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p[1]).toFixed(1)}`).join(' ');
  const last = points.length - 1;
  const a = active ?? last;

  return (
    <figure className="chart">
      <svg viewBox={`0 0 ${W} ${H}`} className="chart-svg" role="img" aria-label={points.map((p) => `${formatDay(p[0])}: ${Math.round(p[1])}`).join(', ')}>
        <line x1={pad.l} x2={W - pad.r} y1={y(0)} y2={y(0)} className="chart-axis" />
        <text x={pad.l - 6} y={y(0)} className="chart-tick" textAnchor="end" dominantBaseline="middle">
          0
        </text>
        <text x={pad.l - 6} y={y(maxV / 1.1)} className="chart-tick" textAnchor="end" dominantBaseline="middle">
          {Math.round(maxV / 1.1)}
        </text>
        {benchmark !== undefined && (
          <g>
            <line x1={pad.l} x2={W - pad.r} y1={y(benchmark)} y2={y(benchmark)} className="chart-bench" />
            <text x={W - pad.r + 4} y={y(benchmark)} className="chart-tick" dominantBaseline="middle">
              🎯 {benchmark}
            </text>
          </g>
        )}
        <path d={path} className="chart-line" />
        {points.map((p, i) => (
          <g key={i} onClick={() => setActive(i)} className="chart-hit">
            <circle cx={x(i)} cy={y(p[1])} r={14} fill="transparent" />
            <circle cx={x(i)} cy={y(p[1])} r={i === a ? 5 : 4} className="chart-dot" />
          </g>
        ))}
        <text x={x(a)} y={y(points[a][1]) - 10} textAnchor="middle" className="chart-label">
          {Math.round(points[a][1])}
        </text>
        <text x={pad.l} y={H - 6} className="chart-tick">
          {formatDay(points[0][0])}
        </text>
        {last > 0 && (
          <text x={W - pad.r} y={H - 6} className="chart-tick" textAnchor="end">
            {formatDay(points[last][0])}
          </text>
        )}
      </svg>
      {active !== null && (
        <figcaption className="muted small">
          {formatDay(points[active][0])}: {Math.round(points[active][1])}
        </figcaption>
      )}
    </figure>
  );
}
