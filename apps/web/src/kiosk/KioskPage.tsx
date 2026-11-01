import { useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Spinner } from '../components/common';
import { hi } from '../i18n/hi';
import { api } from '../lib/api';
import { KioskMic, micSupported } from '../lib/audio';
import { useClassroom } from '../lib/auth';
import { DEMO } from '../lib/config';
import { loadContent, type Content } from '../lib/content';
import { KV_KEYS, db, kvGet, kvSet, type LocalChild } from '../lib/db';
import { requestSync } from '../lib/sync';
import { buzz, sfx, unlockSfx } from '../lib/sfx';
import { say, stopSpeaking } from '../lib/tts';
import type { SessionPlan, TodayResponse } from '../lib/types';
import { Cheenu } from './Cheenu';
import { advance, currentStep, initRunner, isFinished, progress, type RunnerState, type StepOutcome } from './runner';
import { createSession, finishSession } from './store';
import { TapStep } from './TapStep';
import { Confetti, Journey, StarBurst, World } from './World';
import { VoiceStep } from './VoiceStep';

interface Setup {
  child: LocalChild;
  content: Content;
  plan: SessionPlan;
}

async function findPlan(childId: string, classroomId: string): Promise<SessionPlan | null> {
  const cached = await kvGet<SessionPlan>(KV_KEYS.plan(childId));
  if (cached?.items?.length) return cached;
  const today = await kvGet<TodayResponse>(KV_KEYS.today(classroomId));
  const fromToday = today?.children.find((c) => c.child_id === childId)?.plan;
  if (fromToday?.items?.length) return fromToday;
  if (navigator.onLine) {
    try {
      const p = await api.childPlan(childId);
      if (p.items?.length) {
        const plan = p as SessionPlan; // non-empty response has the full SessionPlan shape
        await kvSet(KV_KEYS.plan(childId), plan);
        return plan;
      }
    } catch {
      /* offline or not yet on the server */
    }
  }
  return null;
}

const HOLD_MS = 2000;
/** Reading tasks that get one modelled, unscored example before the first real item. */
const PRACTICE_TYPES = new Set(['akshara', 'word', 'nonword']);

/** Discreet teacher exit: a small lock that must be held for 2 s (a ring fills while holding). */
function HoldToExit({ onExit }: { onExit: () => void }) {
  const timer = useRef<number | null>(null);
  const [holding, setHolding] = useState(false);
  const start = () => {
    setHolding(true);
    timer.current = window.setTimeout(onExit, HOLD_MS);
  };
  const cancel = () => {
    setHolding(false);
    if (timer.current) window.clearTimeout(timer.current);
  };
  return (
    <button
      className={`kiosk-lock ${holding ? 'kiosk-lock-holding' : ''}`}
      onPointerDown={start}
      onPointerUp={cancel}
      onPointerLeave={cancel}
      onPointerCancel={cancel}
      onContextMenu={(e) => e.preventDefault()}
      aria-label={hi.kioskExitHold}
      title={hi.kioskExitHold}
      style={{ ['--hold' as string]: `${HOLD_MS}ms` }}
    >
      <svg viewBox="0 0 36 36" width="40" height="40" aria-hidden>
        <circle cx="18" cy="18" r="16" className="lock-track" />
        <circle cx="18" cy="18" r="16" className="lock-ring" />
      </svg>
      <span className="lock-icon" aria-hidden>
        🔒
      </span>
    </button>
  );
}

