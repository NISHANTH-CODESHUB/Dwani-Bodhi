/** Teacher-side design system: app shell (sidebar / drawer / tab bar), avatars, stat tiles, rings, level bars. */
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { NavLink, useLocation, useNavigate } from 'react-router-dom';
import { hi } from '../i18n/hi';
import { useAuth, useClassroom } from '../lib/auth';
import { avatarColor, avatarText, BAND_LABEL, skillBand, type SkillBand } from '../lib/childUi';
import { KV_KEYS, kvGet } from '../lib/db';
import { runSync, useSyncStatus } from '../lib/sync';
import { LogoutButton } from '../teacher/LogoutButton';
import { useLive } from './common';
import { Icon, type IconName } from './icons';

/* ------------------------------------------------------------------------------- sync pill */
export function SyncPill() {
  const st = useSyncStatus();
  const [state, setState] = useState<'idle' | 'ok' | 'fail'>('idle');
  const run = async () => {
    const ok = await runSync({ manual: true });
    setState(ok ? 'ok' : 'fail');
    window.setTimeout(() => setState('idle'), 3000);
  };
  const tone = !st.online ? 'off' : st.running ? 'busy' : state === 'fail' ? 'fail' : st.queued > 0 ? 'pending' : 'on';
  const label = st.running
    ? hi.syncing
    : state === 'ok'
      ? hi.syncOkShort
      : state === 'fail'
        ? hi.syncFailShort
        : !st.online
          ? hi.offline
          : st.queued > 0
            ? hi.queued(st.queued)
            : hi.synced;
  return (
    <button className={`sync-pill sync-${tone}`} onClick={run} disabled={st.running} aria-live="polite" title={hi.syncNow}>
      <span className="sync-dot" aria-hidden />
      <span className="sync-label">{label}</span>
      <Icon name="sync" size={16} className={`sync-icon ${st.running ? 'spin' : ''}`} />
    </button>
  );
}

/* ------------------------------------------------------------------------------ navigation */
interface NavItem {
  to: string;
  icon: IconName;
  label: string;
  end?: boolean;
  badge?: number;
}

function useNavSections(): { title: string; items: NavItem[] }[] {
  const room = useClassroom();
  const cid = room?.id ?? '';
  const unsure = useLive(() => (cid ? kvGet<number>(KV_KEYS.unsureCount(cid)) : Promise.resolve(undefined)), [cid], undefined);
  const support = {
    title: hi.navSupport,
    items: [
      { to: '/help', icon: 'help' as const, label: hi.navHelp },
      { to: '/pin', icon: 'lock' as const, label: hi.navPin },
    ],
  };
  if (!room) return [support];
  return [
    {
      title: hi.navDaily,
      items: [
        { to: '/', icon: 'home', label: hi.tabHome, end: true },
        { to: '/slate', icon: 'camera', label: hi.slateScan },
        { to: '/unsure', icon: 'review', label: hi.tabReview, badge: unsure ?? 0 },
      ],
    },
    {
      title: hi.navPlan,
      items: [
        { to: '/card', icon: 'clipboard', label: hi.actionCard },
        { to: '/activity', icon: 'activity', label: hi.navActivity },
        { to: '/roster', icon: 'users', label: hi.tabClass },
        { to: '/idcards', icon: 'idcard', label: hi.idCards },
      ],
    },
    support,
  ];
}

function Badge({ n }: { n?: number }) {
  return n ? <span className="nav-badge">{n > 99 ? '99+' : n}</span> : null;
}

