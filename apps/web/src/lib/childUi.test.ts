import { describe, expect, it } from 'vitest';
import { journeyNodes } from '../kiosk/World';
import { avatarColor, avatarText, levelDistribution, skillBand } from './childUi';

describe('skillBand', () => {
  it('maps probabilities to plain-language bands at the learner-model thresholds', () => {
    expect(skillBand(0.8)).toBe('known');
    expect(skillBand(0.79)).toBe('learning');
    expect(skillBand(0.5)).toBe('learning');
    expect(skillBand(0.49)).toBe('notyet');
    expect(skillBand(null)).toBe('unknown');
  });
});

describe('avatar', () => {
  it('is stable per child and falls back to the ID-card number', () => {
    expect(avatarColor('abc')).toBe(avatarColor('abc'));
    expect(avatarText('', 7)).toBe('7');
    expect(avatarText('  सीमा ', 3)).toBe('सी'); // first grapheme cluster, not a bare consonant
  });
});

describe('levelDistribution', () => {
  it('orders rungs beginner-first, ignores unassessed in percentages', () => {
    const rows = levelDistribution({ beginner: 1, akshara: 3, unassessed: 6 }, [
      { id: 'akshara', name_hi: 'अक्षर' },
      { id: 'word', name_hi: 'शब्द' },
    ]);
    expect(rows.map((r) => r.id)).toEqual(['beginner', 'akshara', 'word']);
    expect(rows.map((r) => r.pct)).toEqual([25, 75, 0]);
  });
});

describe('journeyNodes', () => {
  it('compresses long sessions and never overflows', () => {
    expect(journeyNodes(0, 4)).toEqual({ shown: 4, doneShown: 0 });
    expect(journeyNodes(4, 4)).toEqual({ shown: 4, doneShown: 4 });
    expect(journeyNodes(9, 18)).toEqual({ shown: 9, doneShown: 4 });
    expect(journeyNodes(18, 18)).toEqual({ shown: 9, doneShown: 9 });
    expect(journeyNodes(50, 18).doneShown).toBe(9);
  });
});
