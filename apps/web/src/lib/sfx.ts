/**
 * Tiny synthesized sound effects for the kiosk (no audio files to download, works offline).
 * Every effect is short and soft; all are effort rewards — never right/wrong signals.
 */

let ctx: AudioContext | null = null;

function ac(): AudioContext | null {
  if (typeof window === 'undefined') return null;
  const Ctor = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!Ctor) return null;
  if (!ctx) ctx = new Ctor();
  if (ctx.state === 'suspended') void ctx.resume();
  return ctx;
}

function tone(freq: number, start: number, dur: number, type: OscillatorType = 'sine', gain = 0.12): void {
  const c = ac();
  if (!c) return;
  const t0 = c.currentTime + start;
  const o = c.createOscillator();
  const g = c.createGain();
  o.type = type;
  o.frequency.setValueAtTime(freq, t0);
  g.gain.setValueAtTime(0.0001, t0);
  g.gain.exponentialRampToValueAtTime(gain, t0 + 0.02);
  g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
  o.connect(g).connect(c.destination);
  o.start(t0);
  o.stop(t0 + dur + 0.05);
}

/** Call once from a user gesture (e.g. the Start tap) so mobile browsers allow audio. */
export function unlockSfx(): void {
  ac();
}

export const sfx = {
  /** soft pop when something appears */
  pop: () => tone(660, 0, 0.12, 'triangle', 0.08),
  /** sparkle when a star is earned */
  star: () => {
    tone(880, 0, 0.18, 'sine', 0.1);
    tone(1320, 0.08, 0.22, 'sine', 0.08);
  },
  /** gentle tap acknowledgement */
  tap: () => tone(520, 0, 0.09, 'triangle', 0.08),
  /** little fanfare at the end */
  fanfare: () => {
    [523, 659, 784, 1047].forEach((f, i) => tone(f, i * 0.13, 0.28, 'triangle', 0.1));
  },
};

export function buzz(ms = 25): void {
  try {
    navigator.vibrate?.(ms);
  } catch {
    /* not supported */
  }
}