/** Sidebar on wide screens; the same panel slides in as a drawer on phones. */
function SideNav({ open, onClose }: { open: boolean; onClose: () => void }) {
  const auth = useAuth();
  const room = useClassroom();
  const nav = useNavigate();
  const sections = useNavSections();
  const name = auth?.user.display_name ?? '';
  return (
    <>
      <div className={`scrim ${open ? 'scrim-on' : ''}`} onClick={onClose} aria-hidden />
      <aside className={`sidenav ${open ? 'sidenav-open' : ''}`} aria-label={hi.mainNav}>
        <div className="sidenav-brand">
          <img src="/icons/icon-192.png" alt="" width={36} height={36} className="brand-mark" />
          <div className="brand-text">
            <span className="brand-name">{hi.appName}</span>
            <span className="brand-sub">{hi.appSub}</span>
          </div>
          <button className="icon-btn sidenav-close" onClick={onClose} aria-label={hi.closeMenu}>
            <Icon name="back" />
          </button>
        </div>

        {auth && (
          <button className="class-switch" onClick={() => nav('/classes')} title={hi.changeClass}>
            <Icon name="school" size={18} />
            <span className="class-switch-text">
              <span className="class-switch-label">{room ? hi.currentClass : hi.chooseClass}</span>
              <span className="class-switch-name">{room?.name ?? '—'}</span>
            </span>
            <Icon name="chevronDown" size={16} />
          </button>
        )}

        <nav className="sidenav-nav">
          {sections.map((s) => (
            <div key={s.title} className="nav-section">
              <div className="nav-section-title">{s.title}</div>
              {s.items.map((it) => (
                <NavLink key={it.to} to={it.to} end={it.end} className={({ isActive }) => `nav-item ${isActive ? 'nav-item-active' : ''}`}>
                  <Icon name={it.icon} />
                  <span className="nav-item-label">{it.label}</span>
                  <Badge n={it.badge} />
                </NavLink>
              ))}
            </div>
          ))}
        </nav>

        <div className="sidenav-foot">
          <SyncPill />
          {auth && (
            <div className="user-row">
              <span className="user-avatar" aria-hidden>
                {avatarText(name, undefined)}
              </span>
              <span className="user-text">
                <span className="user-name">{name}</span>
                <span className="user-role">{hi.roleTeacher}</span>
              </span>
              <LogoutButton compact />
            </div>
          )}
        </div>
      </aside>
    </>
  );
}

/** Phone bottom navigation: the five daily destinations. */
function TabBar() {
  const room = useClassroom();
  const auth = useAuth();
  const cid = room?.id ?? '';
  const unsure = useLive(() => (cid ? kvGet<number>(KV_KEYS.unsureCount(cid)) : Promise.resolve(undefined)), [cid], undefined);
  if (!room || !auth) return null;
  const tabs: NavItem[] = [
    { to: '/', icon: 'home', label: hi.tabHome, end: true },
    { to: '/roster', icon: 'users', label: hi.tabClass },
    { to: '/slate', icon: 'camera', label: hi.tabSlate },
    { to: '/card', icon: 'clipboard', label: hi.tabCard },
    { to: '/unsure', icon: 'review', label: hi.tabReview, badge: unsure ?? 0 },
  ];
  return (
    <nav className="tabbar" aria-label={hi.mainNav}>
      {tabs.map((t) => (
        <NavLink key={t.to} to={t.to} end={t.end} className={({ isActive }) => `tab ${isActive ? 'tab-active' : ''}`}>
          <span className="tab-icon">
            <Icon name={t.icon} size={22} />
            <Badge n={t.badge} />
          </span>
          <span className="tab-label">{t.label}</span>
        </NavLink>
      ))}
    </nav>
  );
}

/**
 * Every signed-in screen: sidebar/drawer, sticky header (menu or back, title, actions), content, tab bar.
 * `back` shows a back arrow instead of the menu button on phones (sub-screens).
 */
