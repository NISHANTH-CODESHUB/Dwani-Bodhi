import { useEffect, useState } from 'react';
import { Link, useLocation, useSearchParams } from 'react-router-dom';
import { Accuracy, ConsentTag, LevelText, RegisterNo, relDay } from '../components/activity';
import { ErrorBox, Notice, Spinner } from '../components/common';
import { Icon } from '../components/icons';
import { AppShell, EmptyState, Panel } from '../components/ui';
import { hi } from '../i18n/hi';
import { api } from '../lib/api';
import type { AdminStudentPage, ConsentStatus } from '../lib/types';

const t = hi.dash;
const a = hi.act;
const PAGE = 25;

/** Admin: every student in scope, filterable by school/class/grade/consent, searchable by register number. */
export default function AdminStudentsPage() {
  const [params, setParams] = useSearchParams();
  const erased = (useLocation().state as { erased?: string } | null)?.erased;
  const school = params.get('school') ?? '';
  const room = params.get('class') ?? '';
  const grade = params.get('grade') ?? '';
  const consent = (params.get('consent') ?? '') as ConsentStatus | '';
  const offset = Number(params.get('offset') ?? 0) || 0;
  const [q, setQ] = useState(params.get('q') ?? '');
  const [data, setData] = useState<AdminStudentPage | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);

  const set = (patch: Record<string, string>) => {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(patch)) {
      if (v) next.set(k, v);
      else next.delete(k);
    }
    if (!('offset' in patch)) next.delete('offset'); // any filter change goes back to page 1
    setParams(next, { replace: true });
  };

  useEffect(() => {
    let live = true;
    setLoading(true);
    setError(null);
    api
      .adminStudents({
        school_id: school || undefined,
        classroom_id: room || undefined,
        grade: grade ? Number(grade) : undefined,
        consent: consent || undefined,
        q: params.get('q') || undefined,
        limit: PAGE,
        offset,
      })
      .then(
        (res) => live && setData(res),
        (e) => live && setError(e),
      )
      .finally(() => live && setLoading(false));
    return () => {
      live = false;
    };
  }, [school, room, grade, consent, offset, params]);

  // Search as you type, debounced so each keystroke doesn't hit the server.
  useEffect(() => {
    const id = window.setTimeout(() => {
      if ((params.get('q') ?? '') !== q.trim()) set({ q: q.trim() });
    }, 350);
    return () => window.clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q]);

  const rooms = (data?.classrooms ?? []).filter((r) => !school || r.school_id === school);
  const filtered = !!(school || room || grade || consent || params.get('q'));
  const total = data?.total ?? 0;

  return (
    <AppShell title={t.studentsTitle} subtitle={t.studentsSub}>
      <div className="toolbar">
        <label className="search-wrap">
          <Icon name="search" size={18} className="search-ico" />
          <input className="search" type="search" placeholder={a.searchReg} value={q} onChange={(e) => setQ(e.target.value)} aria-label={a.searchReg} />
        </label>
      </div>
      <div className="filter-row">
        <label className="filter-field">
          <span>{t.filterSchool}</span>
          <select value={school} onChange={(e) => set({ school: e.target.value, class: '' })}>
            <option value="">{a.all}</option>
            {(data?.schools ?? []).map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </label>
        <label className="filter-field">
          <span>{t.filterClass}</span>
          <select value={room} onChange={(e) => set({ class: e.target.value })}>
            <option value="">{a.all}</option>
            {rooms.map((r) => (
              <option key={r.id} value={r.id}>
                {school ? r.name : `${r.school} — ${r.name}`}
              </option>
            ))}
          </select>
        </label>
        <label className="filter-field">
          <span>{t.filterGrade}</span>
          <select value={grade} onChange={(e) => set({ grade: e.target.value })}>
            <option value="">{a.all}</option>
            {[1, 2, 3, 4, 5].map((g) => (
              <option key={g} value={g}>
                {g}
              </option>
            ))}
          </select>
        </label>
        <label className="filter-field">
          <span>{t.filterConsent}</span>
          <select value={consent} onChange={(e) => set({ consent: e.target.value })}>
            <option value="">{a.all}</option>
            {(['granted', 'pending', 'withdrawn'] as const).map((c) => (
              <option key={c} value={c}>
                {a.consentLabel[c]}
              </option>
            ))}
          </select>
        </label>
        {filtered && (
          <button
            className="btn btn-small btn-ghost"
            onClick={() => {
              setQ('');
              setParams({}, { replace: true });
            }}
          >
            {t.clear}
          </button>
        )}
      </div>

      {erased && <Notice tone="ok">{t.erased}</Notice>}
      <ErrorBox error={error} />
      {!data && loading && <Spinner />}
      {data && (
        <Panel title={a.studentsN(total)} icon="users" hint={t.namesNote}>
          {data.students.length === 0 ? (
            <EmptyState icon="search" title={t.noStudents} />
          ) : (
            <div className={`table-wrap ${loading ? 'is-loading' : ''}`}>
              <table className="dtable dtable-students dtable-stack">
                <thead>
                  <tr>
                    <th>{a.registerNo}</th>
                    <th>{a.class}</th>
                    <th className="num">{a.grade}</th>
                    <th className="num">{a.sessions}</th>
                    <th>{a.accuracy}</th>
                    <th>{a.literacy}</th>
                    <th>{a.numeracy}</th>
                    <th>{a.lastActive}</th>
                    <th>{a.consent}</th>
                  </tr>
                </thead>
                <tbody>
                  {data.students.map((s) => (
                    <tr key={s.id}>
                      <td>
                        <Link to={`/admin/students/${s.id}`} className="dtable-link">
                          <RegisterNo value={s.register_no} />
                        </Link>
                      </td>
                      <td data-label={a.class}>
                        <span className="dtable-name">{s.classroom}</span>
                        <span className="muted small">
                          {s.school} · #{s.aruco_slot}
                        </span>
                      </td>
                      <td data-label={a.grade} className="num">{s.grade}</td>
                      <td data-label={a.sessions} className="num">{s.sessions}</td>
                      <td data-label={a.accuracy}>
                        <Accuracy value={s.accuracy} />
                      </td>
                      <td data-label={a.literacy}>
                        <LevelText level={s.literacy} />
                      </td>
                      <td data-label={a.numeracy}>
                        <LevelText level={s.numeracy} />
                      </td>
                      <td data-label={a.lastActive} className="nowrap">{relDay(s.last_active)}</td>
                      <td data-label={a.consent}>
                        <ConsentTag value={s.consent} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {total > PAGE && (
            <div className="pager">
              <button className="btn btn-small btn-outline" disabled={offset === 0} onClick={() => set({ offset: String(Math.max(0, offset - PAGE)) })}>
                <Icon name="back" size={16} />
                {t.prev}
              </button>
              <span className="muted small">{t.showing(offset + 1, Math.min(offset + PAGE, total), total)}</span>
              <button className="btn btn-small btn-outline" disabled={offset + PAGE >= total} onClick={() => set({ offset: String(offset + PAGE) })}>
                {t.next}
                <Icon name="chevronRight" size={16} />
              </button>
            </div>
          )}
        </Panel>
      )}
    </AppShell>
  );
}
