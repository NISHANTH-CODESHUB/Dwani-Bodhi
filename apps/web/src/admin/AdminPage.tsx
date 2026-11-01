import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { ErrorBox, Notice, Spinner } from '../components/common';
import { Icon } from '../components/icons';
import { AppShell, Panel } from '../components/ui';
import { hi } from '../i18n/hi';
import { ApiError, api } from '../lib/api';
import { useAuth } from '../lib/auth';
import { pinProblem, PIN_MAX } from '../lib/pin';
import type { AdminClassroom, AdminUser, OrgKind, OrgUnitOut, Role, SchoolOut } from '../lib/types';

const t = hi.admin;
const KINDS: OrgKind[] = ['state', 'district', 'block', 'cluster'];
const ROLES: Role[] = ['teacher', 'admin'];
const GRADES = [1, 2, 3, 4, 5];

interface Data {
  units: OrgUnitOut[];
  schools: SchoolOut[];
  rooms: AdminClassroom[];
  users: AdminUser[];
}

/** 4xx errors carry a plain English reason from the server (weak PIN, duplicate phone, outside your unit). */
function reason(err: unknown): unknown {
  return err instanceof ApiError && err.kind === 'http' && err.status >= 400 && err.status < 500 && err.status !== 401
    ? err.detail
    : err;
}

/** "Uttar Pradesh › Hardoi › Sandila" for a unit (ancestors outside the caller's scope are skipped). */
function unitPath(units: OrgUnitOut[], id: string | null): string {
  const byId = new Map(units.map((u) => [u.id, u]));
  const parts: string[] = [];
  let cur = id ? byId.get(id) : undefined;
  while (cur) {
    parts.unshift(cur.name);
    cur = cur.parent_id ? byId.get(cur.parent_id) : undefined;
  }
  return parts.join(' › ');
}

function UnitSelect({
  units,
  value,
  onChange,
  allowNone,
  exclude,
  kinds,
}: {
  units: OrgUnitOut[];
  value: string;
  onChange: (v: string) => void;
  allowNone: boolean;
  exclude?: string | null;
  kinds?: OrgKind[];
}) {
  const options = units
    .filter((u) => u.id !== exclude && (!kinds || kinds.includes(u.kind)))
    .map((u) => ({ id: u.id, label: `${unitPath(units, u.id)} (${t.kinds[u.kind]})` }))
    .sort((a, b) => a.label.localeCompare(b.label));
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">{allowNone ? t.unitNone : t.unitChoose}</option>
      {options.map((o) => (
        <option key={o.id} value={o.id}>
          {o.label}
        </option>
      ))}
    </select>
  );
}

