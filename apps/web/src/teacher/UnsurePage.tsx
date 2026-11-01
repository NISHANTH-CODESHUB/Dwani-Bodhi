import { useEffect, useRef, useState } from 'react';
import { ErrorBox, Spinner, useLive } from '../components/common';
import { Icon } from '../components/icons';
import { AppShell, Avatar, EmptyState } from '../components/ui';
import { errorText, hi, opSymbol } from '../i18n/hi';
import { ApiError, api } from '../lib/api';
import { useClassroom } from '../lib/auth';
import { KV_KEYS, childLabel, db, kvSet, type LocalChild } from '../lib/db';
import type { ConfirmBody, UnsureEntry } from '../lib/types';

/** Fetches an authenticated media URL as a blob and exposes an object URL. */
function useMediaBlob(path: string | null, auto: boolean) {
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const urlRef = useRef<string | null>(null);
  const gen = useRef(0); // bumps on every path change/unmount: late downloads for an old path are dropped

  const load = async (): Promise<string | null> => {
    if (!path) return null;
    if (urlRef.current) return urlRef.current;
    const mine = gen.current;
    setBusy(true);
    setError(null);
    try {
      const blob = await api.media(path);
      if (mine !== gen.current) return null;
      urlRef.current = URL.createObjectURL(blob);
      setUrl(urlRef.current);
      return urlRef.current;
    } catch (e) {
      setError(e instanceof ApiError && e.status === 410 ? hi.mediaGone : errorText(e));
      return null;
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    if (auto) void load();
    return () => {
      gen.current += 1;
      if (urlRef.current) URL.revokeObjectURL(urlRef.current);
      urlRef.current = null; // otherwise the next path would get this revoked URL back
      setUrl(null);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, auto]);

  return { url, error, busy, load };
}

function UnsureCard({ entry, kid, onDone, onSkip }: {
  entry: UnsureEntry;
  kid: LocalChild | undefined;
  onDone: (id: string) => void;
  onSkip: (id: string) => void;
}) {
  const name = childLabel(kid);
  const isSlate = entry.type === 'slate';
  const media = useMediaBlob(entry.media, isSlate);
  const [rule, setRule] = useState('');
  const [answer, setAnswer] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const play = async () => {
    const u = await media.load();
    if (!u) return;
    audioRef.current?.pause();
    audioRef.current = new Audio(u);
    void audioRef.current.play().catch(() => undefined);
  };

  useEffect(() => () => audioRef.current?.pause(), []);

  const send = async (body: ConfirmBody) => {
    setBusy(true);
    setError(null);
    try {
      await api.confirm(entry.id, body);
      onDone(entry.id);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  const produced = typeof entry.verdict?.produced === 'string' ? entry.verdict.produced : null;
  const prob = entry.problem;

  return (
    <li className="review">
      <div className="review-head">
        <Avatar id={entry.child_id} name={kid?.name ?? ''} slot={kid?.aruco_slot} size={40} />
        <div className="review-who">
          <strong>{name}</strong>
          <span className="review-why">
            {hi.reviewReason(String(entry.verdict?.status ?? ''), entry.type, String(entry.verdict?.detail ?? ''))}
          </span>
        </div>
        <span className="tag review-kind">{hi.itemKind[entry.type] ?? entry.type}</span>
      </div>
      {entry.reason && hi.reviewWhy[entry.reason] && (
        <span className="review-reason">
          <Icon name="info" size={14} />
          {hi.reviewWhy[entry.reason]}
        </span>
      )}
      <div className="review-target">
        {isSlate && prob ? (
          <span>
            {prob.a} {opSymbol(prob.op ?? '+')} {prob.b} = ?
          </span>
        ) : (
          <span lang="hi">{entry.text ?? entry.item_id}</span>
        )}
      </div>
      {produced && (
        <p className="review-heard">
          {hi.heard}: <b lang="hi">{produced}</b>
        </p>
      )}

      {isSlate ? (
        <>
          {media.busy && <Spinner />}
          {media.url && <img src={media.url} alt="" className="slate-crop" />}
          {media.error && <p className="warn-text">{media.error}</p>}
          <form
            className="row-form"
            onSubmit={(e) => {
              e.preventDefault();
              if (answer.trim()) void send({ answer: answer.trim() });
            }}
          >
            <label className="field grow">
              <span>{hi.slateAnswer}</span>
              <input inputMode="numeric" value={answer} onChange={(e) => setAnswer(e.target.value)} maxLength={6} />
            </label>
            <button className="btn btn-primary" disabled={busy || !answer.trim()}>
              {hi.confirm}
            </button>
          </form>
        </>
      ) : (
        <>
          {entry.media && (
            <button className="btn btn-block btn-outline" onClick={play} disabled={media.busy}>
              <Icon name="volume" size={18} />
              {media.busy ? hi.loading : hi.play}
            </button>
          )}
          {media.error && <p className="warn-text">{media.error}</p>}
          {!entry.media && <p className="review-nomedia">{hi.reviewNoMedia}</p>}
          <div className="two-btns">
            <button className="btn btn-ok" disabled={busy} onClick={() => send({ correct: true })}>
              <Icon name="check" size={18} />
              {hi.correctRead}
            </button>
            <button className="btn btn-danger" disabled={busy} onClick={() => send({ correct: false, ...(rule && rule !== 'OTHER' ? { rule } : {}) })}>
              <Icon name="alert" size={18} />
              {hi.wrongRead}
            </button>
          </div>
          <label className="field">
            <span className="small">{hi.errorType}</span>
            <select value={rule} onChange={(e) => setRule(e.target.value)}>
              <option value="">—</option>
              {Object.entries(hi.rules).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
          </label>
        </>
      )}
      <button className="btn btn-ghost btn-small review-skip" disabled={busy} onClick={() => onSkip(entry.id)}>
        {hi.reviewSkip}
      </button>
      <ErrorBox error={error} />
    </li>
  );
}

const BATCH = 5;

function BatchProgress({ done, goal }: { done: number; goal: number }) {
  return (
    <div className="batch" role="status">
      <div className="batch-top">
        <strong>{hi.reviewBatch(Math.min(done, goal), goal)}</strong>
        <span className="batch-sub">{hi.reviewBatchHelp}</span>
      </div>
      <div className="batch-bar" aria-hidden>
        {Array.from({ length: goal }, (_, i) => (
          <span key={i} className={i < done ? 'on' : ''} />
        ))}
      </div>
    </div>
  );
}

export default function UnsurePage() {
  const room = useClassroom()!;
  const [items, setItems] = useState<UnsureEntry[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [thanks, setThanks] = useState(0);
  const [goal, setGoal] = useState(BATCH);
  const [skipped, setSkipped] = useState<Set<string>>(new Set());
  const kids = useLive(() => db.children.where('classroom_id').equals(room.id).toArray(), [room.id], [] as LocalChild[]);
  const byId = new Map(kids.map((k) => [k.id, k]));

  const load = async () => {
    setError(null);
    try {
      const list = await api.unsure(room.id);
      setItems(list);
      await kvSet(KV_KEYS.unsureCount(room.id), list.length);
    } catch (e) {
      setError(e);
    }
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [room.id]);

  const done = (id: string) => {
    setThanks((n) => n + 1);
    setItems((prev) => {
      const next = (prev ?? []).filter((x) => x.id !== id);
      void kvSet(KV_KEYS.unsureCount(room.id), next.length);
      return next;
    });
  };

  // Skipped items stay on the server queue; they are only hidden for this visit.
  const visible = (items ?? []).filter((e) => !skipped.has(e.id));

  return (
    <AppShell narrow title={hi.unsureTitle} subtitle={items ? hi.reviewCount(items.length) : undefined}>
      <ErrorBox error={error} onRetry={load} />
      {!items && !error && <Spinner />}
      {items && items.length === 0 && <EmptyState icon="checkCircle" title={hi.unsureEmpty} />}
      {items && items.length > 0 && thanks === 0 && (
        <div className="banner banner-info">
          <Icon name="review" size={18} />
          {hi.unsureHelp}
        </div>
      )}
      {items && (visible.length > 0 || thanks > 0) && (
        <BatchProgress done={thanks} goal={Math.min(goal, thanks + visible.length)} />
      )}
      {items && thanks > 0 && thanks >= Math.min(goal, thanks + visible.length) && (
        <div className="batch-done">
          <Icon name="checkCircle" size={28} />
          <strong>{hi.reviewBatchDone}</strong>
          <span>{hi.reviewBatchDoneSub(visible.length)}</span>
          {visible.length > 0 && (
            <button className="btn btn-outline" onClick={() => setGoal(thanks + BATCH)}>
              {hi.reviewMore}
            </button>
          )}
        </div>
      )}
      <ul className="review-list">
        {visible.slice(0, Math.max(0, goal - thanks)).map((e) => (
          <UnsureCard
            key={e.id}
            entry={e}
            kid={byId.get(e.child_id)}
            onDone={done}
            onSkip={(id) => setSkipped((s) => new Set(s).add(id))}
          />
        ))}
      </ul>
    </AppShell>
  );
}
