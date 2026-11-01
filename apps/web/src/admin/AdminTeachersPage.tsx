import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Kpi, relDay } from '../components/activity';
import { ErrorBox, Spinner } from '../components/common';
import { Icon } from '../components/icons';
import { AppShell, EmptyState, Panel } from '../components/ui';
import { hi } from '../i18n/hi';
import { api } from '../lib/api';
import type { TeacherRow } from '../lib/types';

const t = hi.dash;
const a = hi.act;

/** Admin: each teacher's classes, students and recent work (most active first). */
export default function AdminTeachersPage() {
  const [rows, setRows] = useState<TeacherRow[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [q, setQ] = useState('');

  const load = async () => {
    setError(null);
    try {
      setRows(await api.adminTeachers());
    } catch (e) {
      setError(e);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const shown = useMemo(() => {
    const s = q.trim().toLowerCase();
    return [...(rows ?? [])]
      .filter((r) => !s || r.display_name.toLowerCase().includes(s) || r.classes.some((c) => `${c.school} ${c.name}`.toLowerCase().includes(s)))
      .sort((x, y) => Number(y.pending) - Number(x.pending) || y.sessions_7d - x.sessions_7d || x.display_name.localeCompare(y.display_name));
  }, [rows, q]);

  const active = (rows ?? []).filter((r) => r.active && !r.pending);
  const working = active.filter((r) => r.sessions_7d > 0).length;

  return (
    <AppShell
      title={t.teachersTitle}
      subtitle={t.teachersSub}
      actions={
        <Link to="/admin/accounts" className="btn btn-small btn-outline appbar-btn">
          <Icon name="shield" size={18} />
          <span className="appbar-btn-label">{hi.navAdmin}</span>
        </Link>
      }
    >
      <ErrorBox error={error} onRetry={load} />
      {!rows && !error && <Spinner />}
      {rows && (
        <>
          <div className="kpis">
            <Kpi label={t.teachers} value={active.length} />
            <Kpi label={hi.classAct.active7d} value={working} />
            <Kpi label={t.students} value={active.reduce((n, r) => n + r.students, 0)} />
            <Kpi label={hi.admin.pending} value={rows.filter((r) => r.pending).length} tone={rows.some((r) => r.pending) ? 'warn' : undefined} />
          </div>
          <div className="toolbar">
            <label className="search-wrap">
              <Icon name="search" size={18} className="search-ico" />
              <input className="search" type="search" placeholder={t.searchTeacher} value={q} onChange={(e) => setQ(e.target.value)} aria-label={t.searchTeacher} />
            </label>
          </div>
          <Panel title={t.teacherActivity} icon="school">
            {shown.length === 0 ? (
              <EmptyState icon="school" title={t.teacherEmpty} />
            ) : (
              <div className="table-wrap">
                <table className="dtable dtable-stack">
                  <thead>
                    <tr>
                      <th>{a.teacher}</th>
                      <th>{t.classes}</th>
                      <th className="num">{t.students}</th>
                      <th className="num">{a.sessions7d}</th>
                      <th className="num">{t.sessions30d}</th>
                      <th>{a.lastActive}</th>
                      <th>{t.lastLogin}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {shown.map((r) => (
                      <tr key={r.id} className={r.active || r.pending ? '' : 'dtable-off'}>
                        <td>
                          <span className="dtable-name">{r.display_name}</span>
                          {r.pending && <span className="tag tag-warn">{hi.admin.pending}</span>}
                          {!r.active && !r.pending && <span className="tag tag-warn">{t.inactive}</span>}
                        </td>
                        <td data-label={t.classes}>
                          {r.classes.length === 0 ? (
                            <span className="muted">{hi.admin.noClassLinked}</span>
                          ) : (
                            r.classes.map((c) => (
                              <Link key={c.id} to={`/admin/students?class=${c.id}`} className="dtable-sub">
                                {c.school} — {c.name}
                              </Link>
                            ))
                          )}
                        </td>
                        <td data-label={t.students} className="num">{r.students}</td>
                        <td data-label={a.sessions7d} className="num">
                          <b>{r.sessions_7d}</b>
                        </td>
                        <td data-label={t.sessions30d} className="num">{r.sessions_30d}</td>
                        <td data-label={a.lastActive} className="nowrap">{relDay(r.last_active)}</td>
                        <td data-label={t.lastLogin} className="nowrap">{relDay(r.last_login_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>
        </>
      )}
    </AppShell>
  );
}
