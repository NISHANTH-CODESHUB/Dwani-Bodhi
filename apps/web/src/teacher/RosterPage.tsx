import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useLive } from '../components/common';
import { Icon } from '../components/icons';
import { RegisterNo } from '../components/activity';
import { AppShell, Avatar, EmptyState } from '../components/ui';
import { hi } from '../i18n/hi';
import { useClassroom } from '../lib/auth';
import { childLabel, db, KV_KEYS, kvGet, type LocalChild } from '../lib/db';
import { pullRoster } from '../lib/sync';
import type { Overview } from '../lib/types';

type Filter = 'all' | 'consent' | 'noname' | 'unsynced';

export default function RosterPage() {
  const room = useClassroom()!;
  const [params, setParams] = useSearchParams();
  const filter = (params.get('filter') as Filter) || 'all';
  const [q, setQ] = useState('');
  const kids = useLive(
    () => db.children.where('classroom_id').equals(room.id).filter((c) => !c.deleted).sortBy('aruco_slot'),
    [room.id],
    [] as LocalChild[],
  );
  const overview = useLive(() => kvGet<Overview>(KV_KEYS.overview(room.id)), [room.id], undefined);
  const levelOf = useMemo(() => new Map((overview?.children ?? []).map((c) => [c.child_id, c])), [overview]);

  useEffect(() => {
    if (navigator.onLine) pullRoster(room.id).catch(() => undefined);
  }, [room.id]);

  const counts = {
    all: kids.length,
    consent: kids.filter((k) => k.consent_status !== 'granted').length,
    noname: kids.filter((k) => !k.name.trim()).length,
    unsynced: kids.filter((k) => k.dirty === 1 || k.sync_error).length,
  };
  const shown = kids.filter((k) => {
    if (filter === 'consent' && k.consent_status === 'granted') return false;
    if (filter === 'noname' && k.name.trim()) return false;
    if (filter === 'unsynced' && !(k.dirty === 1 || k.sync_error)) return false;
    const s = q.trim();
    if (!s) return true;
    return (
      k.name.toLowerCase().includes(s.toLowerCase()) ||
      String(k.aruco_slot) === s.replace('#', '') ||
      (k.register_no ?? '').toLowerCase().includes(s.toLowerCase())
    );
  });

  const setFilter = (f: Filter) => setParams(f === 'all' ? {} : { filter: f }, { replace: true });

  return (
    <AppShell
      title={hi.rosterTitle}
      subtitle={hi.childrenN(kids.length)}
      actions={
        <Link to="/idcards" className="btn btn-small btn-outline appbar-btn" title={hi.idCards}>
          <Icon name="idcard" size={18} />
          <span className="appbar-btn-label">{hi.idCards}</span>
        </Link>
      }
    >
      <div className="toolbar">
        <label className="search-wrap">
          <Icon name="search" size={18} className="search-ico" />
          <input
          className="search"
          type="search"
          placeholder={hi.searchPlaceholder}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          aria-label={hi.searchPlaceholder}
          />
        </label>
        <Link to="/roster/new" className="btn btn-primary">
          <Icon name="plus" size={18} />
          {hi.addChildShort}
        </Link>
      </div>
      <div className="filters" role="tablist">
        {(['all', 'consent', 'noname', 'unsynced'] as Filter[]).map((f) => (
          <button key={f} role="tab" aria-selected={filter === f} className={`filter ${filter === f ? 'filter-on' : ''}`} onClick={() => setFilter(f)}>
            {hi.rosterFilters[f]} <b>{counts[f]}</b>
          </button>
        ))}
      </div>

      {kids.length === 0 && (
        <EmptyState icon="users" title={hi.noChildren}>
          <Link to="/roster/new" className="btn btn-primary">
            {hi.addChild}
          </Link>
        </EmptyState>
      )}
      {kids.length > 0 && shown.length === 0 && <EmptyState icon="search" title={hi.noMatches} />}

      <ul className="people people-card">
        {shown.map((k) => {
          const ov = levelOf.get(k.id);
          return (
            <li key={k.id} className="person">
              <Link to={`/child/${k.id}`} className="person-main">
                <Avatar id={k.id} name={k.name} slot={k.aruco_slot} />
                <span className="person-text">
                  <span className="person-name">
                    {childLabel(k)}
                    {!k.name.trim() && <span className="tag tag-warn">{hi.addName}</span>}
                  </span>
                  <span className="person-meta">
                    <span>{hi.gradeN(k.grade)}</span>
                    <span>#{k.aruco_slot}</span>
                    <RegisterNo value={k.register_no} />
                    {ov?.literacy && <span className="tag tag-lit"><Icon name="book" size={13} /> {ov.literacy.name_hi}</span>}
                    {ov?.numeracy && <span className="tag tag-num"><Icon name="calc" size={13} /> {ov.numeracy.name_hi}</span>}
                    {k.consent_status !== 'granted' && <span className="tag tag-warn">{hi.consentStates[k.consent_status]}</span>}
                    {k.dirty === 1 && <span className="tag">{hi.notSynced}</span>}
                    {k.sync_error && <span className="tag tag-danger">{k.sync_error === 'slot_clash' ? hi.slotClash : k.sync_error}</span>}
                  </span>
                </span>
              </Link>
              <span className="person-actions">
                <Link to={`/roster/${k.id}`} className="icon-btn icon-btn-subtle" aria-label={`${hi.editChild} ${childLabel(k)}`}>
                  <Icon name="edit" size={18} />
                </Link>
                {k.consent_status === 'granted' && (
                  <Link to={`/kiosk/${k.id}`} className="btn btn-primary btn-play" aria-label={`${hi.check} ${childLabel(k)}`}>
                    <Icon name="play" size={18} />
                  </Link>
                )}
              </span>
            </li>
          );
        })}
      </ul>
    </AppShell>
  );
}
