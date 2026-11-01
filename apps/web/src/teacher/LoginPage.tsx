import { useEffect, useState, type FormEvent } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import { ErrorBox } from '../components/common';
import { PinChangeForm } from '../components/PinChangeForm';
import { Icon } from '../components/icons';
import { hi } from '../i18n/hi';
import { ApiError, api } from '../lib/api';
import { getClassroomId, homePath, setAuth, useAuth } from '../lib/auth';
import { NO_LOGIN } from '../lib/config';
import { runSync } from '../lib/sync';
import { pinProblem, PIN_MAX } from '../lib/pin';
import type { Approver, LoginResponse, Role, SignupOptions } from '../lib/types';

/** Keep digits and a leading + only (pasted numbers often carry spaces, dashes or brackets). */
const normalizePhone = (raw: string) => raw.trim().replace(/(?!^\+)[^\d]/g, '');

/** Login-screen wording: the generic texts ("work offline", "session expired") make no sense before sign-in. */
function loginError(err: unknown): unknown {
  if (!(err instanceof ApiError)) return err;
  if (err.kind !== 'http') return hi.loginOffline;
  if (err.status === 401) return hi.loginWrong;
  // 403 = right PIN but the account still waits for approval; 429 = lockout. The server text says what to do.
  if (err.status === 403 || err.status === 429) return err.detail;
  return err;
}

