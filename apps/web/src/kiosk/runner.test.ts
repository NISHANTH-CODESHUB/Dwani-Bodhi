import { describe, expect, it } from 'vitest';
import type { Item, PlannedItem, SessionPlan } from '../lib/types';
import { advance, buildSteps, currentStep, initRunner, isFinished, parseDiscontinueBlocks, progress, type RunnerState } from './runner';

const items = new Map<string, Item>(
  (
    [
      { id: 'ak1', type: 'akshara', text: 'क', skills: ['L3'] },
      { id: 'ak2', type: 'akshara', text: 'ख', skills: ['L3'] },
      { id: 'ak3', type: 'akshara', text: 'ग', skills: ['L3'] },
      { id: 'ak4', type: 'akshara', text: 'घ', skills: ['L3'] },
      { id: 'w1', type: 'word', text: 'नदी', skills: ['L7'] },
      { id: 'w2', type: 'nonword', text: 'तिमा', skills: ['L8'] },
      {
        id: 'p1',
        type: 'passage',
        text: 'मेरा नाम रानी है।',
        skills: ['L9'],
        questions: [{ id: 'q1', prompt_hi: 'कौन?', answer: 'गाय', options: [{ value: 'गाय', label: '🐄 गाय' }, { value: 'कुत्ता' }] }],
      },
      { id: 'rep1', type: 'repeat', text: 'वन', skills: ['L1'] },
      { id: 't1', type: 'tap_number', prompt_hi: 'सात को छुओ', answer: '7', skills: ['M1'], options: [{ value: '7' }, { value: '1' }] },
      { id: 'c1', type: 'tap_compare', prompt_hi: 'बड़ी?', answer: '31', skills: ['M4'], options: [{ value: '29' }, { value: '31' }] },
      { id: 'close', type: 'akshara', text: 'अ', skills: ['L2'] },
      { id: 'sl', type: 'slate', skills: ['M6'], a: 3, b: 4, op: '+' },
    ] as Item[]
  ).map((i) => [i.id, i]),
);

const p = (item_id: string, block: string): PlannedItem => ({ item_id, type: items.get(item_id)?.type ?? 'word', block, gain: 0.1, reason: 'info' });

const plan: SessionPlan = {
  plan_id: 'plan-1',
  child_id: 'c',
  est_seconds: 150,
  items: [
    p('ak1', 'aksharas'),
    p('ak2', 'aksharas'),
    p('ak3', 'aksharas'),
    p('ak4', 'aksharas'),
    p('w1', 'words'),
    p('w2', 'words'),
    p('p1', 'passage'),
    p('rep1', 'control'),
    p('t1', 'numeracy'),
    p('c1', 'numeracy'),
    p('close', 'closing'),
  ],
  rules: {
    silence_timeout_s: 6,
    discontinue_after_silent_aksharas: 3,
    on_discontinue: 'skip_to_blocks:control,numeracy,closing',
    passage_has_questions: true,
  },
};

const ids = (s: RunnerState) => s.steps.slice(s.index).map((st) => (st.kind === 'question' ? `${st.item.id}:${st.question.id}` : st.item.id));

function runAll(s: RunnerState, outcome: (st: RunnerState) => { spoke: boolean } | { tapped: string }): string[] {
  const seen: string[] = [];
  let guard = 0;
  while (!isFinished(s) && guard++ < 100) {
    const st = currentStep(s)!;
    seen.push(st.kind === 'question' ? `${st.item.id}:${st.question.id}` : st.item.id);
    s = advance(s, outcome(s));
  }
  return seen;
}

describe('buildSteps', () => {
  it('expands passage questions, keeps tap items, drops slate and unknown items', () => {
    const steps = buildSteps({ items: [...plan.items, p('sl', 'x'), p('missing', 'words')], rules: plan.rules }, items);
    expect(steps.map((s) => s.kind)).toEqual(['voice', 'voice', 'voice', 'voice', 'voice', 'voice', 'voice', 'question', 'voice', 'tap', 'tap', 'voice']);
  });

  it('omits questions when the plan says the passage has none', () => {
    const steps = buildSteps({ items: [p('p1', 'passage')], rules: { passage_has_questions: false } }, items);
    expect(steps).toHaveLength(1);
  });
});

