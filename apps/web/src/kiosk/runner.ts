/**
 * Offline session runner (guide §6.3.3): walks the server-made plan one step at a time and applies the
 * within-session discontinue rule. Pure and immutable so it can be unit-tested and safely re-rendered.
 */
import type { Item, ItemQuestion, PlannedItem, PlanRules, SessionPlan } from '../lib/types';

export type VoiceType = 'akshara' | 'word' | 'nonword' | 'passage' | 'repeat';
const VOICE_TYPES = new Set<string>(['akshara', 'word', 'nonword', 'passage', 'repeat']);
export const TAP_TYPES = new Set<string>(['tap_number', 'tap_compare', 'tap_count', 'tap_missing']);

export type Step =
  | { kind: 'voice'; item: Item; planned: PlannedItem }
  | { kind: 'tap'; item: Item; planned: PlannedItem }
  | { kind: 'question'; item: Item; question: ItemQuestion; planned: PlannedItem };

/**
 * What happened on a step: for voice steps whether the child produced speech; `skipped` = technical
 * failure (e.g. microphone error) — never counted as silence for the discontinue rule.
 */
export type StepOutcome = { spoke: boolean } | { tapped: string } | { skipped: true };

export interface RunnerState {
  steps: Step[];
  index: number;
  /** steps actually shown to the child so far */
  presented: number;
  /** akshara items seen so far that count for the discontinue rule (not the closing item) */
  aksharasSeen: number;
  silentAksharas: number;
  discontinued: boolean;
  discontinueAfter: number;
  allowedAfterDiscontinue: string[];
  /** consecutive silent voice items in `streakBlock` (frustration rule) */
  silentStreak: number;
  streakBlock: string | null;
  stopBlockAfter: number;
  /** blocks cut short because the child stayed silent; their remaining steps are skipped */
  skippedBlocks: string[];
}

export const DEFAULT_DISCONTINUE_BLOCKS = ['control', 'numeracy', 'closing'];

/** A child who cannot produce single letters or words should not be asked to read a whole story. */
const READING_PREREQ_BLOCKS = new Set(['aksharas', 'words']);
/** The closing success item is never skipped: every session ends on something the child can do. */
const NEVER_SKIPPED = new Set(['closing']);

/** Parses `on_discontinue: "skip_to_blocks:control,numeracy,closing"`. */
export function parseDiscontinueBlocks(rule: string | undefined): string[] {
  const m = /^skip_to_blocks:(.+)$/.exec(rule ?? '');
  if (!m) return DEFAULT_DISCONTINUE_BLOCKS;
  const blocks = m[1]
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);
  return blocks.length ? blocks : DEFAULT_DISCONTINUE_BLOCKS;
}

/** Expands plan items into kiosk steps; passages get one extra step per comprehension question. */
export function buildSteps(plan: Pick<SessionPlan, 'items' | 'rules'>, items: Map<string, Item>): Step[] {
  const steps: Step[] = [];
  const withQuestions = plan.rules?.passage_has_questions !== false;
  for (const planned of plan.items ?? []) {
    const item = items.get(planned.item_id);
    if (!item) continue; // content pack older than the plan: skip unknown items
    if (VOICE_TYPES.has(item.type)) {
      steps.push({ kind: 'voice', item, planned });
      if (item.type === 'passage' && withQuestions) {
        for (const q of item.questions ?? []) steps.push({ kind: 'question', item, question: q, planned });
      }
    } else if (TAP_TYPES.has(item.type) && (item.options?.length ?? 0) > 0) {
      steps.push({ kind: 'tap', item, planned });
    } else if (item.type === 'comprehension') {
      for (const q of item.questions ?? []) steps.push({ kind: 'question', item, question: q, planned });
    }
    // slate items are whole-class (teacher camera), never in the kiosk
  }
  return steps;
}

export function initRunner(plan: Pick<SessionPlan, 'items' | 'rules'>, items: Map<string, Item>): RunnerState {
  const rules: PlanRules = plan.rules ?? {};
  return {
    steps: buildSteps(plan, items),
    index: 0,
    presented: 0,
    aksharasSeen: 0,
    silentAksharas: 0,
    discontinued: false,
    discontinueAfter: Math.max(1, rules.discontinue_after_silent_aksharas ?? 3),
    allowedAfterDiscontinue: parseDiscontinueBlocks(rules.on_discontinue),
    silentStreak: 0,
    streakBlock: null,
    stopBlockAfter: Math.max(2, rules.stop_block_after_silent ?? 3),
    skippedBlocks: [],
  };
}

export function currentStep(s: RunnerState): Step | null {
  return s.steps[s.index] ?? null;
}

export function isFinished(s: RunnerState): boolean {
  return s.index >= s.steps.length;
}

function countsForDiscontinue(step: Step): boolean {
  return step.kind === 'voice' && step.item.type === 'akshara' && step.planned.block !== 'closing';
}

function runnable(step: Step, discontinued: boolean, allowed: string[], skipped: string[]): boolean {
  const block = step.planned.block;
  if (skipped.includes(block)) return false;
  return !discontinued || allowed.includes(block);
}

/** Records the outcome of the current step and moves to the next runnable step. */
export function advance(s: RunnerState, outcome: StepOutcome): RunnerState {
  const step = currentStep(s);
  if (!step) return s;
  let { aksharasSeen, silentAksharas, discontinued, silentStreak, streakBlock } = s;
  const skippedBlocks = [...s.skippedBlocks];
  if (countsForDiscontinue(step) && aksharasSeen < s.discontinueAfter) {
    aksharasSeen += 1;
    if ('spoke' in outcome && !outcome.spoke) silentAksharas += 1;
    // "no response on the first N aksharas" → stop reading items, keep control/numeracy/closing
    if (aksharasSeen === s.discontinueAfter && silentAksharas === s.discontinueAfter) discontinued = true;
  }
  // Frustration rule (EGRA-style stop): N silent voice items in a row ends that block early.
  if (step.kind === 'voice' && 'spoke' in outcome) {
    const block = step.planned.block;
    if (streakBlock !== block) {
      streakBlock = block;
      silentStreak = 0;
    }
    silentStreak = outcome.spoke ? 0 : silentStreak + 1;
    if (silentStreak >= s.stopBlockAfter && !NEVER_SKIPPED.has(block) && !skippedBlocks.includes(block)) {
      skippedBlocks.push(block);
      if (READING_PREREQ_BLOCKS.has(block) && !skippedBlocks.includes('passage')) skippedBlocks.push('passage');
    }
  }
  let index = s.index + 1;
  // A passage the child did not read has nothing to be "comprehended": skip its questions.
  if (step.kind === 'voice' && step.item.type === 'passage' && 'spoke' in outcome && !outcome.spoke) {
    while (index < s.steps.length) {
      const nxt = s.steps[index];
      if (nxt.kind === 'question' && nxt.item.id === step.item.id) index += 1;
      else break;
    }
  }
  while (index < s.steps.length && !runnable(s.steps[index], discontinued, s.allowedAfterDiscontinue, skippedBlocks)) {
    index += 1;
  }
  return {
    ...s,
    index,
    presented: s.presented + 1,
    aksharasSeen,
    silentAksharas,
    discontinued,
    silentStreak,
    streakBlock,
    skippedBlocks,
  };
}

/** Progress for Cheenu's flight bar (never a score). */
export function progress(s: RunnerState): { done: number; total: number } {
  const remaining = s.steps
    .slice(s.index)
    .filter((st) => runnable(st, s.discontinued, s.allowedAfterDiscontinue, s.skippedBlocks)).length;
  return { done: s.presented, total: s.presented + remaining };
}
