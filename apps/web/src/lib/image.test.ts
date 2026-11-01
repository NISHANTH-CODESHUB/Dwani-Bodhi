import { describe, expect, it } from 'vitest';
import { fitWithin, nextQuality, shrinkFactor, TARGET_MAX_BYTES } from './image';

describe('fitWithin', () => {
  it('downscales a 12 MP landscape photo so the long side is 1600', () => {
    expect(fitWithin(4000, 3000)).toEqual({ width: 1600, height: 1200, scale: 0.4 });
  });

  it('handles portrait photos', () => {
    const r = fitWithin(3024, 4032);
    expect(r.height).toBe(1600);
    expect(r.width).toBe(1200);
  });

  it('never upscales small images', () => {
    expect(fitWithin(800, 600)).toEqual({ width: 800, height: 600, scale: 1 });
    expect(fitWithin(1600, 900)).toEqual({ width: 1600, height: 900, scale: 1 });
  });

  it('keeps aspect ratio for odd sizes and a custom max', () => {
    const r = fitWithin(1999, 1001, 1000);
    expect(r.width).toBe(1000);
    expect(r.height).toBe(Math.round(1001 * (1000 / 1999)));
  });

  it('guards against invalid input', () => {
    expect(fitWithin(0, 100)).toEqual({ width: 0, height: 0, scale: 0 });
  });
});

describe('quality / shrink math', () => {
  it('accepts sizes under the target and steps quality down otherwise', () => {
    expect(nextQuality(200 * 1024, 0.82)).toBeNull();
    expect(nextQuality(500 * 1024, 0.82)).toBe(0.72);
    expect(nextQuality(500 * 1024, 0.52)).toBeNull(); // would go below 0.45
  });

  it('shrinks dimensions in proportion to the excess bytes', () => {
    expect(shrinkFactor(TARGET_MAX_BYTES)).toBe(1);
    const f = shrinkFactor(TARGET_MAX_BYTES * 2);
    expect(f).toBeCloseTo(Math.SQRT1_2 * 0.95);
    expect(shrinkFactor(TARGET_MAX_BYTES * 100)).toBe(0.5);
  });
});
