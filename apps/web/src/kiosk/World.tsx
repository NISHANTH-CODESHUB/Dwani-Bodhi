/** The kiosk's playful world: sky, sun, drifting clouds, rolling hills. Decorative only. */
export function World() {
  return (
    <div className="world" aria-hidden>
      <div className="sun" />
      <div className="cloud c1" />
      <div className="cloud c2" />
      <div className="cloud c3" />
      <svg className="hills" viewBox="0 0 400 120" preserveAspectRatio="none">
        <path d="M0 80 Q60 40 130 70 T260 60 T400 70 V120 H0Z" fill="#86efac" />
        <path d="M0 95 Q90 60 180 92 T400 88 V120 H0Z" fill="#4ade80" />
        <g fill="#16a34a">
          <circle cx="60" cy="86" r="10" />
          <rect x="58" y="90" width="4" height="12" fill="#92400e" />
          <circle cx="330" cy="80" r="12" />
          <rect x="328" y="86" width="4" height="14" fill="#92400e" />
        </g>
      </svg>
    </div>
  );
}

/**
 * The journey: one node per step. Finished steps become stars (effort, never correctness);
 * Cheenu sits on the current node. Long sessions are compressed to at most `max` visible nodes.
 */
export function journeyNodes(done: number, total: number, max = 9): { shown: number; doneShown: number } {
  const n = Math.max(1, total);
  const shown = Math.min(n, max);
  const doneShown = Math.min(shown, Math.floor((Math.max(0, done) * shown) / n));
  return { shown, doneShown };
}

export function Journey({ done, total, max = 9 }: { done: number; total: number; max?: number }) {
  const n = Math.max(1, total);
  const { shown, doneShown } = journeyNodes(done, total, max);
  return (
    <div className="journey" role="progressbar" aria-valuemin={0} aria-valuemax={n} aria-valuenow={done}>
      <div className="journey-line" />
      <div className="journey-line-fill" style={{ width: `${(100 * doneShown) / Math.max(1, shown - 1)}%` }} />
      {Array.from({ length: shown }, (_, i) => (
        <span
          key={i}
          className={`node ${i < doneShown ? 'node-done' : ''} ${i === doneShown ? 'node-now' : ''}`}
          style={{ left: `${shown === 1 ? 50 : (100 * i) / (shown - 1)}%` }}
        >
          {i < doneShown ? '⭐' : i === doneShown ? '🐤' : ''}
        </span>
      ))}
      <span className="journey-goal" aria-hidden>
        🏠
      </span>
    </div>
  );
}

/** Star burst shown for a moment after every finished step. */
export function StarBurst({ show }: { show: boolean }) {
  if (!show) return null;
  return (
    <div className="burst" aria-hidden>
      <span className="burst-star">⭐</span>
      {Array.from({ length: 8 }, (_, i) => (
        <span key={i} className="burst-ray" style={{ ['--a' as string]: `${i * 45}deg` }}>
          ✦
        </span>
      ))}
    </div>
  );
}

/** Lightweight CSS confetti for the end screen. */
export function Confetti() {
  const colors = ['#f43f5e', '#f59e0b', '#22c55e', '#3b82f6', '#a855f7', '#14b8a6'];
  return (
    <div className="confetti" aria-hidden>
      {Array.from({ length: 36 }, (_, i) => (
        <i
          key={i}
          style={{
            left: `${(i * 37) % 100}%`,
            background: colors[i % colors.length],
            animationDelay: `${(i % 9) * 0.18}s`,
            animationDuration: `${2.4 + (i % 5) * 0.35}s`,
            ['--r' as string]: `${(i * 53) % 360}deg`,
          }}
        />
      ))}
    </div>
  );
}
