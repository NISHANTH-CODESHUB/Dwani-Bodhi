import { useEffect, useRef, useState } from 'react';
import { hi } from '../i18n/hi';
import { vadParamsFor, type KioskMic, type RecordingResult } from '../lib/audio';
import { DEMO } from '../lib/config';
import { say, stopSpeaking } from '../lib/tts';
import type { PlanRules } from '../lib/types';
import { Cheenu, type CheenuMood } from './Cheenu';
import type { Step, StepOutcome } from './runner';
import { saveResponse } from './store';

type Phase = 'prompt' | 'example' | 'listening' | 'louder' | 'saving' | 'demo' | 'error';

/** Big glowing orb: its halo grows with the child's voice. Tapping it ends the recording ("I'm done"). */
function MicOrb({ level, speaking, onStop, big }: { level: number; speaking: boolean; onStop: () => void; big: boolean }) {
  const lv = Math.max(0, Math.min(1, level));
  return (
    <button
      className={`mic-orb ${speaking ? 'mic-orb-speaking' : ''} ${big ? 'mic-orb-big' : ''}`}
      onClick={onStop}
      aria-label={hi.kioskDoneBtn}
      style={{ ['--lv' as string]: lv.toFixed(2) }}
    >
      <span className="mic-halo" aria-hidden />
      <span className="mic-halo mic-halo-2" aria-hidden />
      <span className="mic-core" aria-hidden>
        <svg viewBox="0 0 24 24" width="44" height="44" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
          <rect x="9" y="3" width="6" height="11" rx="3" fill="currentColor" />
          <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
        </svg>
      </span>
      <span className="mic-label">{speaking ? hi.kioskListening : hi.kioskSpeakNow}</span>
      <span className="mic-done">{hi.kioskTapWhenDone}</span>
    </button>
  );
}

