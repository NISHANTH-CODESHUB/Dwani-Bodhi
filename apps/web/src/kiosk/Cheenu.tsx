/**
 * Cheenu, the friendly sparrow — pure SVG + CSS animation (no downloads).
 * Moods: idle (breathing + blinking), talking (beak moves), listening (leans in, sound waves react to
 * the child's voice `level`), happy (hop + wing flap + sparkles), cheer (big celebration dance).
 */
export type CheenuMood = 'idle' | 'talking' | 'listening' | 'happy' | 'cheer';

export function Cheenu({ mood = 'idle', size = 160, level = 0 }: { mood?: CheenuMood; size?: number; level?: number }) {
  const lv = Math.max(0, Math.min(1, level));
  return (
    <svg
      className={`cheenu cheenu-${mood}`}
      width={size}
      height={size}
      viewBox="0 0 200 200"
      role="img"
      aria-label="Cheenu"
      style={{ ['--lv' as string]: lv.toFixed(2) }}
    >
      <defs>
        <radialGradient id="ch-body" cx="40%" cy="35%" r="70%">
          <stop offset="0%" stopColor="#fde68a" />
          <stop offset="60%" stopColor="#facc15" />
          <stop offset="100%" stopColor="#eab308" />
        </radialGradient>
        <radialGradient id="ch-belly" cx="50%" cy="40%" r="60%">
          <stop offset="0%" stopColor="#fffbeb" />
          <stop offset="100%" stopColor="#fef3c7" />
        </radialGradient>
      </defs>
      <ellipse className="cheenu-shadow" cx="100" cy="188" rx="50" ry="7" fill="#0f172a" opacity="0.12" />
      <g className="cheenu-body">
        {/* tail */}
        <path d="M44 122 Q16 146 26 170 Q50 156 64 140 Z" fill="#eab308" />
        {/* body */}
        <circle cx="100" cy="118" r="62" fill="url(#ch-body)" />
        <ellipse cx="108" cy="142" rx="36" ry="30" fill="url(#ch-belly)" />
        {/* wings */}
        <path className="cheenu-wing cheenu-wing-back" d="M140 112 Q170 120 160 150 Q140 140 132 124 Z" fill="#eab308" />
        <path className="cheenu-wing" d="M60 108 Q44 150 92 152 Q90 120 60 108 Z" fill="#ca8a04" />
        {/* crest */}
        <path d="M88 58 Q94 36 108 50 Q112 32 122 54" stroke="#ca8a04" strokeWidth="6" fill="none" strokeLinecap="round" />
        {/* eye */}
        <g className="cheenu-eye-group">
          <circle cx="128" cy="92" r="13" fill="#fff" />
          <circle className="cheenu-eye" cx="131" cy="93" r="7" fill="#0f172a" />
          <circle cx="134" cy="89" r="2.6" fill="#fff" />
          <rect className="cheenu-lid" x="114" y="78" width="28" height="0" rx="6" fill="#facc15" />
        </g>
        {/* cheek */}
        <circle cx="142" cy="113" r="8" fill="#fb7185" opacity="0.45" />
        {/* beak */}
        <path className="cheenu-beak-top" d="M156 98 L186 106 L156 112 Z" fill="#f97316" />
        <path className="cheenu-beak-bottom" d="M156 112 L180 111 L156 119 Z" fill="#ea580c" />
        {/* feet */}
        <path d="M86 178 v-12 M114 178 v-12 M80 180 h12 M108 180 h12" stroke="#f97316" strokeWidth="5" strokeLinecap="round" />
      </g>
      {mood === 'listening' && (
        <g className="cheenu-waves" fill="none" stroke="#0ea5e9" strokeWidth="5" strokeLinecap="round">
          <path className="wave w1" d="M26 78 Q14 96 26 114" />
          <path className="wave w2" d="M12 68 Q-4 96 12 124" />
        </g>
      )}
      {(mood === 'happy' || mood === 'cheer') && (
        <g className="cheenu-sparkles" fill="#f59e0b">
          <path d="M30 40 l5 10 l10 5 l-10 5 l-5 10 l-5 -10 l-10 -5 l10 -5z" />
          <path d="M172 26 l4 8 l8 4 l-8 4 l-4 8 l-4 -8 l-8 -4 l8 -4z" />
          <path d="M178 150 l3 6 l6 3 l-6 3 l-3 6 l-3 -6 l-6 -3 l6 -3z" />
        </g>
      )}
    </svg>
  );
}
