/** Presentation helpers shared by teacher screens. Pure functions — unit-tested. */

// Muted, professional hues; every one keeps white initials at ≥ 4.5:1 contrast.
const AVATAR_COLORS = ['#2f56c4', '#0d7480', '#6d43c4', '#b2431f', '#11734f', '#a23466', '#56657c', '#8a5d00'];

/** Stable colour per child id (same child → same colour on every screen). */
export function avatarColor(id: string): string {
  let h = 0;
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) >>> 0;
  return AVATAR_COLORS[h % AVATAR_COLORS.length];
}

/** First letter (akshara-safe) of a name, or "#slot" when the name is not on this phone. */
export function avatarText(name: string, slot: number | undefined): string {
  const n = name.trim();
  if (!n) return slot === undefined ? '?' : `${slot}`;
  const seg = typeof Intl !== 'undefined' && 'Segmenter' in Intl
    ? [...new Intl.Segmenter('hi', { granularity: 'grapheme' }).segment(n)][0]?.segment
    : n[0];
  return seg ?? n[0];
}

export type SkillBand = 'known' | 'learning' | 'notyet' | 'unknown';

/**
 * Teachers see plain-language bands, never raw probabilities. Thresholds match the learner model:
 * mastery ≥ 0.8 (levels.MASTERED); < 0.5 is "not yet"; in between is "learning".
 */
export function skillBand(p: number | null | undefined): SkillBand {
  if (p === null || p === undefined) return 'unknown';
  if (p >= 0.8) return 'known';
  if (p >= 0.5) return 'learning';
  return 'notyet';
}

export const BAND_LABEL: Record<SkillBand, string> = {
  known: 'Knows',
  learning: 'Learning',
  notyet: 'Not yet',
  unknown: 'No data',
};

/** Share of a class at each rung, in ladder order (beginner first), for distribution bars. */
export function levelDistribution(
  counts: Record<string, number>,
  ladder: { id: string; name_hi: string }[],
): { id: string; name_hi: string; n: number; pct: number }[] {
  const order = [{ id: 'beginner', name_hi: 'Beginner' }, ...ladder];
  const total = Object.entries(counts).reduce((s, [k, v]) => (k === 'unassessed' ? s : s + v), 0);
  return order
    .map((r) => ({ ...r, n: counts[r.id] ?? 0 }))
    .map((r) => ({ ...r, pct: total ? Math.round((100 * r.n) / total) : 0 }));
}
