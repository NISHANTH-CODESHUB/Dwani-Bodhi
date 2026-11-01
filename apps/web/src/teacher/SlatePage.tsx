import { useEffect, useRef, useState, type ChangeEvent } from 'react';
import { ErrorBox, Notice, useLive } from '../components/common';
import { Icon } from '../components/icons';
import { Page, Panel } from '../components/ui';
import { formatTime, hi, opSymbol } from '../i18n/hi';
import { useClassroom } from '../lib/auth';
import { KV_KEYS, db, kvGet, type LocalSlatePhoto } from '../lib/db';
import { prepareSlatePhoto } from '../lib/image';
import { requestSync } from '../lib/sync';
import type { TodayResponse } from '../lib/types';
import { uuid } from '../lib/uuid';

function Thumb({ id }: { id: string }) {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    let u: string | null = null;
    let live = true;
    void db.images.get(id).then((img) => {
      if (img && live) {
        u = URL.createObjectURL(img.blob);
        setUrl(u);
      }
    });
    return () => {
      live = false; // unmounted before the image loaded: never create the URL at all
      if (u) URL.revokeObjectURL(u);
    };
  }, [id]);
  return url ? (
    <img src={url} alt="" className="thumb" />
  ) : (
    <div className="thumb thumb-empty">
      <Icon name="camera" />
    </div>
  );
}

/** Guide drawing: where the slates and ID cards go in the frame. */
function FrameGuide() {
  return (
    <svg viewBox="0 0 320 200" className="frame-guide" role="img" aria-label={hi.slateHowTo}>
      <rect x="4" y="4" width="312" height="192" rx="10" fill="none" stroke="#2f56c4" strokeWidth="4" strokeDasharray="12 8" />
      {[0, 1, 2, 3].map((i) => (
        <g key={i} transform={`translate(${20 + i * 74} 50)`}>
          <rect width="64" height="100" rx="6" fill="#1f2937" />
          <rect x="18" y="-10" width="28" height="22" rx="3" fill="#facc15" stroke="#111827" />
          <text x="32" y="6" textAnchor="middle" fontSize="11" fill="#111827">
            ID
          </text>
          <text x="32" y="65" textAnchor="middle" fontSize="16" fill="#f8fafc">
            ✎
          </text>
        </g>
      ))}
    </svg>
  );
}

export default function SlatePage() {
  const room = useClassroom()!;
  const fileRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const today = useLive(() => kvGet<TodayResponse>(KV_KEYS.today(room.id)), [room.id], undefined);
  const photos = useLive(
    async () => (await db.slatePhotos.where('classroom_id').equals(room.id).sortBy('taken_at')).reverse().slice(0, 20),
    [room.id],
    [] as LocalSlatePhoto[],
  );
  const problems = today?.slate_problems ?? [];

  const onFile = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      const img = await prepareSlatePhoto(file);
      const id = uuid();
      await db.transaction('rw', db.slatePhotos, db.images, async () => {
        await db.images.put({ id, blob: img.blob, mime: img.mime, size: img.blob.size });
        await db.slatePhotos.put({
          id,
          classroom_id: room.id,
          taken_at: new Date().toISOString(),
          problems,
          size: img.blob.size,
          synced: 0,
          sync_error: null,
        });
      });
      setSaved(true);
      requestSync();
    } catch (err) {
      setError(err instanceof DOMException && err.name === 'QuotaExceededError' ? hi.saveError : hi.slateImageError);
    } finally {
      setBusy(false);
    }
  };

  const remove = async (p: LocalSlatePhoto) => {
    if (!window.confirm(hi.slateDeleteConfirm)) return;
    await db.transaction('rw', db.slatePhotos, db.images, async () => {
      await db.slatePhotos.delete(p.id);
      await db.images.delete(p.id);
    });
    requestSync();
  };

  return (
    <Page narrow title={hi.slateTitle} back="/">
      {problems.length === 0 ? (
        <Notice tone="warn">{hi.slateNoProblems}</Notice>
      ) : (
        <Panel title={hi.slateWrite} icon="calc">
          <div className="board">
            {problems.map((p, i) => (
              <div key={p.item_id} className="board-problem">
                <span className="board-num">{i + 1}.</span> {p.a} {opSymbol(p.op)} {p.b} = ?
              </div>
            ))}
          </div>
        </Panel>
      )}

      <Panel title={hi.slateTitle} icon="camera">
        <FrameGuide />
        <p className="muted">{hi.slateHowTo}</p>
        <input
          ref={fileRef}
          type="file"
          accept="image/*"
          capture="environment"
          hidden
          onChange={onFile}
        />
        <button
          className="btn btn-primary btn-block btn-big"
          disabled={busy || problems.length === 0}
          onClick={() => fileRef.current?.click()}
        >
          <Icon name="camera" size={20} />
          {busy ? hi.slateProcessing : hi.slateTake}
        </button>
        {saved && <Notice tone="ok">{hi.slateSaved}</Notice>}
        <ErrorBox error={error} />
      </Panel>

      {photos.length > 0 && (
        <Panel title={hi.slatePhotos} icon="clipboard">
          <ul className="photo-list">
            {photos.map((p) => (
              <li key={p.id} className="photo-row">
                {p.synced === 0 ? (
                  <Thumb id={p.id} />
                ) : (
                  <div className={`thumb thumb-empty ${p.synced === 2 ? 'thumb-warn' : 'thumb-ok'}`}>
                    <Icon name={p.synced === 1 ? 'checkCircle' : 'alert'} />
                  </div>
                )}
                <span className="row-text">
                  <span className="row-title">{formatTime(p.taken_at)}</span>
                  <span className={`row-sub ${p.synced === 2 ? 'warn-text' : ''}`}>
                    {p.synced === 1 ? hi.slateUploaded : p.synced === 2 ? p.sync_error : hi.slatePending} ·{' '}
                    {p.problems.map((x) => `${x.a}${opSymbol(x.op)}${x.b}`).join(', ')} · {Math.round(p.size / 1024)} KB
                  </span>
                </span>
                {p.synced === 0 && (
                  <button className="icon-btn icon-btn-subtle" aria-label={hi.delete} onClick={() => remove(p)}>
                    <Icon name="trash" size={18} />
                  </button>
                )}
              </li>
            ))}
          </ul>
        </Panel>
      )}
    </Page>
  );
}
