import { useEffect, useRef, useState } from 'react';
import { hi } from '../i18n/hi';
import { buzz, sfx } from '../lib/sfx';
import { say, stopSpeaking } from '../lib/tts';
import type { ItemOption } from '../lib/types';
import { Cheenu } from './Cheenu';
import type { Step, StepOutcome } from './runner';
import { saveResponse } from './store';

function shuffled<T>(xs: T[]): T[] {
  const a = [...xs];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

/** Splits a row of emoji into single pictures (grapheme clusters, so multi-codepoint emoji stay whole). */
function graphemes(s: string): string[] {
  if (typeof Intl !== 'undefined' && 'Segmenter' in Intl) {
    return [...new Intl.Segmenter(undefined, { granularity: 'grapheme' }).segment(s)].map((g) => g.segment);
  }
  return Array.from(s);
}

/**
 * What the child looks at for counting and missing-number tasks. Objects are laid out in rows of five
 * (ten-frame style) as written in the content pack; the gap in a number sequence is a dashed "?" box.
 */
function Stimulus({ type, text }: { type: string; text: string }) {
  if (type === 'tap_count') {
    return (
      <div className="count-card pop-in" role="img" aria-label="Pictures to count">
        {text.split(/\s+/).filter(Boolean).map((row, r) => (
          <div className="count-row" key={r}>
            {graphemes(row).map((g, i) => (
              <span className="count-obj" key={i} style={{ animationDelay: `${(r * 5 + i) * 40}ms` }}>
                {g}
              </span>
            ))}
          </div>
        ))}
      </div>
    );
  }
  return (
    <div className="seq-card pop-in">
      {text.split(',').map((t, i) => {
        const v = t.trim();
        const gap = /^_+$/.test(v);
        return (
          <span key={i} className={`seq-num ${gap ? 'seq-gap' : ''}`}>
            {gap ? '?' : v}
          </span>
        );
      })}
    </div>
  );
}

/** Tap items (number, compare, count, missing number) and passage comprehension questions: big picture/number buttons. */
export function TapStep(props: {
  step: Extract<Step, { kind: 'tap' | 'question' }>;
  prompts: Record<string, string>;
  sessionId: string;
  onDone: (o: StepOutcome) => void;
}) {
  const { step, prompts, sessionId, onDone } = props;
  const isQuestion = step.kind === 'question';
  const options: ItemOption[] = isQuestion ? step.question.options : (step.item.options ?? []);
  // Shuffle once per mount so the answer's position carries no information.
  const [order] = useState(() => shuffled(options));
  const [chosen, setChosen] = useState<string | null>(null);
  const [talking, setTalking] = useState(true);
  const shownAt = useRef(performance.now());
  const mounted = useRef(true);

  const speak = async () => {
    setTalking(true);
    if (isQuestion) {
      if (prompts.question) await say('question', prompts.question);
      await say(`${step.item.id}.${step.question.id}`, step.question.prompt_hi);
    } else if (step.item.prompt_hi) {
      await say(step.item.id, step.item.prompt_hi);
    }
    if (mounted.current) setTalking(false);
  };

  useEffect(() => {
    mounted.current = true;
    shownAt.current = performance.now();
    void speak();
    return () => {
      mounted.current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const tap = async (value: string) => {
    if (chosen !== null) return;
    stopSpeaking();
    sfx.tap();
    buzz(20);
    setChosen(value);
    const rt = Math.round(performance.now() - shownAt.current);
    const payload: Record<string, unknown> = isQuestion
      ? { question_id: step.question.id, chosen: value, rt_ms: rt }
      : { chosen: value, rt_ms: rt };
    await saveResponse({ sessionId, itemId: step.item.id, modality: 'tap', payload }).catch(() => undefined);
    // Neutral acknowledgement only — the child never sees right/wrong.
    window.setTimeout(() => mounted.current && onDone({ tapped: value }), 450);
  };

  const numeric = !isQuestion;
  const prompt = isQuestion ? step.question.prompt_hi : step.item.prompt_hi;
  return (
    <div className="kiosk-step">
      <div className="kiosk-buddy">
        <Cheenu mood={chosen ? 'happy' : talking ? 'talking' : 'idle'} size={118} />
        {prompt && <div className="bubble bubble-pop">{prompt}</div>}
      </div>
      {!isQuestion && step.item.text && (step.item.type === 'tap_count' || step.item.type === 'tap_missing') && (
        <Stimulus type={step.item.type} text={step.item.text} />
      )}
      <button className="replay-btn" onClick={() => void speak()} aria-label={hi.kioskListenAgain}>
        🔊 {hi.kioskListenAgain}
      </button>
      <div className={`tiles ${order.length <= 2 ? 'tiles-2' : ''} ${numeric ? 'tiles-num' : 'tiles-pic'}`}>
        {order.map((o, i) => (
          <button
            key={o.value}
            className={`tile tile-c${i % 4} ${chosen === o.value ? 'tile-chosen' : ''} ${chosen && chosen !== o.value ? 'tile-faded' : ''}`}
            style={{ animationDelay: `${i * 70}ms` }}
            onClick={() => void tap(o.value)}
            disabled={chosen !== null}
            lang="hi"
          >
            {o.label ?? o.value}
          </button>
        ))}
      </div>
    </div>
  );
}
