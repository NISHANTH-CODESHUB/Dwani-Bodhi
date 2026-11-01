import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { ClassFields, classValid, EMPTY_CLASS, type ClassValues } from '../components/ClassFields';
import { ErrorBox, Notice } from '../components/common';
import { Icon } from '../components/icons';
import { Page, Panel } from '../components/ui';
import { hi } from '../i18n/hi';
import { ApiError, api } from '../lib/api';
import { getAuth, setAuth, setClassroom, useAuth, useClassroom } from '../lib/auth';
import { runSync } from '../lib/sync';
import type { ClassroomInfo } from '../lib/types';
import { LogoutButton } from './LogoutButton';

function formError(err: unknown): unknown {
  return err instanceof ApiError && err.kind === 'http' && err.status >= 400 && err.status < 500 ? err.detail : err;
}

function saveClassrooms(classrooms: ClassroomInfo[]): void {
  const a = getAuth();
  if (a) setAuth({ ...a, classrooms });
}

/** New class: the school field starts with the teacher's current school (the server reuses it by name). */
function AddClassForm({ school, onDone, onCancel }: { school: string; onDone: (id: string) => void; onCancel?: () => void }) {
  const [v, setV] = useState<ClassValues>({ ...EMPTY_CLASS, school_name: school });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!classValid(v)) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api.createClassroom({
        school_name: v.school_name.trim(),
        class_name: v.class_name.trim(),
        grades: v.grades,
        region_profile: v.region_profile,
      });
      saveClassrooms(res.classrooms);
      onDone(res.id);
    } catch (err) {
      setError(formError(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Panel title={hi.addClassTitle} icon="plus">
      <form onSubmit={submit} className="form">
        <ClassFields value={v} onChange={setV} />
        <ErrorBox error={error} />
        <div className="form-actions">
          <button className="btn btn-primary btn-lg" disabled={busy || !classValid(v)}>
            {busy ? hi.loading : hi.addClassSave}
          </button>
          {onCancel && (
            <button type="button" className="btn btn-ghost" onClick={onCancel}>
              {hi.cancel}
            </button>
          )}
        </div>
      </form>
    </Panel>
  );
}

function EditClassForm({ room, onDone }: { room: ClassroomInfo; onDone: () => void }) {
  const [v, setV] = useState<ClassValues>({
    school_name: room.school ?? '',
    class_name: room.name,
    grades: room.grades,
    region_profile: room.region_profile,
  });
  const [minutes, setMinutes] = useState(String(room.daily_kiosk_budget_min));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const mins = Number(minutes);
  const ok = classValid(v, false) && Number.isFinite(mins) && mins >= 3 && mins <= 60;
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!ok) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api.updateClassroom(room.id, {
        name: v.class_name.trim(),
        grades: v.grades,
        region_profile: v.region_profile,
        daily_kiosk_budget_min: mins,
      });
      saveClassrooms(res.classrooms);
      onDone();
    } catch (err) {
      setError(formError(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <form onSubmit={submit} className="form class-edit">
      <ClassFields value={v} onChange={setV} withSchool={false} />
      <label className="field">
        <span>{hi.kioskMinutes}</span>
        <input type="number" inputMode="numeric" min={3} max={60} value={minutes} onChange={(e) => setMinutes(e.target.value)} />
      </label>
      <ErrorBox error={error} />
      <div className="form-actions">
        <button className="btn btn-primary" disabled={busy || !ok}>
          {busy ? hi.loading : hi.editClassSave}
        </button>
        <button type="button" className="btn btn-ghost" onClick={onDone}>
          {hi.cancel}
        </button>
      </div>
    </form>
  );
}

export function ClassPickPage() {
  const auth = useAuth();
  const current = useClassroom();
  const nav = useNavigate();
  const rooms = auth?.classrooms ?? [];
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);

  const pick = (id: string) => {
    setClassroom(id);
    void runSync({ manual: true });
    nav('/', { replace: true });
  };

  return (
    <Page narrow title={hi.myClasses} back={current ? '/' : undefined} right={current ? undefined : <LogoutButton />}>
      {rooms.length === 0 && <Notice tone="warn">{hi.noClassrooms}</Notice>}
      {rooms.length > 0 && <p className="muted">{hi.chooseClass}</p>}
      <div className="list">
        {rooms.map((r) => (
          <div key={r.id} className="class-row">
            <div className="class-row-main">
              <button className={`row-link ${r.id === current?.id ? 'row-active' : ''}`} onClick={() => pick(r.id)}>
                <span className="row-icon" aria-hidden>
                  <Icon name="school" />
                </span>
                <span className="row-text">
                  <span className="row-title">{r.name}</span>
                  <span className="row-sub">
                    {r.school ?? ''} · {r.grades.map((g) => hi.gradeN(g)).join(', ')}
                  </span>
                </span>
                {r.id === current?.id ? <Icon name="checkCircle" className="row-check" /> : <Icon name="chevronRight" className="row-chev" />}
              </button>
              <button
                className="icon-btn icon-btn-subtle"
                onClick={() => setEditing(editing === r.id ? null : r.id)}
                aria-expanded={editing === r.id}
                aria-label={`${hi.editClass}: ${r.name}`}
                title={hi.editClass}
              >
                <Icon name="edit" size={18} />
              </button>
            </div>
            {editing === r.id && <EditClassForm room={r} onDone={() => setEditing(null)} />}
          </div>
        ))}
      </div>
      {rooms.length === 0 || adding ? (
        <AddClassForm
          school={current?.school ?? rooms[0]?.school ?? ''}
          onDone={(id) => {
            setAdding(false);
            pick(id);
          }}
          onCancel={rooms.length ? () => setAdding(false) : undefined}
        />
      ) : (
        <button className="btn btn-outline btn-block" onClick={() => setAdding(true)}>
          <Icon name="plus" size={18} />
          {hi.addClass}
        </button>
      )}
    </Page>
  );
}
