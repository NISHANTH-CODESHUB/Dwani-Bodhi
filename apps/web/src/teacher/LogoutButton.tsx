import { useNavigate } from 'react-router-dom';
import { Icon } from '../components/icons';
import { hi } from '../i18n/hi';
import { logout } from '../lib/auth';
import { refreshQueueCount } from '../lib/sync';

export function LogoutButton({ compact = false }: { compact?: boolean }) {
  const nav = useNavigate();
  const onClick = async () => {
    const pending = await refreshQueueCount();
    const msg = pending > 0 ? hi.logoutPending(pending) : hi.logoutConfirm;
    if (!window.confirm(msg)) return;
    logout();
    nav('/login', { replace: true });
  };
  if (compact) {
    return (
      <button className="icon-btn" onClick={onClick} aria-label={hi.logout} title={hi.logout}>
        <Icon name="logout" />
      </button>
    );
  }
  return (
    <button className="btn btn-small btn-ghost" onClick={onClick}>
      <Icon name="logout" size={16} />
      {hi.logout}
    </button>
  );
}
