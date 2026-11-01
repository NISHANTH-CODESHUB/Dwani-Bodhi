/**
 * Cheenu's voice. Prefers a pre-recorded human clip at /audio/hi/<key>.mp3 (precached by the service
 * worker when present); otherwise falls back to on-device speechSynthesis. The voice follows the script:
 * Devanagari (letters, words, story questions) is read with a Hindi voice, everything else in English.
 */

export type SpeechLang = 'hi-IN' | 'en-IN';

/** Hindi voice when the text is mostly Devanagari letters, English otherwise. */
export function speechLang(text: string): SpeechLang {
  let deva = 0;
  let latin = 0;
  for (const ch of text) {
    if (/[\u0900-\u097F]/.test(ch)) deva += 1;
    else if (/[A-Za-z]/.test(ch)) latin += 1;
  }
  return deva > latin ? 'hi-IN' : 'en-IN';
}

const clipAvailable = new Map<string, boolean>();
let currentAudio: HTMLAudioElement | null = null;
const voices = new Map<SpeechLang, Promise<SpeechSynthesisVoice | null>>();

function safeKey(key: string): string {
  return key.replace(/[^a-zA-Z0-9._-]/g, '_');
}

function pickVoice(vs: SpeechSynthesisVoice[], lang: SpeechLang): SpeechSynthesisVoice | null {
  const base = lang.slice(0, 2);
  return (
    vs.find((x) => x.lang === lang && /google/i.test(x.name)) ??
    vs.find((x) => x.lang.replace('_', '-').toLowerCase() === lang.toLowerCase()) ??
    vs.find((x) => x.lang.toLowerCase().startsWith(base)) ??
    null
  );
}

function voiceFor(lang: SpeechLang): Promise<SpeechSynthesisVoice | null> {
  if (typeof speechSynthesis === 'undefined') return Promise.resolve(null);
  let p = voices.get(lang);
  if (!p) {
    p = new Promise((resolve) => {
      const first = speechSynthesis.getVoices();
      if (first.length) {
        resolve(pickVoice(first, lang));
        return;
      }
      const t = setTimeout(() => resolve(pickVoice(speechSynthesis.getVoices(), lang)), 1500);
      speechSynthesis.addEventListener(
        'voiceschanged',
        () => {
          clearTimeout(t);
          resolve(pickVoice(speechSynthesis.getVoices(), lang));
        },
        { once: true },
      );
    });
    voices.set(lang, p);
  }
  return p;
}

export function ttsSupported(): boolean {
  return typeof speechSynthesis !== 'undefined';
}

/** Speaks `text` with the device TTS in the language of its script. Resolves when finished (or after a safety timeout). */
export async function speakText(text: string, rate = 0.9): Promise<void> {
  if (!ttsSupported() || !text.trim()) return;
  const lang = speechLang(text);
  const voice = await voiceFor(lang);
  speechSynthesis.cancel();
  await new Promise<void>((resolve) => {
    const u = new SpeechSynthesisUtterance(text);
    u.lang = lang;
    if (voice) u.voice = voice;
    u.rate = rate;
    // Android Chrome sometimes never fires `end`; never block the kiosk on it.
    const safety = setTimeout(resolve, 2500 + text.length * 120);
    const done = () => {
      clearTimeout(safety);
      resolve();
    };
    u.onend = done;
    u.onerror = done;
    speechSynthesis.speak(u);
  });
}

function playClip(url: string): Promise<boolean> {
  return new Promise((resolve) => {
    const a = new Audio(url);
    currentAudio = a;
    let started = false;
    a.onended = () => resolve(true);
    a.onpause = () => started && resolve(true);
    a.onerror = () => resolve(started);
    a.play().then(
      () => {
        started = true;
      },
      () => resolve(false),
    );
  });
}

let manifest: Promise<Set<string>> | null = null;

/**
 * Recorded clips are listed in /audio/hi/manifest.json (written when clips are added). One small
 * request instead of probing every prompt — and no 404 noise on 2G when nothing is recorded yet.
 */
function clipManifest(): Promise<Set<string>> {
  manifest ??= fetch('/audio/hi/manifest.json')
    .then((r) => (r.ok ? r.json() : []))
    .then((keys: unknown) => new Set(Array.isArray(keys) ? keys.map(String) : []))
    .catch(() => new Set<string>());
  return manifest;
}

async function hasClip(key: string): Promise<boolean> {
  const k = safeKey(key);
  const known = clipAvailable.get(k);
  if (known !== undefined) return known;
  const ok = (await clipManifest()).has(k);
  clipAvailable.set(k, ok);
  return ok;
}

/**
 * Says a line. `key` names a recorded clip (a prompt key like "welcome", or an item id); `text` is what
 * the TTS says when no clip exists.
 */
export async function say(key: string | null, text: string): Promise<void> {
  stopSpeaking();
  if (key && (await hasClip(key))) {
    if (await playClip(`/audio/hi/${safeKey(key)}.mp3`)) return;
  }
  await speakText(text);
}

export function stopSpeaking(): void {
  if (currentAudio) {
    currentAudio.pause();
    currentAudio = null;
  }
  if (ttsSupported()) speechSynthesis.cancel();
}

/** Splits long text into sentence-sized chunks (Chrome cuts off long utterances). */
export function sentenceChunks(text: string): string[] {
  return text
    .split(/(?<=[।.!?\n])\s*/)
    .map((p) => p.trim())
    .filter(Boolean);
}

/** Reads long text (e.g. the Action Card) aloud chunk by chunk until done or cancelled. */
export async function speakLong(text: string, isCancelled: () => boolean): Promise<void> {
  for (const p of sentenceChunks(text)) {
    if (isCancelled()) return;
    await speakText(p, 0.95);
  }
}
