import { useEffect, useState, type FormEvent } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { RegisterNo, StudentActivityPanels, StudentFacts, StudentStats } from '../components/activity';
import { ErrorBox, Notice, Spinner } from '../components/common';
import { Icon } from '../components/icons';
import { EmptyState, Page, Panel } from '../components/ui';
import { hi } from '../i18n/hi';
import { ApiError, api } from '../lib/api';
import type { ChildProfile, ConsentStatus, StudentActivity } from '../lib/types';

const t = hi.dash;
const a = hi.act;

function Manage({ data, onSaved }: { data: StudentActivity; onSaved: (next: StudentActivity) => void }) {
  const nav = useNavigate();
  const s = data.student;
  const [grade, setGrade] = useState(s.grade);
  const [consent, setConsent] = useState<ConsentStatus>(s.consent);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const changed = grade !== s.grade || consent !== s.consent;

  const reason = (e: unknown) => (e instanceof ApiError && e.kind === 'http' && e.status < 500 && e.status !== 401 ? e.detail : e);

  const save = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      const row = await api.updateStudent(s.id, { grade, consent_status: consent });
      onSaved({ ...data, student: row });
      setSaved(true);
    } catch (err) {
      setError(reason(err));
    } finally {
      setBusy(false);
    }
  };

  const erase = async () => {
    if (!window.confirm(t.eraseConfirm(s.register_no ?? s.id))) return;
    setBusy(true);
    setError(null);
    try {
      await api.deleteChild(s.id);
      nav('/admin/students', { replace: true, state: { erased: s.register_no } });
    } catch (err) {
      setError(reason(err));
      setBusy(false);
    }
  };

  return (
    <Panel title={t.manage} icon="edit">
      <form className="form" onSubmit={save}>
        <fieldset className="field">
          <legend>{a.grade}</legend>
          <div className="seg">
            {[1, 2, 3, 4, 5].map((g) => (
              <button type="button" key={g} className={`seg-btn ${grade === g ? 'seg-on' : ''}`} onClick={() => setGrade(g)}>
                {g}
              </button>
            ))}
          </div>
        </fieldset>
        <fieldset className="field">
          <legend>{a.consent}</legend>
          <div className="seg">
            {(['granted', 'pending', 'withdrawn'] as const).map((c) => (
              <button type="button" key={c} className={`seg-btn ${consent === c ? 'seg-on' : ''}`} onClick={() => setConsent(c)}>
                {a.consentLabel[c]}
              </button>
            ))}
          </div>
        </fieldset>
        {saved && <Notice tone="ok">{t.saved}</Notice>}
        <ErrorBox error={error} />
        <div className="form-actions form-actions-split">
          <button type="button" className="btn btn-danger-ghost" disabled={busy} onClick={() => void erase()}>
            <Icon name="trash" size={18} />
            {t.erase}
          </button>
          <button className="btn btn-primary" disabled={busy || !changed}>
            <Icon name="check" size={18} />
            {busy ? hi.loading : t.save}
          </button>
        </div>
      </form>
    </Panel>
  );
}

export default function AdminStudentPage() {
  const { id = '' } = useParams();
  const [data, setData] = useState<StudentActivity | null>(null);
  const [profile, setProfile] = useState<ChildProfile | null>(null);
  const [error, setError] = useState<unknown>(null);

  const load = async () => {
    setError(null);
    try {
      const [act, prof] = await Promise.all([api.studentActivity(id), api.profile(id)]);
      setData(act);
      setProfile(prof);
    } catch (e) {
      setError(e);
    }
  };

  useEffect(() => {
    setData(null);
    setProfile(null);
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const confirmed = profile?.confusions.filter((c) => c.status === 'confirmed') ?? [];
  const reg = data?.student.register_no;

  return (
    <Page title={reg ? t.studentTitle(reg) : hi.dash.studentsTitle} back="/admin/students">
      <ErrorBox error={error} onRetry={load} />
      {!data && !error && <Spinner />}
      {data && (
        <>
          <section className="profile-hero">
            <span className="avatar avatar-noname" style={{ width: 64, height: 64, fontSize: 20 }} aria-hidden>
              #{data.student.aruco_slot}
            </span>
            <div className="profile-hero-text">
              <div className="profile-name">
                <RegisterNo value={reg} large />
              </div>
              <div className="profile-meta">
                {data.student.school} — {data.student.classroom} · {hi.gradeN(data.student.grade)}
              </div>
              <div className="profile-meta muted small">{t.namesNote}</div>
            </div>
          </section>
          <StudentStats s={data.student} />
          <div className="dash-grid dash-grid-2">
            <div className="dash-col">
              <Panel title={hi.profile} icon="idcard">
                <StudentFacts s={data.student} />
              </Panel>
              <Panel title={a.confusions} icon="alert" hint={hi.confusionsHint}>
                {confirmed.length === 0 ? (
                  <EmptyState icon="checkCircle" title={hi.noConfusions} />
                ) : (
                  confirmed.map((c) => (
                    <div key={c.id} className="confusion confusion-sure">
                      <div className="confusion-head">
                        <span className="confusion-icon" aria-hidden>
                          <Icon name={c.domain === 'numeracy' ? 'calc' : 'book'} size={16} />
                        </span>
                        <span className="confusion-title">{c.description_hi}</span>
                        <span className="band band-notyet">{c.certainty_hi}</span>
                      </div>
                    </div>
                  ))
                )}
              </Panel>
              <Manage data={data} onSaved={setData} />
            </div>
            <div className="dash-col">
              <StudentActivityPanels data={data} />
            </div>
          </div>
        </>
      )}
    </Page>
  );
}
