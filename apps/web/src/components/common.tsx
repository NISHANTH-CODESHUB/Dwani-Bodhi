import { liveQuery } from 'dexie';
import { useEffect, useState, type DependencyList, type ReactNode } from 'react';
import { errorText, hi } from '../i18n/hi';
import { Icon } from './icons';

/** Re-renders whenever the IndexedDB data read by `query` changes (Dexie liveQuery). */
export function useLive<T>(query: () => Promise<T>, deps: DependencyList, initial: T): T {
  const [value, setValue] = useState<T>(initial);
  useEffect(() => {
    const sub = liveQuery(query).subscribe({ next: setValue, error: (e) => console.error(e) });
    return () => sub.unsubscribe();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return value;
}

export function ErrorBox({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  if (!error) return null;
  return (
    <div className="alert alert-error" role="alert">
      <Icon name="alert" size={18} className="alert-ico" />
      <span className="alert-text">{typeof error === 'string' ? error : errorText(error)}</span>
      {onRetry && (
        <button className="btn btn-small btn-outline" onClick={onRetry}>
          {hi.retry}
        </button>
      )}
    </div>
  );
}

export function Notice({ children, tone = 'info' }: { children: ReactNode; tone?: 'info' | 'warn' | 'ok' }) {
  return (
    <div className={`alert alert-${tone}`}>
      <Icon name={tone === 'warn' ? 'alert' : tone === 'ok' ? 'checkCircle' : 'info'} size={18} className="alert-ico" />
      <span className="alert-text">{children}</span>
    </div>
  );
}

export function Spinner({ label = hi.loading }: { label?: string }) {
  return (
    <div className="spinner" role="status">
      <span className="spinner-dot" aria-hidden />
      {label}
    </div>
  );
}
