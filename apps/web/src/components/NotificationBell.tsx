import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { formatTime, hi } from '../i18n/hi';
import { useAuth } from '../lib/auth';
import { markAllRead, markRead, refreshNotifications, useNotifications } from '../lib/notifications';
import type { AppNotification } from '../lib/types';
import { Icon } from './icons';

const t = hi.notif;

/** App-bar bell: unread count, and a panel with the latest notifications (sign-up requests first to act on). */
export function NotificationBell() {
  const auth = useAuth();
  const list = useNotifications();
  const nav = useNavigate();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    void refreshNotifications();
    const onDown = (e: MouseEvent | TouchEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false);
    document.addEventListener('mousedown', onDown);
    document.addEventListener('touchstart', onDown);
    window.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('touchstart', onDown);
      window.removeEventListener('keydown', onKey);
    };
  }, [open]);

  if (!auth) return null;

  const go = (n: AppNotification) => {
    void markRead(n.id);
    setOpen(false);
    if (auth.user.role === 'admin' && (n.kind === 'signup_request' || n.kind === 'admin_joined')) nav('/admin/accounts');
  };

  return (
    <div className="bell" ref={ref}>
      <button
        className="icon-btn bell-btn"
        aria-label={list.unread ? `${t.open} (${t.unread(list.unread)})` : t.open}
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <Icon name="bell" size={22} />
        {list.unread > 0 && <span className="bell-badge">{list.unread > 99 ? '99+' : list.unread}</span>}
      </button>
      {open && (
        <div className="bell-panel" role="dialog" aria-label={t.title}>
          <div className="bell-head">
            <strong>{t.title}</strong>
            {list.unread > 0 && (
              <button className="btn btn-small btn-ghost" onClick={() => void markAllRead()}>
                {t.markAll}
              </button>
            )}
          </div>
          {list.items.length === 0 ? (
            <p className="bell-empty muted">{t.empty}</p>
          ) : (
            <ul className="bell-list">
              {list.items.map((n) => (
                <li key={n.id}>
                  <button className={`bell-item ${n.read ? '' : 'bell-item-new'}`} onClick={() => go(n)}>
                    <span className={`bell-ico bell-ico-${n.kind}`} aria-hidden>
                      <Icon name={n.kind === 'signup_request' ? 'users' : n.kind === 'account_approved' ? 'checkCircle' : 'shield'} size={16} />
                    </span>
                    <span className="bell-text">
                      <span className="bell-title">{n.title}</span>
                      {n.body && <span className="bell-body">{n.body}</span>}
                      <span className="bell-time">{formatTime(n.created_at)}</span>
                    </span>
                    {!n.read && <span className="bell-dot" aria-label="new" />}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