describe('runner', () => {
  it('runs every step in order when the child responds', () => {
    const seen = runAll(initRunner(plan, items), () => ({ spoke: true }));
    expect(seen).toEqual(['ak1', 'ak2', 'ak3', 'ak4', 'w1', 'w2', 'p1', 'p1:q1', 'rep1', 't1', 'c1', 'close']);
  });

  it('discontinues after the first 3 aksharas are silent: skips reading, keeps control/numeracy/closing', () => {
    let s = initRunner(plan, items);
    s = advance(s, { spoke: false });
    s = advance(s, { spoke: false });
    expect(s.discontinued).toBe(false);
    s = advance(s, { spoke: false });
    expect(s.discontinued).toBe(true);
    expect(ids(s)).toEqual(['rep1', 't1', 'c1', 'close']);
    expect(currentStep(s)?.item.id).toBe('rep1');
    expect(progress(s)).toEqual({ done: 3, total: 7 });
  });

  it('does not discontinue if any of the first N aksharas had speech', () => {
    const outcomes = [false, true, false, false];
    let i = 0;
    const seen = runAll(initRunner(plan, items), () => ({ spoke: outcomes[i++] ?? false }));
    expect(seen).toContain('w1');
    expect(seen).toContain('p1');
  });

  it('does not count aksharas after the first N (or the closing akshara)', () => {
    let s = initRunner(plan, items);
    s = advance(s, { spoke: true });
    s = advance(s, { spoke: false });
    s = advance(s, { spoke: false });
    s = advance(s, { spoke: false }); // 4th akshara — outside the first 3
    expect(s.discontinued).toBe(false);
    expect(s.aksharasSeen).toBe(3);
  });

  it('honours a custom N and custom block list', () => {
    const custom = { ...plan, rules: { ...plan.rules, discontinue_after_silent_aksharas: 2, on_discontinue: 'skip_to_blocks:closing' } };
    let s = initRunner(custom, items);
    s = advance(s, { spoke: false });
    s = advance(s, { spoke: false });
    expect(s.discontinued).toBe(true);
    expect(ids(s)).toEqual(['close']);
  });

  it('tap outcomes never trigger the rule; plans without aksharas never discontinue', () => {
    const noAk = { ...plan, items: plan.items.filter((x) => !x.item_id.startsWith('ak')) };
    const seen = runAll(initRunner(noAk, items), (st) => (currentStep(st)?.kind === 'voice' ? { spoke: false } : { tapped: '7' }));
    // (the silent passage's question is skipped — nothing was read to comprehend)
    expect(seen).toEqual(['w1', 'w2', 'p1', 'rep1', 't1', 'c1', 'close']);
  });

  it('a technical skip (mic error) is never counted as silence', () => {
    let s = initRunner(plan, items);
    s = advance(s, { skipped: true });
    s = advance(s, { spoke: false });
    s = advance(s, { spoke: false });
    expect(s.discontinued).toBe(false);
    expect(currentStep(s)?.item.id).toBe('ak4');
  });

  it('advance past the end is a no-op', () => {
    const s = initRunner({ items: [], rules: {} }, items);
    expect(isFinished(s)).toBe(true);
    expect(advance(s, { spoke: true })).toBe(s);
  });

  it('parses the on_discontinue rule', () => {
    expect(parseDiscontinueBlocks('skip_to_blocks:control, numeracy')).toEqual(['control', 'numeracy']);
    expect(parseDiscontinueBlocks(undefined)).toEqual(['control', 'numeracy', 'closing']);
    expect(parseDiscontinueBlocks('weird')).toEqual(['control', 'numeracy', 'closing']);
  });
});

