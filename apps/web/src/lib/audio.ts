/**
 * Microphone capture for the kiosk: MediaRecorder (Opus/WebM preferred, 16 kHz mono constraints) plus an
 * energy-based voice-activity detector that runs on WebAudio RMS frames. The VAD itself is a pure state
 * machine (`vadStep`) so it is unit-testable on synthetic energy frames.
 */

// ------------------------------------------------------------------------------- pure VAD
export interface VadParams {
  /** Stop when no speech has started within this time (child silent). */
  noSpeechTimeoutMs: number;
  /** Stop after this much continuous silence following speech (end of utterance). */
  endSilenceMs: number;
  /** Hard cap for the item type. */
  maxMs: number;
  /** Absolute RMS floor for speech (linear, 0..1). */
  minSpeechRms: number;
  /** Speech when RMS > noiseFloor × this ratio (and above minSpeechRms). */
  noiseRatio: number;
  /** Continuous speech needed before we consider speech to have started (debounces clicks). */
  onsetMs: number;
  /** Total speech below which a recording is "too quiet / no response". */
  minTotalSpeechMs: number;
  /**
   * Cap for the initial noise-floor estimate (taken from the first frame). Prevents a child who starts
   * speaking immediately from being learned as "background"; the floor still adapts upward slowly.
   */
  maxInitialFloor: number;
}

export const DEFAULT_VAD: VadParams = {
  noSpeechTimeoutMs: 6000,
  endSilenceMs: 1200,
  maxMs: 8000,
  minSpeechRms: 0.015,
  noiseRatio: 3,
  onsetMs: 120,
  minTotalSpeechMs: 250,
  maxInitialFloor: 0.02,
};

export type VadStop = 'end_of_speech' | 'no_speech' | 'max_duration';

export interface VadState {
  t: number; // ms since start
  noiseFloor: number;
  started: boolean;
  runMs: number; // current continuous speech run
  speechMs: number; // total speech
  firstSpeechAt: number | null;
  lastSpeechAt: number | null;
  peakRms: number;
  stop: VadStop | null;
}

export function initVad(): VadState {
  return {
    t: 0,
    noiseFloor: -1,
    started: false,
    runMs: 0,
    speechMs: 0,
    firstSpeechAt: null,
    lastSpeechAt: null,
    peakRms: 0,
    stop: null,
  };
}

export function speechThreshold(noiseFloor: number, p: VadParams): number {
  return Math.max(p.minSpeechRms, Math.max(noiseFloor, 0) * p.noiseRatio);
}

/** Feeds one RMS frame of `frameMs` duration. Returns the new state; `stop` is set once a stop rule fires. */
export function vadStep(s: VadState, rms: number, frameMs: number, p: VadParams): VadState {
  if (s.stop) return s;
  const t = s.t + frameMs;
  let noiseFloor = s.noiseFloor < 0 ? Math.min(rms, p.maxInitialFloor) : s.noiseFloor;
  const isSpeech = rms > speechThreshold(noiseFloor, p);
  if (!isSpeech) {
    // Track the background: fall fast, rise slowly (so speech doesn't inflate the floor).
    noiseFloor = rms < noiseFloor ? rms : noiseFloor + 0.05 * (rms - noiseFloor);
  }
  const runMs = isSpeech ? s.runMs + frameMs : 0;
  let { started, firstSpeechAt, lastSpeechAt, speechMs } = s;
  if (isSpeech) {
    speechMs += frameMs;
    lastSpeechAt = t;
    if (!started && runMs >= p.onsetMs) {
      started = true;
      firstSpeechAt = t - runMs;
    }
  }
  let stop: VadStop | null = null;
  if (t >= p.maxMs) stop = 'max_duration';
  else if (!started && t >= p.noSpeechTimeoutMs) stop = 'no_speech';
  else if (started && lastSpeechAt !== null && t - lastSpeechAt >= p.endSilenceMs) stop = 'end_of_speech';
  return { t, noiseFloor, started, runMs, speechMs, firstSpeechAt, lastSpeechAt, peakRms: Math.max(s.peakRms, rms), stop };
}

/** Runs the VAD over a whole array of frames (used by tests and for offline analysis). */
export function runVad(frames: number[], frameMs: number, p: VadParams): VadState {
  let s = initVad();
  for (const f of frames) {
    s = vadStep(s, f, frameMs, p);
    if (s.stop) break;
  }
  return s;
}

/** "ok": usable speech; "quiet": no/too little speech → ask the child to speak louder (once). */
export function classifyRecording(s: VadState, p: VadParams): 'ok' | 'quiet' {
  return s.started && s.speechMs >= p.minTotalSpeechMs ? 'ok' : 'quiet';
}

/** VAD parameters for an item type from the server plan rules (`silence_timeout_s`, `max_item_seconds`). */
export function vadParamsFor(
  type: string,
  rules: { silence_timeout_s?: number; max_item_seconds?: Partial<Record<string, number>> } | undefined,
): VadParams {
  const silenceMs = (rules?.silence_timeout_s ?? 6) * 1000;
  const defaultsMax: Record<string, number> = { akshara: 6, word: 8, nonword: 8, repeat: 8, passage: 60 };
  const maxMs = (rules?.max_item_seconds?.[type] ?? defaultsMax[type] ?? 10) * 1000;
  // End-of-utterance hangover. Early readers sound words out (क… म… ल… कमल) with pauses between
  // sounds, so words wait longer than letters; passages have natural pauses between words.
  const hangovers: Record<string, number> = { akshara: 1500, repeat: 1500, word: 2000, nonword: 2000, passage: 3000 };
  const hangover = hangovers[type] ?? 1500;
  return {
    ...DEFAULT_VAD,
    noSpeechTimeoutMs: Math.min(silenceMs, maxMs),
    endSilenceMs: Math.min(silenceMs, hangover),
    maxMs,
  };
}