export function LoginPage() {
  const auth = useAuth();
  const nav = useNavigate();
  const [phone, setPhone] = useState('');
  const [pin, setPin] = useState('');
  const [busy, setBusy] = useState(false);
  const [showPin, setShowPin] = useState(false);
  const [error, setError] = useState<unknown>(null);
  // Weak PIN: the server issued a token that can only change the PIN. Nothing is stored until it is changed.
  const [forced, setForced] = useState<{ token: string; reason?: string; pin: string } | null>(null);

  // Brand-new installation (no accounts yet): show the one-time "create the top-level admin" form.
  const [setupNeeded, setSetupNeeded] = useState(false);
  const [signup, setSignup] = useState(false);
  useEffect(() => {
    if (!NO_LOGIN) api.setupStatus().then((r) => setSetupNeeded(r.needed), () => undefined);
  }, []);

  if (auth) return <Navigate to={homePath(auth.user.role)} replace />;

  const enter = (res: LoginResponse) => {
    setAuth({ token: res.token, user: res.user, classrooms: res.classrooms });
    void runSync({ manual: true });
    if (res.user.role !== 'teacher') nav(homePath(res.user.role), { replace: true });
    else nav(getClassroomId() ? '/' : '/classes', { replace: true });
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await api.login(normalizePhone(phone), pin);
      if (res.pin_change_required) {
        setForced({ token: res.token, reason: res.pin_problem, pin });
        setPin('');
        return;
      }
      enter(res);
    } catch (err) {
      setError(loginError(err));
    } finally {
      setBusy(false);
    }
  };

  const open = async (role: string) => {
    setBusy(true);
    setError(null);
    try {
      enter(await api.openSession(role));
    } catch (err) {
      setError(loginError(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login">
      <aside className="login-brand">
        <div className="login-brand-top">
          <img src="/icons/icon-192.png" alt="" width={48} height={48} className="brand-mark" />
          <div className="brand-text">
            <span className="brand-name">{hi.appName}</span>
            <span className="brand-sub">{hi.appSub}</span>
          </div>
        </div>
        <p className="login-tagline">{hi.tagline}</p>
        <ul className="login-features">
          {hi.loginFeatures.map((f) => (
            <li key={f}>
              <Icon name="checkCircle" size={20} />
              {f}
            </li>
          ))}
        </ul>
      </aside>
      <main className="login-main">
        {NO_LOGIN ? (
          <div className="login-card">
            <div className="login-card-head">
              <h1>{hi.loginWelcome}</h1>
              <p className="muted">{hi.openSub}</p>
            </div>
            {['teacher', 'crcc', 'admin'].map((role) => (
              <button key={role} className="btn btn-primary btn-block btn-lg" disabled={busy} onClick={() => void open(role)}>
                {hi.openAs(hi.roles[role])}
              </button>
            ))}
            <ErrorBox error={error} />
          </div>
        ) : setupNeeded ? (
          <SetupForm onDone={enter} />
        ) : signup ? (
          <SignupForm onBack={() => setSignup(false)} onEnter={enter} />
        ) : forced ? (
          <div className="login-card">
            <div className="login-card-head">
              <h1>{hi.pinForcedTitle}</h1>
              <p className="muted">{hi.pinForcedSub}</p>
            </div>
            {forced.reason && <p className="warn-text">{forced.reason}</p>}
            <PinChangeForm token={forced.token} phone={normalizePhone(phone)} currentPin={forced.pin} onDone={enter} />
          </div>
        ) : (
        <form onSubmit={submit} className="login-card">
          <div className="login-card-head">
            <h1>{hi.loginWelcome}</h1>
            <p className="muted">{hi.loginSub}</p>
          </div>
          <label className="field">
            <span>{hi.phone}</span>
            <input
              type="tel"
              inputMode="numeric"
              autoComplete="tel"
              required
              minLength={6}
              maxLength={20}
              placeholder="98XXXXXXXX"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
            />
          </label>
          <label className="field">
            <span>{hi.pin}</span>
            <span className="pin-wrap">
              <input
                type={showPin ? 'text' : 'password'}
                inputMode="numeric"
                autoComplete="current-password"
                required
                minLength={4}
                maxLength={12}
                value={pin}
                onChange={(e) => setPin(e.target.value.replace(/\D/g, ''))}
              />
              <button type="button" className="pin-eye" onClick={() => setShowPin((v) => !v)} aria-label={showPin ? hi.hidePin : hi.showPin}>
                <Icon name={showPin ? 'eyeOff' : 'eye'} />
              </button>
            </span>
          </label>
          <ErrorBox error={error} />
          <button className="btn btn-primary btn-block btn-lg" disabled={busy}>
            {busy ? hi.loading : hi.login}
          </button>
          <button type="button" className="btn btn-outline btn-block" onClick={() => { setError(null); setSignup(true); }}>
            <Icon name="plus" size={18} />
            {hi.signupLink}
          </button>
          <p className="login-privacy">
            <Icon name="shield" size={16} />
            {hi.loginPrivacy}
          </p>
        </form>
        )}
      </main>
    </div>
  );
}

/** First-run only: creates the global (top-level) admin, then logs straight in. */
function SetupForm({ onDone }: { onDone: (res: LoginResponse) => void }) {
  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  const [pin, setPin] = useState('');
  const [again, setAgain] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const cleanPhone = phone.replace(/\D/g, '');
  const problem = pin ? pinProblem(pin, cleanPhone) : null;
  const mismatch = again.length > 0 && again !== pin;
  const ready = !!name.trim() && cleanPhone.length >= 10 && !!pin && !problem && again === pin;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!ready) return;
    setBusy(true);
    setError(null);
    try {
      onDone(await api.setup({ phone: cleanPhone, pin, display_name: name.trim() }));
    } catch (err) {
      setError(err instanceof ApiError && (err.status === 409 || err.status === 422) ? err.detail : err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="login-card">
      <div className="login-card-head">
        <h1>{hi.setupTitle}</h1>
        <p className="muted">{hi.setupSub}</p>
      </div>
      <label className="field">
        <span>{hi.setupName}</span>
        <input value={name} onChange={(e) => setName(e.target.value)} required maxLength={120} autoComplete="name" />
      </label>
      <label className="field">
        <span>{hi.phone}</span>
        <input type="tel" inputMode="numeric" autoComplete="tel" required minLength={10} maxLength={20} placeholder="98XXXXXXXX" value={phone} onChange={(e) => setPhone(e.target.value)} />
      </label>
      <label className="field">
        <span>{hi.pinNew}</span>
        <input type="password" inputMode="numeric" autoComplete="new-password" maxLength={PIN_MAX} value={pin} onChange={(e) => setPin(e.target.value.replace(/\D/g, ''))} />
      </label>
      {problem && pin.length >= 6 && <p className="warn-text">{problem}</p>}
      <label className="field">
        <span>{hi.pinAgain}</span>
        <input type="password" inputMode="numeric" autoComplete="new-password" maxLength={PIN_MAX} value={again} onChange={(e) => setAgain(e.target.value.replace(/\D/g, ''))} />
      </label>
      {mismatch && <p className="warn-text">{hi.pinMismatch}</p>}
      <ErrorBox error={error} />
      <button className="btn btn-primary btn-block btn-lg" disabled={busy || !ready}>
        {busy ? hi.loading : hi.setupCreate}
      </button>
    </form>
  );
}

const SIGNUP_ROLES: Role[] = ['teacher', 'admin'];

/**
 * "Create account". Teachers: a pending request that an admin above the class approves (every such admin
 * is notified). Admins: the account is ready at once and the user is signed in straight away.
 */
function SignupForm({ onBack, onEnter }: { onBack: () => void; onEnter: (res: LoginResponse) => void }) {
  const [opts, setOpts] = useState<SignupOptions | null>(null);
  const [role, setRole] = useState<Role>('teacher');
  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  const [pin, setPin] = useState('');
  const [again, setAgain] = useState('');
  const [room, setRoom] = useState('');
  const [unit, setUnit] = useState('');
  const [approvers, setApprovers] = useState<Approver[] | null>(null);
  const [approver, setApprover] = useState('');
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    api.signupOptions().then(setOpts, setError);
  }, []);

  // Who can approve depends on the role and the chosen place; reload the list whenever they change.
  useEffect(() => {
    setApprover('');
    setApprovers(null);
    const place = role === 'teacher' && room ? { classroom_id: room } : null; // admins need no approver
    if (!place) return;
    let live = true;
    api.approvers(role, place).then(
      (list) => {
        if (!live) return;
        setApprovers(list);
        if (list.length === 1) setApprover(list[0].id);
      },
      (err) => live && setError(err),
    );
    return () => {
      live = false;
    };
  }, [role, room, unit]);

  const cleanPhone = phone.replace(/\D/g, '');
  const problem = pin ? pinProblem(pin, cleanPhone) : null;
  const mismatch = again.length > 0 && again !== pin;
  const placed = role === 'teacher' ? !!room : !!unit;
  const needsApprover = role === 'teacher';
  const ready =
    !!name.trim() && cleanPhone.length >= 10 && !!pin && !problem && again === pin && placed && (!needsApprover || !!approver);

  const unitLabel = (id: string): string => {
    const byId = new Map((opts?.units ?? []).map((u) => [u.id, u]));
    const parts: string[] = [];
    for (let u = byId.get(id); u; u = u.parent_id ? byId.get(u.parent_id) : undefined) parts.unshift(u.name);
    const kind = byId.get(id)?.kind;
    return `${parts.join(' › ')}${kind ? ` (${hi.admin.kinds[kind]})` : ''}`;
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!ready) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api.signup({
        role,
        display_name: name.trim(),
        phone: cleanPhone,
        pin,
        ...(role === 'teacher' ? { classroom_ids: [room], approver_id: approver } : { org_unit_id: unit }),
      });
      if (res.token && res.user) {
        // Admin accounts are active at once: sign straight in.
        onEnter({ token: res.token, user: res.user, classrooms: res.classrooms ?? [], pin_change_required: false });
        return;
      }
      setDone(approvers?.find((a) => a.id === approver)?.display_name ?? '');
    } catch (err) {
      setError(err instanceof ApiError && err.kind === 'http' && err.status >= 400 && err.status < 500 ? err.detail : err);
    } finally {
      setBusy(false);
    }
  };

  if (done !== null) {
    return (
      <div className="login-card">
        <div className="login-card-head">
          <h1>{hi.signupTitle}</h1>
        </div>
        <div className="alert alert-ok">
          <Icon name="checkCircle" size={18} className="alert-ico" />
          <span className="alert-text">{done ? hi.signupDoneTo(done) : hi.signupDone}</span>
        </div>
        <button className="btn btn-primary btn-block btn-lg" onClick={onBack}>
          {hi.backToLogin}
        </button>
      </div>
    );
  }

  return (
    <form onSubmit={submit} className="login-card">
      <div className="login-card-head">
        <h1>{hi.signupTitle}</h1>
        <p className="muted">{hi.signupSub}</p>
      </div>
      <fieldset className="field">
        <legend>{hi.signupRole}</legend>
        <div className="seg">
          {SIGNUP_ROLES.map((r) => (
            <button type="button" key={r} className={`seg-btn ${role === r ? 'seg-on' : ''}`} onClick={() => setRole(r)}>
              {hi.roles[r]}
            </button>
          ))}
        </div>
      </fieldset>
      <label className="field">
        <span>{hi.setupName}</span>
        <input value={name} onChange={(e) => setName(e.target.value)} required maxLength={120} autoComplete="name" />
      </label>
      <label className="field">
        <span>{hi.phone}</span>
        <input type="tel" inputMode="numeric" autoComplete="tel" required minLength={10} maxLength={20} placeholder="98XXXXXXXX" value={phone} onChange={(e) => setPhone(e.target.value)} />
      </label>
      {role === 'teacher' ? (
        <label className="field">
          <span>{hi.signupClass}</span>
          {opts && opts.classrooms.length === 0 ? (
            <small className="warn-text">{hi.signupNoClasses}</small>
          ) : (
            <select value={room} onChange={(e) => setRoom(e.target.value)} required>
              <option value="">{hi.admin.unitChoose}</option>
              {(opts?.classrooms ?? []).map((c) => (
                <option key={c.id} value={c.id}>
                  {c.school} — {c.name}
                </option>
              ))}
            </select>
          )}
        </label>
      ) : (
        <label className="field">
          <span>{hi.signupUnit}</span>
          <select value={unit} onChange={(e) => setUnit(e.target.value)} required>
            <option value="">{hi.admin.unitChoose}</option>
            {(opts?.units ?? [])
              .map((u) => ({ id: u.id, label: unitLabel(u.id) }))
              .sort((a, b) => a.label.localeCompare(b.label))
              .map((u) => (
                <option key={u.id} value={u.id}>
                  {u.label}
                </option>
              ))}
          </select>
        </label>
      )}
      {needsApprover ? (
      <label className="field">
        <span>{hi.signupApprover}</span>
        {approvers && approvers.length === 0 ? (
          <small className="warn-text">{hi.signupNoApprover}</small>
        ) : (
          <>
            <select value={approver} onChange={(e) => setApprover(e.target.value)} required disabled={!approvers}>
              <option value="">{approvers ? hi.admin.unitChoose : hi.signupApproverPick}</option>
              {(approvers ?? []).map((a) => (
                <option key={a.id} value={a.id}>
                  {a.display_name} — {a.unit ?? hi.approverTop}
                </option>
              ))}
            </select>
            <small className="field-hint">{hi.signupApproverHint}</small>
          </>
        )}
      </label>
      ) : (
        <div className="alert alert-ok">
          <Icon name="checkCircle" size={18} className="alert-ico" />
          <span className="alert-text">{hi.signupAdminNow}</span>
        </div>
      )}
      <label className="field">
        <span>{hi.pinNew}</span>
        <input type="password" inputMode="numeric" autoComplete="new-password" maxLength={PIN_MAX} value={pin} onChange={(e) => setPin(e.target.value.replace(/\D/g, ''))} />
      </label>
      {problem && pin.length >= 6 && <p className="warn-text">{problem}</p>}
      <label className="field">
        <span>{hi.pinAgain}</span>
        <input type="password" inputMode="numeric" autoComplete="new-password" maxLength={PIN_MAX} value={again} onChange={(e) => setAgain(e.target.value.replace(/\D/g, ''))} />
      </label>
      {mismatch && <p className="warn-text">{hi.pinMismatch}</p>}
      <ErrorBox error={error} />
      <button className="btn btn-primary btn-block btn-lg" disabled={busy || !ready}>
        {busy ? hi.loading : role === 'admin' ? hi.signupCreateAdmin : hi.signupSend}
      </button>
      <button type="button" className="btn btn-ghost btn-block" onClick={onBack}>
        {hi.haveAccount}
      </button>
    </form>
  );
}