export function AppShell({
  title,
  subtitle,
  actions,
  back,
  narrow,
  children,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  back?: string | true;
  /** Reading-width column (long text, forms, queues) instead of the full dashboard width. */
  narrow?: boolean;
  children: ReactNode;
}) {
  const nav = useNavigate();
  const loc = useLocation();
  const room = useClassroom();
  const auth = useAuth();
  const [drawer, setDrawer] = useState(false);
  useEffect(() => setDrawer(false), [loc.pathname]);
  useEffect(() => {
    if (!drawer) return;
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setDrawer(false);
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [drawer]);
  const hasTabs = !!room && !!auth;

  return (
    <div className={`shell ${hasTabs ? 'shell-tabs' : ''}`}>
      <SideNav open={drawer} onClose={() => setDrawer(false)} />
      <div className="shell-main">
        <header className="appbar">
          {back ? (
            <button className="icon-btn" aria-label={hi.back} onClick={() => (back === true ? nav(-1) : nav(back))}>
              <Icon name="back" size={22} />
            </button>
          ) : (
            <button className="icon-btn appbar-menu" aria-label={hi.menu} onClick={() => setDrawer(true)}>
              <Icon name="menu" size={22} />
            </button>
          )}
          <div className="appbar-titles">
            <h1 className="appbar-title">{title}</h1>
            {subtitle && <div className="appbar-sub">{subtitle}</div>}
          </div>
          <div className="appbar-actions">
            {actions}
            <span className="appbar-sync">
              <SyncPill />
            </span>
          </div>
        </header>
        <main className={`shell-content ${narrow ? 'shell-content-narrow' : ''}`}>{children}</main>
      </div>
      <TabBar />
    </div>
  );
}

/** Sub-screen alias: same shell with a back arrow. */
export function Page({
  title,
  subtitle,
  back,
  right,
  narrow,
  children,
}: {
  title: string;
  subtitle?: ReactNode;
  back?: string | true;
  right?: ReactNode;
  narrow?: boolean;
  children: ReactNode;
}) {
  return (
    <AppShell title={title} subtitle={subtitle} back={back} actions={right} narrow={narrow}>
      {children}
    </AppShell>
  );
}

/** Panel = titled white surface (the basic layout block). */
export function Panel({ title, icon, hint, action, className, children }: { title?: ReactNode; icon?: IconName; hint?: ReactNode; action?: ReactNode; className?: string; children: ReactNode }) {
  return (
    <section className={`panel ${className ?? ''}`}>
      {(title || action) && (
        <div className="panel-head">
          <div className="panel-titles">
            {title && (
              <h2>
                {icon && <Icon name={icon} size={18} className="panel-ico" />}
                {title}
              </h2>
            )}
            {hint && <span className="panel-hint">{hint}</span>}
          </div>
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

/* ---------------------------------------------------------------------------------- avatar */
export function Avatar({ id, name, slot, size = 44 }: { id: string; name: string; slot?: number; size?: number }) {
  const text = avatarText(name, slot);
  const noName = !name.trim();
  return (
    <span
      className={`avatar ${noName ? 'avatar-noname' : ''}`}
      style={{ width: size, height: size, fontSize: size * (noName ? 0.34 : 0.42), background: noName ? undefined : avatarColor(id) }}
      aria-hidden
    >
      {noName ? `#${text}` : text}
    </span>
  );
}

/* ------------------------------------------------------------------------------- stat tile */
export function StatTile({ icon, value, label, tone = 'brand', onClick }: { icon: IconName; value: ReactNode; label: string; tone?: 'brand' | 'warn' | 'ok' | 'violet'; onClick?: () => void }) {
  const Comp = onClick ? 'button' : 'div';
  return (
    <Comp className={`stat stat-${tone}`} onClick={onClick}>
      <span className="stat-top">
        <span className="stat-icon" aria-hidden>
          <Icon name={icon} size={18} />
        </span>
        {onClick && <Icon name="chevronRight" size={16} className="stat-go" />}
      </span>
      <span className="stat-value">{value}</span>
      <span className="stat-label">{label}</span>
    </Comp>
  );
}

/* --------------------------------------------------------------------------- progress ring */
export function ProgressRing({ done, total, size = 56 }: { done: number; total: number; size?: number }) {
  const r = (size - 8) / 2;
  const c = 2 * Math.PI * r;
  const frac = total ? Math.min(1, done / total) : 0;
  return (
    <svg className="ring" width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`${done}/${total}`}>
      <circle cx={size / 2} cy={size / 2} r={r} className="ring-track" />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        className="ring-fill"
        strokeDasharray={`${c * frac} ${c}`}
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
      />
      <text x="50%" y="50%" dominantBaseline="central" textAnchor="middle" className="ring-text">
        {done}/{total}
      </text>
    </svg>
  );
}

/* ------------------------------------------------------------------- level distribution */
/** Ordinal levels → one hue, light (beginner) to dark (top rung). Text flips to white on the dark steps. */
const RUNG_TONES = ['#dbe4f5', '#b5c8f0', '#86a5e6', '#5b82d9', '#3560c4', '#1e3f94', '#152d6b'];
const DARK_FROM = 3;

export function LevelBars({ title, rows }: { title: string; rows: { id: string; name_hi: string; n: number; pct: number }[] }) {
  const total = rows.reduce((s, r) => s + r.n, 0);
  const tone = (i: number) => RUNG_TONES[Math.min(i, RUNG_TONES.length - 1)];
  return (
    <div className="levelbars">
      <div className="levelbars-head">
        <strong>{title}</strong>
        <span className="muted small">{hi.childrenN(total)}</span>
      </div>
      <div className="levelbars-track" role="img" aria-label={rows.map((r) => `${r.name_hi} ${r.n}`).join(', ')}>
        {total === 0 && <span className="levelbars-empty" />}
        {rows.map((r, i) =>
          r.n ? (
            <span
              key={r.id}
              className={`levelbars-seg ${i >= DARK_FROM ? 'levelbars-seg-dark' : ''}`}
              style={{ flexGrow: r.n, background: tone(i) }}
              title={`${r.name_hi}: ${r.n} (${r.pct}%)`}
            >
              {r.pct >= 12 ? r.n : ''}
            </span>
          ) : null,
        )}
      </div>
      <div className="levelbars-legend">
        {rows.map((r, i) => (
          <span key={r.id} className={`legend ${r.n ? '' : 'legend-empty'}`}>
            <i style={{ background: tone(i) }} />
            {r.name_hi} <b>{r.n}</b>
          </span>
        ))}
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------------------- skill band */
export function BandChip({ p, checking }: { p: number | null; checking?: boolean }) {
  const band: SkillBand = skillBand(p);
  return (
    <span className={`band band-${band}`}>
      <span className="band-dot" aria-hidden />
      {BAND_LABEL[band]}
      {checking && <span className="band-check">· {hi.checking}</span>}
    </span>
  );
}

/** Ladder stepper: rungs left→right, current highlighted, next marked when uncertain. */
export function Ladder({ rungs, current, certain }: { rungs: { id: string; name_hi: string }[]; current: number; certain: boolean }) {
  const all = [{ id: 'beginner', name_hi: 'Beginner' }, ...rungs];
  const pos = current + 1; // -1 (beginner) → 0
  const ref = useRef<HTMLOListElement>(null);
  const [edges, setEdges] = useState({ left: false, right: false });
  // On narrow phones a long ladder scrolls: centre the child's rung and fade the edges that hide more rungs.
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const sync = () =>
      setEdges({ left: el.scrollLeft > 4, right: el.scrollLeft + el.clientWidth < el.scrollWidth - 4 });
    const cur = el.children[pos] as HTMLElement | undefined;
    if (cur && el.scrollWidth > el.clientWidth) el.scrollLeft = cur.offsetLeft - (el.clientWidth - cur.offsetWidth) / 2;
    sync();
    el.addEventListener('scroll', sync, { passive: true });
    return () => el.removeEventListener('scroll', sync);
  }, [pos, rungs.length]);
  return (
    <ol ref={ref} className={`ladder ${edges.left ? 'ladder-more-left' : ''} ${edges.right ? 'ladder-more-right' : ''}`}>
      {all.map((r, i) => (
        <li key={r.id} aria-current={i === pos ? 'step' : undefined} className={`ladder-step ${i < pos ? 'ladder-done' : ''} ${i === pos ? 'ladder-current' : ''} ${i === pos && !certain ? 'ladder-unsure' : ''}`}>
          <span className="ladder-dot" aria-hidden>
            {i < pos ? <Icon name="check" size={14} /> : i === pos ? <span className="ladder-pip" /> : null}
          </span>
          <span className="ladder-name">{r.name_hi}</span>
        </li>
      ))}
    </ol>
  );
}

export function EmptyState({ icon, title, children }: { icon: IconName; title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <div className="empty-icon" aria-hidden>
        <Icon name={icon} size={28} />
      </div>
      <div className="empty-title">{title}</div>
      {children && <div className="empty-body">{children}</div>}
    </div>
  );
}