export function rmsOf(buf: Float32Array): number {
  let sum = 0;
  for (let i = 0; i < buf.length; i++) sum += buf[i] * buf[i];
  return Math.sqrt(sum / Math.max(1, buf.length));
}

/** Meter level 0..1 on a perceptual (log) scale: -60 dBFS → 0, -10 dBFS → 1. */
export function meterLevel(rms: number): number {
  if (rms <= 0) return 0;
  const db = 20 * Math.log10(rms);
  return Math.min(1, Math.max(0, (db + 60) / 50));
}

// ------------------------------------------------------------------------------ recorder
export interface RecordingResult {
  blob: Blob;
  mime: string;
  durationMs: number;
  vad: VadState;
  quality: 'ok' | 'quiet';
}

const MIME_CANDIDATES = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4', 'audio/aac'];

export function pickMimeType(): string | undefined {
  if (typeof MediaRecorder === 'undefined') return undefined;
  return MIME_CANDIDATES.find((m) => {
    try {
      return MediaRecorder.isTypeSupported(m);
    } catch {
      return false;
    }
  });
}

export function micSupported(): boolean {
  return typeof navigator !== 'undefined' && !!navigator.mediaDevices?.getUserMedia && typeof MediaRecorder !== 'undefined';
}

/**
 * Keeps one microphone stream + AudioContext open for the whole kiosk session (cheap on low-end phones,
 * and avoids a permission prompt per item). Call `close()` when the session ends.
 */
export class KioskMic {
  private stream: MediaStream | null = null;
  private ctx: AudioContext | null = null;
  private analyser: AnalyserNode | null = null;
  private active: { cancel: (finish: boolean) => void } | null = null;
  /** Once closed, the mic never re-opens (a late record()/open() after leaving the kiosk must not turn it on). */
  private closed = false;

  async open(): Promise<void> {
    if (this.closed) throw new DOMException('microphone closed', 'AbortError');
    if (this.stream) return;
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        sampleRate: 16000,
        sampleSize: 16,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
      video: false,
    });
    if (this.closed) {
      // close() ran while the permission prompt was open: release the device right away.
      stream.getTracks().forEach((t) => t.stop());
      throw new DOMException('microphone closed', 'AbortError');
    }
    this.stream = stream;
    const Ctx: typeof AudioContext =
      window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    this.ctx = new Ctx();
    const src = this.ctx.createMediaStreamSource(this.stream);
    this.analyser = this.ctx.createAnalyser();
    this.analyser.fftSize = 1024;
    src.connect(this.analyser);
  }

  /**
   * Records one utterance; resolves when the VAD stops (or `stopNow()` is called).
   * `onLevel` receives meter levels (0..1) ~20× per second.
   */
  async record(params: VadParams, onLevel?: (level: number, speaking: boolean) => void): Promise<RecordingResult> {
    if (!this.stream || !this.analyser || !this.ctx) await this.open();
    const stream = this.stream!;
    const analyser = this.analyser!;
    if (this.ctx!.state === 'suspended') await this.ctx!.resume();
    const mime = pickMimeType();
    const rec = new MediaRecorder(stream, { ...(mime ? { mimeType: mime } : {}), audioBitsPerSecond: 24_000 });
    const chunks: Blob[] = [];
    rec.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    const buf = new Float32Array(analyser.fftSize);
    const frameMs = 50;
    let vad = initVad();
    const t0 = performance.now();
    let lastT = t0;

    return new Promise<RecordingResult>((resolve, reject) => {
      let timer = 0;
      const finish = () => {
        window.clearInterval(timer);
        this.active = null;
        if (rec.state !== 'inactive') rec.stop();
      };
      rec.onstop = () => {
        const type = rec.mimeType || mime || 'audio/webm';
        const blob = new Blob(chunks, { type });
        resolve({ blob, mime: type, durationMs: Math.round(performance.now() - t0), vad, quality: classifyRecording(vad, params) });
      };
      rec.onerror = () => {
        window.clearInterval(timer);
        this.active = null;
        reject(new Error('recorder error'));
      };
      this.active = { cancel: () => finish() };
      rec.start(250);
      timer = window.setInterval(() => {
        analyser.getFloatTimeDomainData(buf);
        const rms = rmsOf(buf);
        const now = performance.now();
        // Use real elapsed time: timers drift on busy low-end phones.
        const dt = Math.min(250, Math.max(1, now - lastT));
        lastT = now;
        vad = vadStep(vad, rms, dt, params);
        onLevel?.(meterLevel(rms), rms > speechThreshold(vad.noiseFloor, params));
        if (vad.stop) finish();
      }, frameMs);
    });
  }

  /** Ends the current recording early (e.g. the child taps "Done"). */
  stopNow(): void {
    this.active?.cancel(true);
  }

  close(): void {
    this.closed = true;
    this.active?.cancel(false);
    this.stream?.getTracks().forEach((t) => t.stop());
    void this.ctx?.close().catch(() => undefined);
    this.stream = null;
    this.ctx = null;
    this.analyser = null;
  }
}