describe('comprehension after a silent passage', () => {
  it('skips the passage questions when the child did not read the passage', () => {
    const seen = runAll(initRunner(plan, items), (s) => {
      const st = currentStep(s)!;
      if (st.kind === 'voice') return { spoke: st.item.type !== 'passage' };
      return { tapped: 'x' };
    });
    expect(seen).toContain('p1');
    expect(seen).not.toContain('p1:q1');
    expect(seen).toContain('rep1');
  });

  it('asks the questions when the passage was read', () => {
    const seen = runAll(initRunner(plan, items), (s) => (currentStep(s)!.kind === 'voice' ? { spoke: true } : { tapped: 'x' }));
    expect(seen).toContain('p1:q1');
  });
});

describe('frustration rule (silent streak ends a block)', () => {
  const wordsPlan: SessionPlan = {
    ...plan,
    items: [
      p('ak1', 'aksharas'),
      p('w1', 'words'),
      p('w2', 'words'),
      p('ak2', 'words'),
      p('ak3', 'words'),
      p('p1', 'passage'),
      p('rep1', 'control'),
      p('t1', 'numeracy'),
      p('close', 'closing'),
    ],
    rules: { ...plan.rules, stop_block_after_silent: 3 },
  };

  it('three silent words in a row skip the rest of the words and the story, but keep maths and the closing item', () => {
    const seen = runAll(initRunner(wordsPlan, items), (s) => {
      const st = currentStep(s)!;
      if (st.kind !== 'voice') return { tapped: '7' };
      return { spoke: st.planned.block === 'aksharas' || st.planned.block === 'control' || st.planned.block === 'closing' };
    });
    expect(seen).toEqual(['ak1', 'w1', 'w2', 'ak2', 'rep1', 't1', 'close']);
  });

  it('a spoken item resets the streak', () => {
    const pattern = new Map([['w1', false], ['w2', false], ['ak2', true], ['ak3', false]]);
    const seen = runAll(initRunner(wordsPlan, items), (s) => {
      const st = currentStep(s)!;
      if (st.kind !== 'voice') return { tapped: '7' };
      return { spoke: pattern.get(st.item.id) ?? true };
    });
    expect(seen).toEqual(['ak1', 'w1', 'w2', 'ak2', 'ak3', 'p1', 'p1:q1', 'rep1', 't1', 'close']);
  });

  it('never skips the closing item and never counts technical skips as silence', () => {
    let s = initRunner({ ...wordsPlan, items: [p('w1', 'words'), p('w2', 'words'), p('close', 'closing')] }, items);
    s = advance(s, { skipped: true });
    s = advance(s, { skipped: true });
    expect(s.skippedBlocks).toEqual([]);
    expect(currentStep(s)?.item.id).toBe('close');
  });

  it('progress counts only steps that will still run', () => {
    let s = initRunner(wordsPlan, items);
    for (let i = 0; i < 4; i++) s = advance(s, { spoke: i === 0 }); // ak1 spoken, then 3 silent words
    expect(s.skippedBlocks).toEqual(['words', 'passage']);
    expect(progress(s)).toEqual({ done: 4, total: 7 });
  });
});

describe('new EGMA tap tasks', () => {
  it('runs counting and missing-number items as tap steps', () => {
    const extra = new Map<string, Item>([
      ...items,
      ['cnt', { id: 'cnt', type: 'tap_count', text: '🍎🍎🍎', prompt_hi: 'How many?', answer: '3', skills: ['M1'], options: [{ value: '3' }, { value: '4' }] } as Item],
      ['mis', { id: 'mis', type: 'tap_missing', text: '2, 3, __, 5', prompt_hi: 'Missing?', answer: '4', skills: ['M1'], options: [{ value: '4' }, { value: '6' }] } as Item],
    ]);
    const steps = buildSteps({ items: [p('cnt', 'numeracy'), p('mis', 'numeracy')], rules: {} }, extra);
    expect(steps.map((s) => s.kind)).toEqual(['tap', 'tap']);
  });
});