export default function KioskPage() {
  const { childId = '' } = useParams();
  const room = useClassroom()!;
  const nav = useNavigate();
  const [setup, setSetup] = useState<Setup | null>(null);
  const [blocker, setBlocker] = useState<string | null>(null);
  const [phase, setPhase] = useState<'intro' | 'starting' | 'run' | 'end'>('intro');
  const [runner, setRunner] = useState<RunnerState | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const sessionRef = useRef<string | null>(null);
  const runnerRef = useRef<RunnerState | null>(null);
  const micRef = useRef<KioskMic | null>(null);
  const announced = useRef(new Set<string>());
  const wakeLock = useRef<WakeLockSentinel | null>(null);
  const sessionDone = useRef(false);
  const [burst, setBurst] = useState(false);
  const [stars, setStars] = useState(0);
  const advanceTimer = useRef<number | null>(null);
  const alive = useRef(true);

  useEffect(() => {
    let live = true;
    const block = (msg: string) => live && setBlocker(msg);
    void (async () => {
      try {
        const child = await db.children.get(childId);
        if (!child || child.deleted) return block(hi.consentRequired);
        if (child.consent_status !== 'granted') return block(hi.consentRequired);
        const content = await loadContent();
        if (!content) return block(hi.kioskNoContent);
        const plan = await findPlan(childId, room.id);
        if (!plan) return block(hi.kioskNoPlan);
        if (!DEMO && !micSupported()) return block(hi.micUnsupported);
        if (live) setSetup({ child, content, plan });
      } catch (e) {
        console.error(e);
        block(hi.kioskStorageError);
      }
    })();
    return () => {
      live = false;
    };
  }, [childId, room.id]);

  // Cleanup: close the mic, stop speech, release wake lock, leave full screen; close an abandoned session.
  useEffect(() => {
    // Must be re-armed on (re)mount: React StrictMode mounts → cleans up → mounts again, and a flag left
    // false here makes start() return silently, so the kiosk sat on "Start" forever.
    alive.current = true;
    return () => {
      alive.current = false;
      micRef.current?.close();
      stopSpeaking();
      if (advanceTimer.current) window.clearTimeout(advanceTimer.current);
      void endSession(); // e.g. Android back button mid-session: keep what was recorded

      void wakeLock.current?.release().catch(() => undefined);
      if (document.fullscreenElement) void document.exitFullscreen().catch(() => undefined);
    };
  }, []);

  const endSession = async () => {
    const sid = sessionRef.current;
    if (sessionDone.current || !sid) return;
    sessionDone.current = true;
    await finishSession(sid, runnerRef.current?.discontinued ?? false);
    requestSync();
  };

  const start = async () => {
    if (!setup) return;
    setPhase('starting');
    unlockSfx();
    // These need the user's tap (gesture): full screen, wake lock, mic permission, speech unlock.
    try {
      await document.documentElement.requestFullscreen?.({ navigationUI: 'hide' });
    } catch {
      /* not allowed — fine */
    }
    try {
      wakeLock.current = (await navigator.wakeLock?.request('screen')) ?? null;
    } catch {
      /* optional */
    }
    if (!alive.current) return;
    if (!DEMO) {
      const mic = new KioskMic();
      micRef.current = mic; // set before awaiting, so leaving the page during the prompt closes it
      try {
        await mic.open();
      } catch {
        if (alive.current) setBlocker(hi.micDenied);
        return;
      }
    }
    if (!alive.current) return; // left the kiosk while the permission prompt was open
    let sid: string;
    try {
      sid = await createSession(setup.child.id, room.id, setup.plan.plan_id ?? null);
    } catch (e) {
      console.error(e);
      if (alive.current) setBlocker(hi.kioskStorageError);
      return;
    }
    sessionRef.current = sid;
    if (!alive.current) {
      void endSession();
      return;
    }
    setSessionId(sid);
    const r = initRunner(setup.plan, setup.content.items);
    runnerRef.current = r;
    setRunner(r);
    await say('welcome', setup.content.bootstrap.prompts.welcome ?? "Hello! Let's play!");
    if (isFinished(r)) {
      setPhase('end');
      return;
    }
    setPhase('run');
  };

  /** Every finished step earns a star (effort, never correctness), then the next step slides in. */
  const onStepDone = (o: StepOutcome) => {
    const prev = runnerRef.current;
    if (!prev || advanceTimer.current) return;
    const next = advance(prev, o);
    runnerRef.current = next;
    if (!('skipped' in o)) {
      setStars((n) => n + 1);
      setBurst(true);
      sfx.star();
      buzz(30);
    }
    advanceTimer.current = window.setTimeout(() => {
      advanceTimer.current = null;
      setBurst(false);
      setRunner(next);
      if (isFinished(next)) setPhase('end');
    }, 'skipped' in o ? 0 : 700);
  };

  useEffect(() => {
    if (phase !== 'end' || !setup) return;
    void endSession();
    micRef.current?.close();
    sfx.fanfare();
    buzz(80);
    void say('bye', setup.content.bootstrap.prompts.bye ?? 'Well done!');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase]);

  const exit = async () => {
    stopSpeaking();
    micRef.current?.close();
    await endSession();
    nav('/', { replace: true });
  };

  if (blocker) {
    return (
      <div className="kiosk kiosk-blocked">
        <World />
        <Cheenu mood="idle" />
        <p className="kiosk-msg">{blocker}</p>
        <button className="btn btn-primary btn-big" onClick={() => nav(-1)}>
          {hi.back}
        </button>
      </div>
    );
  }
  if (!setup) return <Spinner />;

  const step = runner ? currentStep(runner) : null;
  const prog = runner ? progress(runner) : { done: 0, total: 1 };
  const prompts = setup.content.bootstrap.prompts;

  let announce = false;
  let practice: string | null = null;
  if (step && step.kind === 'voice') {
    const t = step.item.type;
    const first = !announced.current.has(t);
    announce = t === 'passage' || t === 'repeat' || first;
    if (first && PRACTICE_TYPES.has(t)) practice = prompts[`example_${t}`] ?? null;
  }

  return (
    <div className={`kiosk kiosk-${phase}`}>
      <World />
      <HoldToExit onExit={exit} />
      {phase === 'run' && <Journey done={prog.done} total={prog.total} />}
      <StarBurst show={burst} />

      {(phase === 'intro' || phase === 'starting') && (
        <div className="kiosk-intro">
          <Cheenu mood={phase === 'starting' ? 'talking' : 'happy'} size={210} />
          <div className="bubble bubble-big bubble-pop">{prompts.welcome ?? "Hello! Let's play!"}</div>
          <p className="kiosk-child">{hi.kioskHello(setup.child.name.trim())}</p>
          <button className="kiosk-start" onClick={start} disabled={phase === 'starting'} aria-label={hi.kioskStart}>
            <span className="kiosk-start-icon" aria-hidden>
              ▶
            </span>
            {hi.kioskStart}
          </button>
        </div>
      )}

      {phase === 'run' && step && sessionId && runner && (
        <div key={runner.index} className="kiosk-stage">
          {step.kind === 'voice' ? (
            <VoiceStep
              step={step}
              rules={setup.plan.rules}
              prompts={prompts}
              mic={micRef.current}
              sessionId={sessionId}
              announce={announce}
              practice={practice}
              onDone={(o) => {
                announced.current.add(step.item.type);
                onStepDone(o);
              }}
            />
          ) : (
            <TapStep step={step} prompts={prompts} sessionId={sessionId} onDone={onStepDone} />
          )}
        </div>
      )}

      {phase === 'end' && (
        <div className="kiosk-end">
          <Confetti />
          <Cheenu mood="cheer" size={210} />
          <div className="bubble bubble-big bubble-pop">{prompts.bye ?? hi.kioskThanks}</div>
          <div className="star-count" aria-label={hi.kioskStars(stars)}>
            <span className="star-count-star">⭐</span>
            <span className="star-count-n">× {stars}</span>
          </div>
          <p className="kiosk-child">{hi.kioskWellDone(setup.child.name.trim())}</p>
          <button className="btn btn-big btn-teacher" onClick={exit}>
            {hi.kioskBack}
          </button>
        </div>
      )}
    </div>
  );
}