export function VoiceStep(props: {
  step: Extract<Step, { kind: 'voice' }>;
  rules: PlanRules;
  prompts: Record<string, string>;
  mic: KioskMic | null;
  sessionId: string;
  announce: boolean;
  /** Unscored practice example Cheenu models before the first item of this task type (EGRA practice item). */
  practice?: string | null;
  onDone: (o: StepOutcome) => void;
}) {
  const { step, rules, prompts, mic, sessionId, announce, practice, onDone } = props;
  const item = step.item;
  const type = item.type;
  const [phase, setPhase] = useState<Phase>('prompt');
  const [level, setLevel] = useState(0);
  const [speaking, setSpeaking] = useState(false);
  const [sim, setSim] = useState('');
  const started = useRef(false);
  const mounted = useRef(true);
  const finished = useRef(false);

  const done = (o: StepOutcome) => {
    if (finished.current || !mounted.current) return;
    finished.current = true;
    onDone(o);
  };

  const speakPrompt = async () => {
    if (announce && prompts[type]) await say(type, prompts[type]);
    if (practice && mounted.current) {
      // "I do, you do": Cheenu reads one example the child is not tested on, then hands over.
      setPhase('example');
      await say('example_intro', prompts.example_intro ?? 'Listen to me first.');
      if (mounted.current) await say(`example_${type}`, practice);
      if (mounted.current) await say('your_turn', prompts.your_turn ?? "Now it's your turn!");
      if (mounted.current) setPhase('prompt');
    }
    if (type === 'repeat' && item.text) await say(item.id, item.text);
  };

  useEffect(() => {
    mounted.current = true;
    if (!started.current) {
      started.current = true;
      void run();
    }
    return () => {
      mounted.current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function run() {
    await speakPrompt();
    if (!mounted.current) return;
    if (DEMO || !mic) {
      setPhase('demo');
      return;
    }
    const params = vadParamsFor(type, rules);
    let rec: RecordingResult | null = null;
    let retried = false;
    try {
      for (;;) {
        setPhase('listening');
        rec = await mic.record(params, (l, s) => {
          setLevel(l);
          setSpeaking(s);
        });
        if (!mounted.current) return;
        if (rec.quality === 'quiet' && !retried) {
          retried = true;
          setPhase('louder');
          await say('try_again_louder', prompts.try_again_louder ?? 'Say it a little louder.');
          if (type === 'repeat' && item.text) await say(item.id, item.text);
          if (!mounted.current) return;
          continue;
        }
        break;
      }
    } catch {
      setPhase('error');
      return;
    }
    setPhase('saving');
    const spoke = rec.quality === 'ok';
    try {
      await saveResponse({
        sessionId,
        itemId: item.id,
        modality: 'voice',
        payload: {
          duration_ms: rec.durationMs,
          speech_ms: Math.round(rec.vad.speechMs),
          speech_onset_ms: rec.vad.firstSpeechAt === null ? null : Math.round(rec.vad.firstSpeechAt),
          vad_stop: rec.vad.stop ?? 'manual',
          no_speech: !spoke,
          retried,
          mime: rec.mime,
        },
        audio: { blob: rec.blob, mime: rec.mime },
      });
    } catch {
      /* storage failure: keep the child moving; the teacher sees missing data later */
    }
    done({ spoke });
  }

  const submitSim = async (text: string) => {
    setPhase('saving');
    await saveResponse({
      sessionId,
      itemId: item.id,
      modality: 'voice',
      payload: { simulated_utterance: text, duration_ms: 3000, no_speech: !text },
    }).catch(() => undefined);
    done({ spoke: !!text });
  };

  const mood: CheenuMood =
    phase === 'listening'
      ? 'listening'
      : phase === 'prompt' || phase === 'louder' || phase === 'example'
        ? 'talking'
        : phase === 'saving'
          ? 'happy'
          : 'idle';
  const isPassage = type === 'passage';

  return (
    <div className={`kiosk-step ${isPassage ? 'kiosk-step-passage' : ''}`}>
      <div className="kiosk-buddy">
        <Cheenu mood={mood} size={isPassage ? 84 : 128} level={phase === 'listening' ? level : 0} />
        {phase === 'louder' ? (
          <div className="bubble bubble-pop">{prompts.try_again_louder ?? 'Say it a little louder.'}</div>
        ) : phase === 'example' ? (
          <div className="bubble bubble-pop">{prompts.example_intro ?? 'Listen to me first.'}</div>
        ) : phase === 'prompt' && prompts[type] ? (
          <div className="bubble bubble-pop">{prompts[type]}</div>
        ) : null}
      </div>

      {phase === 'example' && practice ? (
        <div className={`word-card word-card-example pop-in word-card-${type}`} lang="hi">
          <span className="example-tag">{hi.kioskExample}</span>
          {practice}
        </div>
      ) : type === 'repeat' ? (
        <button
          className="ear-card pop-in"
          aria-label={hi.kioskListenAgain}
          onClick={() => item.text && void say(item.id, item.text)}
          disabled={phase === 'listening'}
        >
          <span className="ear-icon" aria-hidden>
            👂
          </span>
          <span>{hi.kioskListenAgain}</span>
        </button>
      ) : isPassage ? (
        <p className="story-card pop-in" lang="hi">
          {item.text}
        </p>
      ) : (
        <div className={`word-card pop-in word-card-${type}`} lang="hi">
          {item.text}
        </div>
      )}

      {phase === 'listening' && (
        <MicOrb
          level={level}
          speaking={speaking}
          big={!isPassage}
          onStop={() => {
            stopSpeaking();
            mic?.stopNow();
          }}
        />
      )}

      {phase === 'demo' && (
        <form
          className="demo-box"
          onSubmit={(e) => {
            e.preventDefault();
            void submitSim(sim.trim());
          }}
        >
          <label className="small">{hi.simulateLabel}</label>
          <input value={sim} onChange={(e) => setSim(e.target.value)} lang="hi" autoComplete="off" />
          <div className="two-btns">
            <button className="btn btn-primary" type="submit">
              {hi.simulateSend}
            </button>
            <button className="btn" type="button" onClick={() => void submitSim('')}>
              {hi.simulateSilent}
            </button>
          </div>
        </form>
      )}

      {phase === 'error' && (
        <div className="kiosk-error">
          <p>{hi.micDenied}</p>
          <button className="btn btn-primary" onClick={() => done({ skipped: true })}>
            → {hi.done}
          </button>
        </div>
      )}
    </div>
  );
}