function ClassPicker({ rooms, value, onChange }: { rooms: AdminClassroom[]; value: string[]; onChange: (v: string[]) => void }) {
  if (rooms.length === 0) return <small className="field-hint">{t.noClasses}</small>;
  return (
    <div className="admin-checks">
      {rooms.map((r) => (
        <label key={r.id} className="admin-check">
          <input
            type="checkbox"
            checked={value.includes(r.id)}
            onChange={(e) => onChange(e.target.checked ? [...value, r.id] : value.filter((x) => x !== r.id))}
          />
          {r.school} — {r.name}
        </label>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------------------ accounts */
function AddAccount({ data, myUnit, onCreated }: { data: Data; myUnit: string | null; onCreated: (name: string, pin?: string) => void }) {
  const [role, setRole] = useState<Role>('teacher');
  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  const [pin, setPin] = useState('');
  const [unit, setUnit] = useState('');
  const [rooms, setRooms] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const cleanPhone = phone.replace(/\D/g, '');
  const pinIssue = pin ? pinProblem(pin, cleanPhone) : null;
  // Org-scoped admins must place every account inside their subtree; admins only strictly below themselves.
  const unitRequired = myUnit !== null && !(role === 'teacher' && rooms.length > 0);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (pinIssue) return;
    if (unitRequired && !unit) {
      setError(`${t.unit}: ${t.unitChoose}`);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await api.createUser({
        role,
        phone: cleanPhone,
        display_name: name.trim(),
        ...(pin ? { pin } : {}),
        org_unit_id: unit || null,
        classroom_ids: role === 'teacher' ? rooms : [],
      });
      onCreated(name.trim(), res.pin);
      setName('');
      setPhone('');
      setPin('');
      setRooms([]);
    } catch (err) {
      setError(reason(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Panel title={t.addAccount} icon="plus">
      <form className="form" onSubmit={submit}>
        <fieldset className="field">
          <legend>{t.role}</legend>
          <div className="seg">
            {ROLES.map((r) => (
              <button type="button" key={r} className={`seg-btn ${role === r ? 'seg-on' : ''}`} onClick={() => setRole(r)}>
                {hi.roles[r]}
              </button>
            ))}
          </div>
          <small className="field-hint">{t.roleHint[role]}</small>
        </fieldset>
        <div className="admin-grid">
          <label className="field">
            <span>{t.name}</span>
            <input value={name} onChange={(e) => setName(e.target.value)} required maxLength={120} autoComplete="off" />
          </label>
          <label className="field">
            <span>{hi.phone}</span>
            <input type="tel" inputMode="numeric" value={phone} onChange={(e) => setPhone(e.target.value)} required minLength={10} maxLength={20} placeholder="98XXXXXXXX" autoComplete="off" />
          </label>
          <label className="field">
            <span>{t.pinOptional}</span>
            <input inputMode="numeric" value={pin} maxLength={PIN_MAX} onChange={(e) => setPin(e.target.value.replace(/\D/g, ''))} autoComplete="off" />
            <small className="field-hint">{pinIssue && pin.length >= 6 ? <span className="warn-text">{pinIssue}</span> : t.pinOptionalHint}</small>
          </label>
          <label className="field">
            <span>{t.unit}</span>
            <UnitSelect
              units={data.units}
              value={unit}
              onChange={setUnit}
              allowNone={!unitRequired}
              exclude={role === 'admin' ? myUnit : null}
            />
          </label>
        </div>
        {role === 'teacher' && (
          <fieldset className="field">
            <legend>{t.classes}</legend>
            <ClassPicker rooms={data.rooms} value={rooms} onChange={setRooms} />
          </fieldset>
        )}
        <ErrorBox error={error} />
        <div className="form-actions">
          <button className="btn btn-primary form-save" disabled={busy || !!pinIssue}>
            <Icon name="check" size={18} />
            {busy ? hi.loading : t.create}
          </button>
        </div>
      </form>
    </Panel>
  );
}

function UserRow({ u, data, onChanged, onPin }: { u: AdminUser; data: Data; onChanged: () => void; onPin: (name: string, pin: string) => void }) {
  const me = useAuth()?.user.id;
  const [editing, setEditing] = useState(false);
  const [rooms, setRooms] = useState<string[]>(u.classrooms.map((c) => c.id));
  // The list reloads after every change: re-sync the checkboxes unless the admin is mid-edit.
  const serverRooms = u.classrooms.map((c) => c.id).join(',');
  useEffect(() => {
    if (!editing) setRooms(serverRooms ? serverRooms.split(',') : []);
  }, [serverRooms, editing]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (err) {
      setError(reason(err));
    } finally {
      setBusy(false);
    }
  };

  const where = u.org_unit_id ? unitPath(data.units, u.org_unit_id) || '—' : t.topLevel;
  return (
    <li className={`card admin-user ${u.active || u.pending ? '' : 'admin-user-off'}`}>
      <div className="admin-user-head">
        <div>
          <strong>{u.display_name}</strong>{' '}
          <span className="chip">{hi.roles[u.role]}</span> {u.is_self && <span className="chip">{t.you}</span>}{' '}
          {u.pending ? <span className="tag tag-warn">{t.pending}</span> : !u.active && <span className="tag tag-warn">{t.inactive}</span>}
          {u.pending && u.approver && (
            <div className="small">
              <strong>{u.approver.id === me ? t.sentToYou : t.sentTo(u.approver.display_name)}</strong>
            </div>
          )}
          <div className="small muted">{where}</div>
          {u.role === 'teacher' && (
            <div className="small muted">
              {u.classrooms.length ? u.classrooms.map((c) => `${c.school} — ${c.name}`).join(', ') : t.noClassLinked}
            </div>
          )}
        </div>
        {u.can_manage && u.pending && (
          <div className="admin-actions">
            <button
              className="btn btn-small btn-primary"
              disabled={busy}
              onClick={() => void run(async () => {
                await api.approveUser(u.id);
                onChanged();
              })}
            >
              <Icon name="check" size={16} />
              {t.approve}
            </button>
            <button
              className="btn btn-small btn-danger-ghost"
              disabled={busy}
              onClick={() =>
                window.confirm(t.rejectConfirm(u.display_name)) &&
                void run(async () => {
                  await api.rejectUser(u.id);
                  onChanged();
                })
              }
            >
              {t.reject}
            </button>
          </div>
        )}
        {u.can_manage && !u.pending && (
          <div className="admin-actions">
            {u.role === 'teacher' && u.active && (
              <button className="btn btn-small btn-ghost" disabled={busy} onClick={() => setEditing((v) => !v)}>
                <Icon name="school" size={16} />
                {t.editClasses}
              </button>
            )}
            {u.active && (
              <button
                className="btn btn-small btn-ghost"
                disabled={busy}
                onClick={() =>
                  window.confirm(t.resetConfirm(u.display_name)) &&
                  void run(async () => onPin(u.display_name, (await api.resetPin(u.id)).pin))
                }
              >
                <Icon name="lock" size={16} />
                {t.resetPin}
              </button>
            )}
            <button
              className={`btn btn-small ${u.active ? 'btn-danger-ghost' : 'btn-ghost'}`}
              disabled={busy}
              onClick={() =>
                (!u.active || window.confirm(t.deactivateConfirm(u.display_name))) &&
                void run(async () => {
                  await api.updateUser(u.id, { active: !u.active });
                  onChanged();
                })
              }
            >
              {u.active ? t.deactivate : t.activate}
            </button>
          </div>
        )}
      </div>
      {editing && (
        <div className="form admin-edit">
          <ClassPicker rooms={data.rooms} value={rooms} onChange={setRooms} />
          <div className="form-actions">
            <button
              className="btn btn-primary btn-small"
              disabled={busy}
              onClick={() =>
                void run(async () => {
                  await api.updateUser(u.id, { classroom_ids: rooms });
                  setEditing(false);
                  onChanged();
                })
              }
            >
              {t.saveClasses}
            </button>
          </div>
        </div>
      )}
      <ErrorBox error={error} />
    </li>
  );
}

/* ------------------------------------------------------------------------------ hierarchy */
function AddUnit({ data, myUnit, onDone }: { data: Data; myUnit: string | null; onDone: () => void }) {
  const [kind, setKind] = useState<OrgKind>(myUnit ? 'block' : 'state');
  const [name, setName] = useState('');
  const [parent, setParent] = useState('');
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const parentKinds = KINDS.slice(0, KINDS.indexOf(kind));
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.createOrgUnit({ kind, name: name.trim(), parent_id: parent || null });
      setName('');
      onDone();
    } catch (err) {
      setError(reason(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Panel title={t.addUnit} icon="plus">
      <form className="form" onSubmit={submit}>
        <fieldset className="field">
          <legend>{t.unitKind}</legend>
          <div className="seg">
            {KINDS.map((k) => (
              <button type="button" key={k} className={`seg-btn ${kind === k ? 'seg-on' : ''}`} onClick={() => { setKind(k); setParent(''); }}>
                {t.kinds[k]}
              </button>
            ))}
          </div>
        </fieldset>
        <div className="admin-grid">
          <label className="field">
            <span>{t.name}</span>
            <input value={name} onChange={(e) => setName(e.target.value)} required maxLength={200} />
          </label>
          {kind !== 'state' || myUnit ? (
            <label className="field">
              <span>{t.parent}</span>
              <UnitSelect units={data.units} value={parent} onChange={setParent} allowNone={!myUnit} kinds={parentKinds} />
            </label>
          ) : null}
        </div>
        <ErrorBox error={error} />
        <button className="btn btn-primary" disabled={busy}>
          {t.add}
        </button>
      </form>
    </Panel>
  );
}

function AddSchool({ data, myUnit, onDone }: { data: Data; myUnit: string | null; onDone: () => void }) {
  const [name, setName] = useState('');
  const [udise, setUdise] = useState('');
  const [unit, setUnit] = useState('');
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.createSchool({ name: name.trim(), udise_code: udise.trim() || undefined, org_unit_id: unit || null });
      setName('');
      setUdise('');
      onDone();
    } catch (err) {
      setError(reason(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Panel title={t.addSchool} icon="school">
      <form className="form" onSubmit={submit}>
        <div className="admin-grid">
          <label className="field">
            <span>{t.name}</span>
            <input value={name} onChange={(e) => setName(e.target.value)} required maxLength={200} />
          </label>
          <label className="field">
            <span>{t.udise}</span>
            <input value={udise} onChange={(e) => setUdise(e.target.value)} maxLength={32} />
          </label>
          <label className="field">
            <span>{t.unit}</span>
            <UnitSelect units={data.units} value={unit} onChange={setUnit} allowNone={!myUnit} />
          </label>
        </div>
        <ErrorBox error={error} />
        <button className="btn btn-primary" disabled={busy || (!!myUnit && !unit)}>
          {t.add}
        </button>
      </form>
    </Panel>
  );
}

function AddClass({ data, onDone }: { data: Data; onDone: () => void }) {
  const [school, setSchool] = useState('');
  const [name, setName] = useState('');
  const [grades, setGrades] = useState<number[]>([1, 2]);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.createClassroom({ school_id: school, name: name.trim(), grades: [...grades].sort() });
      setName('');
      onDone();
    } catch (err) {
      setError(reason(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Panel title={t.addClass} icon="users">
      <form className="form" onSubmit={submit}>
        <div className="admin-grid">
          <label className="field">
            <span>{t.school}</span>
            <select value={school} onChange={(e) => setSchool(e.target.value)} required>
              <option value="">{t.unitChoose}</option>
              {data.schools.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>{t.className}</span>
            <input value={name} onChange={(e) => setName(e.target.value)} required maxLength={120} placeholder="Class 1-2" />
          </label>
        </div>
        <fieldset className="field">
          <legend>{t.grades}</legend>
          <div className="seg">
            {GRADES.map((g) => (
              <button
                type="button"
                key={g}
                className={`seg-btn ${grades.includes(g) ? 'seg-on' : ''}`}
                onClick={() => setGrades(grades.includes(g) ? grades.filter((x) => x !== g) : [...grades, g])}
              >
                {g}
              </button>
            ))}
          </div>
        </fieldset>
        <ErrorBox error={error} />
        <button className="btn btn-primary" disabled={busy || grades.length === 0 || !school}>
          {t.add}
        </button>
      </form>
    </Panel>
  );
}

function Tree({ data }: { data: Data }) {
  const ids = new Set(data.units.map((u) => u.id));
  const roots = data.units.filter((u) => !u.parent_id || !ids.has(u.parent_id));
  const looseSchools = data.schools.filter((s) => !s.org_unit_id || !ids.has(s.org_unit_id));

  const schoolNode = (s: SchoolOut) => (
    <li key={s.id}>
      <span className="admin-node">
        <Icon name="school" size={16} /> {s.name}
        {s.udise_code && <span className="muted small"> · {s.udise_code}</span>}
      </span>
      <ul>
        {data.rooms
          .filter((r) => r.school_id === s.id)
          .map((r) => (
            <li key={r.id}>
              <span className="admin-node small">
                <Icon name="users" size={14} /> {r.name} ({r.grades.join(', ')}) —{' '}
                <span className="muted">{r.teachers.length ? t.teachersOf(r.teachers.map((x) => x.display_name).join(', ')) : t.noTeacher}</span>
              </span>
            </li>
          ))}
      </ul>
    </li>
  );

  const unitNode = (u: OrgUnitOut) => (
    <li key={u.id}>
      <span className="admin-node">
        <span className="chip">{t.kinds[u.kind]}</span> <strong>{u.name}</strong>
      </span>
      <ul>
        {data.units.filter((c) => c.parent_id === u.id).map(unitNode)}
        {data.schools.filter((s) => s.org_unit_id === u.id).map(schoolNode)}
      </ul>
    </li>
  );

  if (roots.length === 0 && looseSchools.length === 0) return <p className="muted">{t.emptyTree}</p>;
  return (
    <ul className="admin-tree">
      {roots.map(unitNode)}
      {looseSchools.map(schoolNode)}
    </ul>
  );
}

/* ------------------------------------------------------------------------------ page */
export default function AdminPage() {
  const auth = useAuth();
  const myUnit = auth?.user.org_unit_id ?? null;
  const [tab, setTab] = useState<'accounts' | 'hierarchy'>('accounts');
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [shownPin, setShownPin] = useState<{ name: string; pin: string } | null>(null);
  const [created, setCreated] = useState(false);
  const [roleFilter, setRoleFilter] = useState<Role | ''>('');

  const load = async () => {
    setError(null);
    try {
      const [units, schools, rooms, users] = await Promise.all([api.orgUnits(), api.schools(), api.adminClassrooms(), api.users()]);
      setData({ units, schools, rooms, users });
    } catch (err) {
      setError(err);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const scopeText = useMemo(() => {
    if (!myUnit) return t.scopeAll;
    return t.scopeUnit(data?.units.find((u) => u.id === myUnit)?.name ?? '…');
  }, [myUnit, data]);

  // Requests sent to me first; others above can still act on them (e.g. when the chosen admin is away).
  const me = auth?.user.id;
  const pending = (data?.users ?? []).filter((u) => u.pending)
    .sort((a, b) => Number(b.approver?.id === me) - Number(a.approver?.id === me));
  const users = (data?.users ?? []).filter((u) => !u.pending && (!roleFilter || u.role === roleFilter));

  return (
    <AppShell title={t.title} subtitle={scopeText}>
      {shownPin && (
        <div className="alert alert-ok admin-pin" role="status">
          <Icon name="lock" size={18} className="alert-ico" />
          <span className="alert-text">
            <strong className="admin-pin-value">{t.oneTimePin(shownPin.name, shownPin.pin)}</strong>
            <br />
            {t.oneTimePinHint}
          </span>
          <button className="btn btn-small btn-outline" onClick={() => setShownPin(null)}>
            {t.dismiss}
          </button>
        </div>
      )}
      {created && !shownPin && <Notice tone="ok">{t.created}</Notice>}
      <div className="seg admin-tabs">
        <button className={`seg-btn ${tab === 'accounts' ? 'seg-on' : ''}`} onClick={() => setTab('accounts')}>
          {t.tabAccounts}
        </button>
        <button className={`seg-btn ${tab === 'hierarchy' ? 'seg-on' : ''}`} onClick={() => setTab('hierarchy')}>
          {t.tabHierarchy}
        </button>
      </div>
      <ErrorBox error={error} onRetry={load} />
      {!data && !error && <Spinner />}
      {data && tab === 'accounts' && (
        <>
          {pending.length > 0 && (
            <Panel title={`${t.pendingTitle} (${pending.length})`} icon="alert" hint={t.pendingHint}>
              <ul className="admin-users">
                {pending.map((u) => (
                  <UserRow key={u.id} u={u} data={data} onChanged={load} onPin={(name, pin) => setShownPin({ name, pin })} />
                ))}
              </ul>
            </Panel>
          )}
          <AddAccount
            data={data}
            myUnit={myUnit}
            onCreated={(name, pin) => {
              setCreated(true);
              setShownPin(pin ? { name, pin } : null);
              void load();
            }}
          />
          <Panel
            title={t.accounts}
            icon="users"
            action={
              <div className="seg">
                {(['', ...ROLES] as const).map((r) => (
                  <button key={r || 'all'} className={`seg-btn ${roleFilter === r ? 'seg-on' : ''}`} onClick={() => setRoleFilter(r)}>
                    {r ? hi.roles[r] : t.allRoles}
                  </button>
                ))}
              </div>
            }
          >
            {users.length === 0 ? (
              <p className="muted">{t.noAccounts}</p>
            ) : (
              <ul className="admin-users">
                {users.map((u) => (
                  <UserRow key={u.id} u={u} data={data} onChanged={load} onPin={(name, pin) => setShownPin({ name, pin })} />
                ))}
              </ul>
            )}
          </Panel>
        </>
      )}
      {data && tab === 'hierarchy' && (
        <>
          <Panel title={t.tree} icon="chart">
            <Tree data={data} />
          </Panel>
          <AddUnit data={data} myUnit={myUnit} onDone={load} />
          <AddSchool data={data} myUnit={myUnit} onDone={load} />
          <AddClass data={data} onDone={load} />
        </>
      )}
    </AppShell>
  );
}
