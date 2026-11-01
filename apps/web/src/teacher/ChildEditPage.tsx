import { useEffect, useState, type FormEvent } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { RegisterNo } from '../components/activity';
import { ErrorBox, Spinner } from '../components/common';
import { Icon } from '../components/icons';
import { Page } from '../components/ui';
import { hi } from '../i18n/hi';
import { useClassroom } from '../lib/auth';
import { db, type LocalChild } from '../lib/db';
import { requestSync } from '../lib/sync';
import type { ConsentStatus, Gender } from '../lib/types';
import { uuid } from '../lib/uuid';

const CONSENTS: ConsentStatus[] = ['pending', 'granted', 'withdrawn'];

export default function ChildEditPage() {
  const { id } = useParams();
  const room = useClassroom()!;
  const nav = useNavigate();
  const isNew = !id;
  const [loaded, setLoaded] = useState(isNew);
  const [existing, setExisting] = useState<LocalChild | null>(null);
  const [name, setName] = useState('');
  const [grade, setGrade] = useState<number>(room.grades[0] ?? 1);
  const [slot, setSlot] = useState<string>('');
  const [gender, setGender] = useState<Gender | ''>('');
  const [consent, setConsent] = useState<ConsentStatus>('pending');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isNew) {
      // Suggest the lowest free ID-card number.
      void db.children
        .where('classroom_id')
        .equals(room.id)
        .filter((c) => !c.deleted)
        .toArray()
        .then((all) => {
          const used = new Set(all.map((c) => c.aruco_slot));
          let s = 1;
          while (used.has(s) && s < 99) s++;
          setSlot(String(s));
        });
      return;
    }
    void db.children.get(id).then((c) => {
      // Unknown, erased or another class's child: "edit" would silently create a new child instead.
      if (!c || c.deleted || c.classroom_id !== room.id) {
        nav('/roster', { replace: true });
        return;
      }
      setExisting(c);
      setName(c.name);
      setGrade(c.grade);
      setSlot(String(c.aruco_slot));
      setGender(c.gender ?? '');
      setConsent(c.consent_status);
      setLoaded(true);
    });
  }, [id, isNew, room.id, nav]);

  if (!loaded) return <Spinner />;

  const grades = Array.from(new Set([...room.grades, 1, 2, 3])).sort();

  const save = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    const slotN = Number(slot);
    if (!Number.isInteger(slotN) || slotN < 0 || slotN > 99) {
      setError(hi.slotHint);
      return;
    }
    const clash = await db.children
      .where('classroom_id')
      .equals(room.id)
      .filter((c) => !c.deleted && c.aruco_slot === slotN && c.id !== existing?.id)
      .count();
    if (clash) {
      setError(hi.slotTaken);
      return;
    }
    const now = new Date().toISOString();
    const row: LocalChild = {
      id: existing?.id ?? uuid(),
      classroom_id: room.id,
      name: name.trim(),
      grade,
      aruco_slot: slotN,
      register_no: existing?.register_no ?? null, // server-owned: keep it across local edits
      gender: gender || null,
      consent_status: consent,
      consent_date:
        consent === existing?.consent_status ? (existing?.consent_date ?? null) : consent === 'granted' ? now : null,
      dirty: 1,
      deleted: 0,
      sync_error: null,
      updated_at: now,
    };
    // Name-only edits don't need a server round trip (the server never sees names).
    const serverFieldsSame =
      existing &&
      existing.dirty === 0 &&
      existing.grade === row.grade &&
      existing.aruco_slot === row.aruco_slot &&
      existing.gender === row.gender &&
      existing.consent_status === row.consent_status;
    if (serverFieldsSame) row.dirty = 0;
    try {
      await db.children.put(row);
    } catch {
      setError(hi.saveError);
      return;
    }
    requestSync();
    nav('/roster', { replace: true });
  };

  const remove = async () => {
    if (!existing || !window.confirm(hi.deleteChildConfirm)) return;
    await db.children.update(existing.id, { deleted: 1, consent_status: 'withdrawn' });
    requestSync();
    nav('/roster', { replace: true });
  };

  return (
    <Page narrow title={isNew ? hi.addChild : hi.editChild} back="/roster">
      <form className="panel form form-narrow" onSubmit={save}>
        {!isNew && (
          <div className="field">
            <span>{hi.act.registerNo}</span>
            <div>
              <RegisterNo value={existing?.register_no} large />
            </div>
          </div>
        )}
        <label className="field">
          <span>{hi.childName}</span>
          <input value={name} onChange={(e) => setName(e.target.value)} required maxLength={60} autoComplete="off" />
          <small className="field-hint">
            <Icon name="lock" size={14} /> {hi.nameNote}
          </small>
        </label>

        <fieldset className="field">
          <legend>{hi.grade}</legend>
          <div className="seg">
            {grades.map((g) => (
              <button type="button" key={g} className={`seg-btn ${grade === g ? 'seg-on' : ''}`} onClick={() => setGrade(g)}>
                {g}
              </button>
            ))}
          </div>
        </fieldset>

        <label className="field">
          <span>{hi.slot}</span>
          <input type="number" inputMode="numeric" min={0} max={99} value={slot} onChange={(e) => setSlot(e.target.value)} required />
          <small className="field-hint">{hi.slotHint}</small>
        </label>

        <fieldset className="field">
          <legend>{hi.gender}</legend>
          <div className="seg">
            {(['f', 'm', 'x'] as Gender[]).map((g) => (
              <button
                type="button"
                key={g}
                className={`seg-btn ${gender === g ? 'seg-on' : ''}`}
                onClick={() => setGender(gender === g ? '' : g)}
              >
                {hi.genders[g]}
              </button>
            ))}
          </div>
        </fieldset>

        <fieldset className="field consent-box">
          <legend>{hi.consent}</legend>
          <p className="consent-text">{hi.consentText}</p>
          <div className="seg">
            {CONSENTS.map((c) => (
              <button
                type="button"
                key={c}
                className={`seg-btn ${consent === c ? (c === 'granted' ? 'seg-ok' : 'seg-on') : ''}`}
                onClick={() => setConsent(c)}
              >
                {hi.consentStates[c]}
              </button>
            ))}
          </div>
          {consent !== 'granted' && <small className="warn-text">{hi.consentRequired}</small>}
        </fieldset>

        {existing?.sync_error === 'slot_clash' && <ErrorBox error={hi.slotClash} />}
        <ErrorBox error={error} />
        <div className="form-actions">
          {existing && (
            <button type="button" className="btn btn-danger-ghost" onClick={remove}>
              <Icon name="trash" size={18} />
              {hi.delete}
            </button>
          )}
          <button className="btn btn-primary form-save">
            <Icon name="check" size={18} />
            {hi.save}
          </button>
        </div>
      </form>
    </Page>
  );
}
