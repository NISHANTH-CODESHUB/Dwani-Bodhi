import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { DailyChart, Kpi, RegisterNo, relDay } from '../components/activity';
import { ErrorBox, Spinner } from '../components/common';
import { Icon } from '../components/icons';
import { AppShell, LevelBars, Panel } from '../components/ui';
import { formatTime, hi } from '../i18n/hi';
import { ApiError, api } from '../lib/api';
import { useAuth } from '../lib/auth';
import { refreshNotifications } from '../lib/notifications';
import type { AdminDashboard, AdminUser } from '../lib/types';

const t = hi.dash;
const a = hi.act;

function levelRows(rows: { level: string; n: number }[]) {
  const total = rows.reduce((s, r) => s + r.n, 0);
  return rows.map((r, i) => ({ id: `${i}-${r.level}`, name_hi: r.level, n: r.n, pct: total ? Math.round((100 * r.n) / total) : 0 }));
}

/** Sign-up requests the admin can act on right here (the same list lives under Accounts & hierarchy). */
function PendingRequests({ users, onChanged }: { users: AdminUser[]; onChanged: () => void }) {
  const me = useAuth()?.user.id;
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const act = async (u: AdminUser, approve: boolean) => {
    if (!approve && !window.confirm(hi.admin.rejectConfirm(u.display_name))) return;
    setBusy(u.id);
    setError(null);
    try {
      if (approve) await api.approveUser(u.id);
      else await api.rejectUser(u.id);
      onChanged();
      void refreshNotifications();
    } catch (e) {
      setError(e instanceof ApiError && e.kind === 'http' && e.status < 500 ? e.detail : e);
    } finally {
      setBusy(null);
    }
  };
  return (
    <Panel
      title={users.length ? `${t.pendingTitle} (${users.length})` : t.pendingTitle}
      icon="bell"
      className={users.length ? 'panel-attention' : ''}
      action={
        <Link to="/admin/accounts" className="btn btn-small btn-ghost">
          {t.pendingOpen}
        </Link>
      }
    >
      {users.length === 0 ? (
        <p className="muted">{t.pendingNone}</p>
      ) : (
        <ul className="req-list">
          {users.map((u) => (
            <li key={u.id} className="req">
              <span className="req-text">
                <strong>{u.display_name}</strong> <span className="chip">{hi.roles[u.role]}</span>
                <span className="muted small">
                  {u.classrooms.map((c) => `${c.school} — ${c.name}`).join(', ')}
                  {u.created_at && ` · ${formatTime(u.created_at)}`}
                </span>
                {u.approver && (
                  <span className="small">
                    <strong>{u.approver.id === me ? hi.admin.sentToYou : hi.admin.sentTo(u.approver.display_name)}</strong>
                  </span>
                )}
              </span>
              {u.can_manage && (
                <span className="req-actions">
                  <button className="btn btn-small btn-primary" disabled={busy === u.id} onClick={() => void act(u, true)}>
                    <Icon name="check" size={16} />
                    {hi.admin.approve}
                  </button>
                  <button className="btn btn-small btn-danger-ghost" disabled={busy === u.id} onClick={() => void act(u, false)}>
                    {hi.admin.reject}
                  </button>
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
      <ErrorBox error={error} />
    </Panel>
  );
}

export default function AdminDashboardPage() {
  const auth = useAuth();
  const [data, setData] = useState<AdminDashboard | null>(null);
  const [pending, setPending] = useState<AdminUser[]>([]);
  const [error, setError] = useState<unknown>(null);

  const load = async () => {
    setError(null);
    try {
      const [d, users] = await Promise.all([api.adminDashboard(), api.users()]);
      setData(d);
      setPending(users.filter((u) => u.pending));
    } catch (e) {
      setError(e);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  return (
    <AppShell title={t.title} subtitle={auth?.user.org_unit_id ? t.scopeUnit : hi.admin.scopeAll}>
      <ErrorBox error={error} onRetry={load} />
      {!data && !error && <Spinner />}
      {data && (
        <>
          <div className="kpis kpis-6">
            <Kpi label={t.schools} value={data.totals.schools} sub={`${data.totals.classrooms} ${t.classrooms.toLowerCase()}`} />
            <Kpi
              label={t.teachers}
              value={data.totals.teachers}
              sub={data.totals.teachers_pending ? t.pendingBadge(data.totals.teachers_pending) : undefined}
              tone={data.totals.teachers_pending ? 'warn' : undefined}
            />
            <Kpi label={t.students} value={data.totals.students} sub={t.assessedN(data.totals.students_assessed)} />
            <Kpi label={t.sessions7d} value={data.totals.sessions_7d} />
            <Kpi label={t.sessions30d} value={data.totals.sessions_30d} />
          </div>

          <div className="dash-grid dash-grid-2">
            <div className="dash-col">
              <PendingRequests users={pending} onChanged={load} />
              <DailyChart data={data.daily} title={a.daily14} />
              <Panel title={t.levelsTitle} icon="chart">
                <LevelBars title={a.literacy} rows={levelRows(data.levels.literacy)} />
                <LevelBars title={a.numeracy} rows={levelRows(data.levels.numeracy)} />
              </Panel>
            </div>
            <div className="dash-col">
              <Panel
                title={t.teacherActivity}
                icon="school"
                action={
                  <Link to="/admin/teachers" className="btn btn-small btn-ghost">
                    {t.allTeachers}
                  </Link>
                }
              >
                {data.teachers.length === 0 ? (
                  <p className="muted">{t.teacherEmpty}</p>
                ) : (
                  <ul className="mini-list">
                    {data.teachers.slice(0, 8).map((tr) => (
                      <li key={tr.id} className="mini">
                        <span className="mini-main">
                          <strong>{tr.display_name}</strong>
                          {tr.pending && <span className="tag tag-warn">{hi.admin.pending}</span>}
                          {!tr.active && !tr.pending && <span className="tag tag-warn">{t.inactive}</span>}
                          <span className="muted small">
                            {tr.classes.map((c) => c.name).join(', ') || hi.admin.noClassLinked} · {a.studentsN(tr.students)}
                          </span>
                        </span>
                        <span className="mini-side">
                          <b>{tr.sessions_7d}</b>
                          <span className="muted small">{a.sessions7d.toLowerCase()}</span>
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </Panel>
              <Panel
                title={t.recent}
                icon="clock"
                action={
                  <Link to="/admin/students" className="btn btn-small btn-ghost">
                    {t.allStudents}
                  </Link>
                }
              >
                {data.recent.length === 0 ? (
                  <p className="muted">{t.recentEmpty}</p>
                ) : (
                  <ul className="mini-list">
                    {data.recent.map((r) => (
                      <li key={r.session_id}>
                        <Link to={`/admin/students/${r.student_id}`} className="mini mini-link">
                          <span className="mini-main">
                            <RegisterNo value={r.register_no} />
                            <span className="muted small">
                              {r.school} — {r.classroom}
                            </span>
                          </span>
                          <span className="mini-side">
                            <span className="small">{relDay(r.at)}</span>
                            <span className="muted small">
                              {r.answers} {a.answers.toLowerCase()}
                            </span>
                          </span>
                        </Link>
                      </li>
                    ))}
                  </ul>
                )}
              </Panel>
              <p className="muted small with-ico">
                <Icon name="shield" size={14} /> {t.namesNote}
              </p>
            </div>
          </div>
        </>
      )}
    </AppShell>
  );
}
