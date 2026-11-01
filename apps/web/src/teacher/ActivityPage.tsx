import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Accuracy, DailyChart, Kpi, LevelText, pct, RegisterNo, relDay } from '../components/activity';
import { ErrorBox, Spinner, useLive } from '../components/common';
import { Icon } from '../components/icons';
import { AppShell, Avatar, EmptyState, Panel } from '../components/ui';
import { hi } from '../i18n/hi';
import { api } from '../lib/api';
import { useClassroom } from '../lib/auth';
import { childLabel, db, KV_KEYS, kvGet, kvSet, type LocalChild } from '../lib/db';
import type { ClassActivity, StudentRow } from '../lib/types';

const t = hi.classAct;
const a = hi.act;
type Sort = 'slot' | 'active' | 'accuracy' | 'sessions';

function sorter(key: Sort): (x: StudentRow, y: StudentRow) => number {
  switch (key) {
    case 'active':
      return (x, y) => (y.last_active ?? '').localeCompare(x.last_active ?? '');
    case 'accuracy':
      return (x, y) => (x.accuracy ?? 2) - (y.accuracy ?? 2); // lowest first: who needs help
    case 'sessions':
      return (x, y) => y.sessions - x.sessions;
    default:
      return (x, y) => x.aruco_slot - y.aruco_slot;
  }
}

/** Teacher: what every student in the class has done, with names from this phone. */
export default function ActivityPage() {
  const room = useClassroom()!;
  const cached = useLive(() => kvGet<ClassActivity>(KV_KEYS.classActivity(room.id)), [room.id], undefined);
  const [fresh, setFresh] = useState<ClassActivity | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [sort, setSort] = useState<Sort>('slot');
  const kids = useLive(() => db.children.where('classroom_id').equals(room.id).toArray(), [room.id], [] as LocalChild[]);
  const local = useMemo(() => new Map(kids.map((k) => [k.id, k])), [kids]);

  const load = async () => {
    setError(null);
    try {
      const res = await api.classActivity(room.id);
      setFresh(res);
      await kvSet(KV_KEYS.classActivity(room.id), res);
    } catch (e) {
      setError(e);
    }
  };

  useEffect(() => {
    setFresh(null);
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [room.id]);

  const data = fresh ?? cached ?? null;
  const rows = useMemo(() => [...(data?.students ?? [])].sort(sorter(sort)), [data, sort]);

  return (
    <AppShell title={t.title} subtitle={t.sub}>
      {!fresh && cached && <p className="muted small">{t.offlineNote}</p>}
      <ErrorBox error={error && !data ? error : null} onRetry={load} />
      {!data && !error && <Spinner />}
      {data && (
        <>
          <div className="kpis">
            <Kpi label={t.students} value={data.totals.students} sub={`${data.totals.consented} ${a.consentLabel.granted.toLowerCase()}`} />
            <Kpi label={t.active7d} value={data.totals.active_7d} />
            <Kpi label={t.sessions14d} value={data.totals.sessions_14d} sub={`${data.totals.answers_14d} ${a.answers.toLowerCase()}`} />
            <Kpi label={t.accuracy} value={pct(data.totals.accuracy)} />
            <Kpi label={t.toReview} value={data.totals.to_review} tone={data.totals.to_review ? 'warn' : undefined} />
          </div>
          <DailyChart data={data.daily} title={a.daily14} />
          <Panel
            title={t.table}
            icon="users"
            action={
              <label className="sort">
                <span className="muted small">{t.sortBy}</span>
                <select value={sort} onChange={(e) => setSort(e.target.value as Sort)}>
                  {(Object.keys(t.sort) as Sort[]).map((k) => (
                    <option key={k} value={k}>
                      {t.sort[k]}
                    </option>
                  ))}
                </select>
              </label>
            }
          >
            {rows.length === 0 ? (
              <EmptyState icon="users" title={hi.noChildren} />
            ) : (
              <div className="table-wrap">
                <table className="dtable dtable-students dtable-stack">
                  <thead>
                    <tr>
                      <th>{hi.children}</th>
                      <th>{a.registerNo}</th>
                      <th className="num">{a.sessions}</th>
                      <th>{a.accuracy}</th>
                      <th>{a.literacy}</th>
                      <th>{a.numeracy}</th>
                      <th>{a.lastActive}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((s) => {
                      const k = local.get(s.id);
                      return (
                        <tr key={s.id}>
                          <td>
                            <Link to={`/child/${s.id}`} className="dtable-person">
                              <Avatar id={s.id} name={k?.name ?? ''} slot={s.aruco_slot} size={32} />
                              <span>
                                <span className="dtable-name">{childLabel(k, s.aruco_slot)}</span>
                                <span className="muted small">
                                  {hi.gradeN(s.grade)} · #{s.aruco_slot}
                                  {s.consent !== 'granted' && <> · {a.consentLabel[s.consent]}</>}
                                </span>
                              </span>
                            </Link>
                          </td>
                          <td data-label={a.registerNo}>
                            <RegisterNo value={s.register_no} />
                          </td>
                          <td data-label={a.sessions} className="num">
                            {s.sessions}
                            {s.sessions_7d > 0 && <span className="muted small"> (+{s.sessions_7d})</span>}
                          </td>
                          <td data-label={a.accuracy}>
                            <Accuracy value={s.accuracy} />
                          </td>
                          <td data-label={a.literacy}>
                            <LevelText level={s.literacy} />
                          </td>
                          <td data-label={a.numeracy}>
                            <LevelText level={s.numeracy} />
                          </td>
                          <td data-label={a.lastActive} className="nowrap">
                            {relDay(s.last_active)}
                            {s.to_review > 0 && (
                              <span className="tag tag-warn" title={a.toReview}>
                                <Icon name="review" size={12} /> {s.to_review}
                              </span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
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
