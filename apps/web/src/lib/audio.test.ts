import { describe, expect, it } from 'vitest';
import { DEFAULT_VAD, classifyRecording, meterLevel, rmsOf, runVad, vadParamsFor, type VadParams } from './audio';

const FRAME = 50;
const P: VadParams = { ...DEFAULT_VAD, noSpeechTimeoutMs: 3000, endSilenceMs: 1000, maxMs: 8000 };
const noise = (ms: number, level = 0.004) => Array.from({ length: ms / FRAME }, (_, i) => level * (1 + 0.1 * Math.sin(i)));
const speech = (ms: number, level = 0.12) => Array.from({ length: ms / FRAME }, () => level);

describe('energy VAD', () => {
  it('stops after the end-of-speech silence following speech', () => {
    const s = runVad([...noise(500), ...speech(800), ...noise(3000)], FRAME, P);
    expect(s.stop).toBe('end_of_speech');
    expect(s.started).toBe(true);
    // speech ended at 1300 ms → stop 1000 ms later
    expect(s.t).toBe(2300);
    expect(s.speechMs).toBe(800);
    expect(classifyRecording(s, P)).toBe('ok');
  });

  it('reports no_speech when the child stays silent until the timeout', () => {
    const s = runVad(noise(10_000), FRAME, P);
    expect(s.stop).toBe('no_speech');
    expect(s.t).toBe(3000);
    expect(s.started).toBe(false);
    expect(classifyRecording(s, P)).toBe('quiet');
  });

  it('caps at the max duration for long continuous speech', () => {
    const s = runVad(speech(20_000), FRAME, P);
    expect(s.stop).toBe('max_duration');
    expect(s.t).toBe(8000);
  });

  it('ignores short clicks (below the onset time)', () => {
    const frames = [...noise(300), ...speech(50, 0.3), ...noise(5000)];
    const s = runVad(frames, FRAME, P);
    expect(s.started).toBe(false);
    expect(s.stop).toBe('no_speech');
    expect(classifyRecording(s, P)).toBe('quiet');
  });

  it('pauses shorter than the hangover do not end the utterance', () => {
    const frames = [...speech(400), ...noise(600), ...speech(400), ...noise(2000)];
    const s = runVad(frames, FRAME, P);
    expect(s.stop).toBe('end_of_speech');
    expect(s.speechMs).toBe(800);
    expect(s.t).toBe(2400);
  });

  it('adapts to a noisy classroom: steady noise above the absolute floor is not speech', () => {
    const loudRoom = noise(4000, 0.03);
    const s = runVad([...loudRoom, ...speech(600, 0.2), ...noise(2000, 0.03)], FRAME, {
      ...P,
      noSpeechTimeoutMs: 6000,
    });
    expect(s.started).toBe(true);
    expect(s.firstSpeechAt).toBe(4000);
  });

  it('detects a child who starts speaking immediately (floor not learned from speech)', () => {
    const s = runVad([...speech(700), ...noise(2000)], FRAME, P);
    expect(s.started).toBe(true);
    expect(s.firstSpeechAt).toBe(0);
    expect(s.stop).toBe('end_of_speech');
    expect(classifyRecording(s, P)).toBe('ok');
  });

  it('too-quiet speech (barely above the floor) is classified as quiet', () => {
    const s = runVad([...noise(500), ...speech(150, 0.05), ...noise(4000)], FRAME, P);
    expect(classifyRecording(s, P)).toBe('quiet');
  });
});

describe('vadParamsFor', () => {
  it('uses plan rules for max seconds and the silence timeout', () => {
    const rules = { silence_timeout_s: 6, max_item_seconds: { akshara: 6, passage: 60 } };
    const ak = vadParamsFor('akshara', rules);
    expect(ak.maxMs).toBe(6000);
    expect(ak.noSpeechTimeoutMs).toBe(6000);
    expect(ak.endSilenceMs).toBe(1500);
    expect(vadParamsFor('word', rules).endSilenceMs).toBe(2000); // time to sound the word out
    const ps = vadParamsFor('passage', rules);
    expect(ps.maxMs).toBe(60_000);
    expect(ps.endSilenceMs).toBe(3000);
  });

  it('falls back to defaults without rules and never exceeds the silence timeout', () => {
    expect(vadParamsFor('word', undefined).maxMs).toBe(8000);
    expect(vadParamsFor('word', { silence_timeout_s: 1 }).endSilenceMs).toBe(1000);
  });
});

describe('helpers', () => {
  it('rms and meter level', () => {
    expect(rmsOf(new Float32Array([0.5, -0.5, 0.5, -0.5]))).toBeCloseTo(0.5);
    expect(meterLevel(0)).toBe(0);
    expect(meterLevel(1)).toBe(1);
    expect(meterLevel(0.01)).toBeGreaterThan(0);
  });
});
