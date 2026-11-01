import { useEffect, useRef, useState } from 'react';
import { ErrorBox, Spinner, useLive } from '../components/common';
import { Icon } from '../components/icons';
import { AppShell, EmptyState } from '../components/ui';
import { formatTime, hi } from '../i18n/hi';
import { api } from '../lib/api';
import { useClassroom } from '../lib/auth';
import { useContent } from '../lib/content';
import { KV_KEYS, kvGet, kvGetWithTime, kvSet } from '../lib/db';
import { speakLong, stopSpeaking, ttsSupported } from '../lib/tts';
import type { CardGroup, CardResponse, SummaryGroup } from '../lib/types';

const MATERIAL_ICON: Record<string, string> = {
  chalk: '🖍️',
  slate: '⬛',
  blackboard: '🟩',
  pebbles: '🪨',
  matchsticks: '🥢',
  rubber_bands: '➰',
  paper_cards: '🃏',
  body_movement: '🙌',
  bottle_caps: '🔘',
  string: '🧵',
};

function groupText(g: CardGroup, s: SummaryGroup | undefined): string {
  const lines: string[] = [];
  if (s) lines.push(`${hi.domains[s.domain] ?? ''}, ${s.level_name_hi}, ${hi.cardChildren(s.n_children)}.`);
  lines.push(`${g.title_hi}.`, g.why_hi, ...g.steps_hi);
  if (g.example_items.length) lines.push(`${hi.cardExamples}: ${g.example_items.join(', ')}.`);
  return lines.join('\n');
}

/** How sure the evidence behind a group's main confusion is: verified vs. still being checked. */
function Certainty({ top }: { top?: NonNullable<SummaryGroup['top_confusions']>[number] }) {
  if (!top || top.n_confirmed === undefined) return null;
  const maybe = top.n_suspected ?? 0;
  return (
    <div className="cert-row">
      {top.n_confirmed > 0 && (
        <span className="cert cert-sure">
          <Icon name="checkCircle" size={14} />
          {hi.certSure(top.n_confirmed)}
        </span>
      )}
      {maybe > 0 && (
        <span className="cert cert-maybe">
          <Icon name="review" size={14} />
          {hi.certMaybe(maybe)}
        </span>
      )}
    </div>
  );
}

