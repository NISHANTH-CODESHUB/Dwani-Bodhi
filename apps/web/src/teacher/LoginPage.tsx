import { useState, type FormEvent } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import { ClassFields, classValid, EMPTY_CLASS, type ClassValues } from '../components/ClassFields';
import { ErrorBox } from '../components/common';
import { PinChangeForm } from '../components/PinChangeForm';
import { Icon } from '../components/icons';
import { hi } from '../i18n/hi';
import { ApiError, api } from '../lib/api';
import { getClassroomId, setAuth, useAuth } from '../lib/auth';
import { NO_LOGIN } from '../lib/config';
import { runSync } from '../lib/sync';
import { pinProblem, PIN_MAX } from '../lib/pin';
import type { LoginResponse } from '../lib/types';

/** Keep digits and a leading + only (pasted numbers often carry spaces, dashes or brackets). */
const normalizePhone = (raw: string) => raw.trim().replace(/(?!^\+)[^\d]/g, '');

/** Login-screen wording: the generic texts ("work offline", "session expired") make no sense before sign-in. */
function loginError(err: unknown): unknown {
  if (!(err instanceof ApiError)) return err;
  if (err.kind !== 'http') return hi.loginOffline;
  if (err.status === 401) return hi.loginWrong;
  // 429 = too many wrong PINs: the server text says how long to wait.
  if (err.status === 429) return err.detail;
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

  const [signup, setSignup] = useState(false);

  if (auth) return <Navigate to="/" replace />;

  const enter = (res: LoginResponse) => {
    setAuth({ token: res.token, user: res.user, classrooms: res.classrooms });
    void runSync({ manual: true });
    nav(getClassroomId() ? '/' : '/classes', { replace: true });
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

  const open = async () => {
    setBusy(true);
    setError(null);
    try {
      enter(await api.openSession());
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
            <button className="btn btn-primary btn-block btn-lg" disabled={busy} onClick={() => void open()}>
              {hi.openAsTeacher}
            </button>
            <ErrorBox error={error} />
          </div>
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
          <p className="muted small login-forgot">{hi.pinForgotten}</p>
        </form>
        )}
      </main>
    </div>
  );
}

/** "Create account": a teacher account with its school and first class, active at once (no approval). */
function SignupForm({ onBack, onEnter }: { onBack: () => void; onEnter: (res: LoginResponse) => void }) {
  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  const [pin, setPin] = useState('');
  const [again, setAgain] = useState('');
  const [cls, setCls] = useState<ClassValues>(EMPTY_CLASS);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const cleanPhone = normalizePhone(phone).replace(/\D/g, '');
  const problem = pin ? pinProblem(pin, cleanPhone) : null;
  const mismatch = again.length > 0 && again !== pin;
  const ready = !!name.trim() && cleanPhone.length >= 10 && !!pin && !problem && again === pin && classValid(cls);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!ready) return;
    setBusy(true);
    setError(null);
    try {
      onEnter(
        await api.signup({
          display_name: name.trim(),
          phone: cleanPhone,
          pin,
          school_name: cls.school_name.trim(),
          class_name: cls.class_name.trim(),
          grades: cls.grades,
          region_profile: cls.region_profile,
        }),
      );
    } catch (err) {
      setError(err instanceof ApiError && err.kind === 'http' && err.status >= 400 && err.status < 500 ? err.detail : loginError(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="login-card">
      <div className="login-card-head">
        <h1>{hi.signupTitle}</h1>
        <p className="muted">{hi.signupSub}</p>
      </div>
      <label className="field">
        <span>{hi.signupName}</span>
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
      <ClassFields value={cls} onChange={setCls} />
      <ErrorBox error={error} />
      <button className="btn btn-primary btn-block btn-lg" disabled={busy || !ready}>
        {busy ? hi.loading : hi.signupCreate}
      </button>
      <button type="button" className="btn btn-ghost btn-block" onClick={onBack}>
        {hi.haveAccount}
      </button>
    </form>
  );
}
