import { useState, type FormEvent } from 'react';
import { hi } from '../i18n/hi';
import { ApiError, api } from '../lib/api';
import { pinProblem, PIN_MAX } from '../lib/pin';
import type { LoginResponse } from '../lib/types';
import { ErrorBox } from './common';
import { Icon } from './icons';

/**
 * Sets a new PIN. Used right after login when the old PIN is weak (`token` = the short-lived
 * pin-change token, `currentPin` already known) and from the "change PIN" page.
 */
export function PinChangeForm({
  token,
  phone,
  currentPin,
  onDone,
}: {
  token?: string;
  phone?: string;
  currentPin?: string;
  onDone: (res: LoginResponse) => void;
}) {
  const [current, setCurrent] = useState(currentPin ?? '');
  const [next, setNext] = useState('');
  const [again, setAgain] = useState('');
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const problem = next ? pinProblem(next, phone) : null;
  const mismatch = again.length > 0 && again !== next;
  const sameAsOld = next.length > 0 && next === current;
  const ready = !!current && !!next && !problem && !mismatch && !sameAsOld && again === next;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!ready) return;
    setBusy(true);
    setError(null);
    try {
      onDone(await api.changePin({ current_pin: current, new_pin: next, phone }, token));
    } catch (err) {
      // 400/422 carry a Hindi reason from the server (wrong current PIN, weak new PIN).
      setError(err instanceof ApiError && (err.status === 400 || err.status === 422) ? err.detail : err);
    } finally {
      setBusy(false);
    }
  };

  const pinInput = (value: string, set: (v: string) => void, autoComplete: string, label: string) => (
    <label className="field">
      <span>{label}</span>
      <input
        type={show ? 'text' : 'password'}
        inputMode="numeric"
        autoComplete={autoComplete}
        maxLength={PIN_MAX}
        value={value}
        onChange={(e) => set(e.target.value.replace(/\D/g, ''))}
      />
    </label>
  );

  return (
    <form onSubmit={submit} className="pin-form">
      {currentPin === undefined && pinInput(current, setCurrent, 'current-password', hi.pinCurrent)}
      {pinInput(next, setNext, 'new-password', hi.pinNew)}
      <ul className="pin-rules" aria-live="polite">
        <li className={next.length >= 6 ? 'ok' : ''}>
          <Icon name={next.length >= 6 ? 'checkCircle' : 'info'} size={15} />
          {hi.pinRuleLength}
        </li>
        <li className={next && !problem ? 'ok' : ''}>
          <Icon name={next && !problem ? 'checkCircle' : 'info'} size={15} />
          {hi.pinRuleGuess}
        </li>
      </ul>
      {problem && next.length >= 6 && <p className="warn-text">{problem}</p>}
      {sameAsOld && <p className="warn-text">{hi.pinSameAsOld}</p>}
      {pinInput(again, setAgain, 'new-password', hi.pinAgain)}
      {mismatch && <p className="warn-text">{hi.pinMismatch}</p>}
      <label className="pin-show">
        <input type="checkbox" checked={show} onChange={(e) => setShow(e.target.checked)} />
        {hi.showPin}
      </label>
      <ErrorBox error={error} />
      <button className="btn btn-primary btn-block btn-lg" disabled={busy || !ready}>
        {busy ? hi.loading : hi.pinSave}
      </button>
      <p className="login-privacy">
        <Icon name="shield" size={16} />
        {hi.pinPrivacy}
      </p>
    </form>
  );
}