export default function CardPage() {
  const room = useClassroom()!;
  const content = useContent();
  const cached = useLive(() => kvGetWithTime<CardResponse>(KV_KEYS.card(room.id)), [room.id], undefined);
  const c = cached?.value;
  const doneKey = c ? `carddone:${room.id}:${c.week}` : '';
  const doneList = useLive(() => (doneKey ? kvGet<string[]>(doneKey) : Promise.resolve(undefined)), [doneKey], undefined);
  const done = new Set(doneList ?? []);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [speaking, setSpeaking] = useState<string | null>(null);
  const [open, setOpen] = useState<Set<string>>(new Set());
  const speakToken = useRef(0);

  const fetchCard = async (regenerate: boolean) => {
    setLoading(true);
    setError(null);
    try {
      await kvSet(KV_KEYS.card(room.id), await api.card(room.id, regenerate));
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (navigator.onLine) void fetchCard(false);
    return () => {
      speakToken.current += 1;
      stopSpeaking();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [room.id]);

  // first unfinished group starts expanded
  useEffect(() => {
    if (c && open.size === 0) {
      const first = c.card.groups.find((g) => !done.has(g.group_key)) ?? c.card.groups[0];
      if (first) setOpen(new Set([first.group_key]));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [c?.id]);

  const summary = new Map((c?.summary.groups ?? []).map((g) => [g.key, g]));

  const toggleDone = async (key: string) => {
    const next = new Set(done);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    await kvSet(doneKey, [...next]);
  };
  const toggleOpen = (key: string) =>
    setOpen((prev) => {
      const n = new Set(prev);
      if (n.has(key)) n.delete(key);
      else n.add(key);
      return n;
    });
  /** One reading at a time; tapping the same button again stops it. A token cancels stale readings. */
  const speak = async (id: string, text: string) => {
    const wasSame = speaking === id;
    speakToken.current += 1;
    stopSpeaking();
    if (wasSame) {
      setSpeaking(null);
      return;
    }
    const mine = speakToken.current;
    setSpeaking(id);
    await speakLong(text, () => speakToken.current !== mine);
    if (speakToken.current === mine) setSpeaking(null);
  };

  const total = c?.card.groups.length ?? 0;
  const doneCount = c ? c.card.groups.filter((g) => done.has(g.group_key)).length : 0;

  return (
    <AppShell narrow title={hi.cardTitle} subtitle={c ? hi.cardWeek(c.week.replace(/^\d{4}-W/, '')) : undefined}>
      {loading && !c && <Spinner />}
      <ErrorBox error={c ? null : error} onRetry={() => fetchCard(false)} />
      {!loading && !c && !error && <EmptyState icon="clipboard" title={hi.cardNone} />}
      {c && (
        <>
          <section className="card-hero">
            <div>
              <div className="hero-kicker">{hi.cardHeroKicker}</div>
              <div className="card-hero-title">{c.card.headline_hi}</div>
              <div className="card-hero-meta">
                {hi.cardProgress(doneCount, total)} · {c.source === 'llm' ? hi.cardByAI : hi.cardByTemplate}
              </div>
            </div>
            {ttsSupported() && (
              <button
                className={`btn btn-hero-ghost ${speaking === 'all' ? 'is-on' : ''}`}
                onClick={() => speak('all', [c.card.headline_hi, ...c.card.groups.map((g) => groupText(g, summary.get(g.group_key))), c.card.teacher_tip_hi].join('\n'))}
              >
                <Icon name={speaking === 'all' ? 'stop' : 'volume'} size={18} />
                {speaking === 'all' ? hi.cardStop : hi.cardListen}
              </button>
            )}
          </section>

          {c.summary.last_week && (c.summary.last_week.resolved || c.summary.last_week.improved || c.summary.last_week.persists) ? (
            <div className="banner banner-ok">
              <Icon name="chart" size={18} />
              {hi.lastWeekResult(c.summary.last_week.resolved ?? 0, c.summary.last_week.improved ?? 0, c.summary.last_week.persists ?? 0)}
            </div>
          ) : null}

          {c.card.groups.map((g, idx) => {
            const s = summary.get(g.group_key);
            const act = content?.bootstrap.activities[g.activity_id];
            const isOpen = open.has(g.group_key);
            const isDone = done.has(g.group_key);
            return (
              <article key={g.group_key} className={`gcard gcard-${s?.domain ?? 'x'} ${isDone ? 'gcard-done' : ''}`}>
                <button className="gcard-head" onClick={() => toggleOpen(g.group_key)} aria-expanded={isOpen}>
                  <span className="gcard-num">{isDone ? <Icon name="check" size={16} /> : idx + 1}</span>
                  <span className="gcard-titles">
                    <span className="gcard-level">
                      {s ? `${hi.domains[s.domain] ?? s.domain} · ${s.level_name_hi}` : g.group_key}
                      {s && <span className="gcard-count">{hi.cardChildren(s.n_children)}</span>}
                    </span>
                    <span className="gcard-title">{g.title_hi}</span>
                  </span>
                  <Icon name="chevronDown" className={`chev ${isOpen ? 'chev-open' : ''}`} />
                </button>
                {isOpen && (
                  <div className="gcard-body">
                    <div className="evidence">
                      <span className="evidence-label">{hi.cardWhy}</span>
                      {g.why_hi}
                      <Certainty top={s?.top_confusions?.[0]} />
                      {g.example_items.length > 0 && (
                        <div className="evidence-ex">
                          {g.example_items.map((x) => (
                            <span key={x} className="ex">
                              {x}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                    <ol className="steps-pro">
                      {g.steps_hi.map((st, i) => (
                        <li key={i}>
                          <span className="step-n">{i + 1}</span>
                          <span>{st}</span>
                        </li>
                      ))}
                    </ol>
                    {act && (
                      <div className="materials">
                        <span className="materials-time">
                          <Icon name="clock" size={15} /> {hi.cardMinutes(act.minutes)}
                        </span>
                        {act.materials.map((m) => (
                          <span key={m} className="material">
                            {MATERIAL_ICON[m] ?? '•'} {hi.materials[m] ?? m.replace(/_/g, ' ')}
                          </span>
                        ))}
                      </div>
                    )}
                    <div className="gcard-actions">
                      {ttsSupported() && (
                        <button className="btn btn-small btn-ghost" onClick={() => speak(g.group_key, groupText(g, s))}>
                          <Icon name={speaking === g.group_key ? 'stop' : 'volume'} size={16} />
                          {speaking === g.group_key ? hi.cardStop : hi.cardListen}
                        </button>
                      )}
                      <button className={`btn btn-small ${isDone ? 'btn-ok' : 'btn-outline'}`} onClick={() => toggleDone(g.group_key)}>
                        {isDone ? hi.cardDoneYes : hi.cardMarkDone}
                      </button>
                    </div>
                  </div>
                )}
              </article>
            );
          })}

          <div className="tip">
            <Icon name="bulb" size={20} className="tip-ico" />
            <span>{c.card.teacher_tip_hi}</span>
          </div>
          <p className="muted small center">{hi.cardRecheck}</p>
          <p className="muted small center">{hi.cardCachedAt(formatTime(cached?.updated_at))}</p>
          {error ? <ErrorBox error={error} /> : null}
          <button className="btn btn-ghost btn-block" disabled={loading} onClick={() => fetchCard(true)}>
            <Icon name="sync" size={16} />
            {loading ? hi.loading : hi.cardRegenerate}
          </button>
        </>
      )}
    </AppShell>
  );
}
