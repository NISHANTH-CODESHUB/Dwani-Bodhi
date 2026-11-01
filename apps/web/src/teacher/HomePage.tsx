import { Link, useNavigate } from 'react-router-dom';
import { Notice, useLive } from '../components/common';
import { Icon } from '../components/icons';
import { AppShell, Avatar, EmptyState, LevelBars, Panel, ProgressRing, StatTile } from '../components/ui';
import { formatDay, hi, localDay, opSymbol } from '../i18n/hi';
import { useAuth, useClassroom } from '../lib/auth';
import { levelDistribution } from '../lib/childUi';
import { useContent } from '../lib/content';
import { KV_KEYS, childLabel, db, kvGet, kvGetWithTime, type LocalChild } from '../lib/db';
import type { CardResponse, Overview, TodayResponse } from '../lib/types';

function startOfToday(): string {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  return d.toISOString();
}

function todayHeading(): string {
  return new Date().toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'long' });
}

export function HomePage() {
  const auth = useAuth();
  const room = useClassroom()!;
  const content = useContent();
  const nav = useNavigate();
  const cid = room.id;

  const today = useLive(() => kvGetWithTime<TodayResponse>(KV_KEYS.today(cid)), [cid], undefined);
  const card = useLive(() => kvGet<CardResponse>(KV_KEYS.card(cid)), [cid], undefined);
  const overview = useLive(() => kvGet<Overview>(KV_KEYS.overview(cid)), [cid], undefined);
  const unsureCount = useLive(() => kvGet<number>(KV_KEYS.unsureCount(cid)), [cid], undefined);
  const kids = useLive(
    () => db.children.where('classroom_id').equals(cid).filter((c) => !c.deleted).toArray(),
    [cid],
    [] as LocalChild[],
  );
  const doneToday = useLive(
    async () =>
      new Set(
        (await db.sessions.where('started_at').aboveOrEqual(startOfToday()).toArray())
          .filter((s) => s.classroom_id === cid)
          .map((s) => s.child_id),
      ),
    [cid],
    new Set<string>(),
  );

  const byId = new Map(kids.map((k) => [k.id, k]));
  const t = today?.value;
  const stale = t && t.day !== localDay();
  const problems = t?.slate_problems ?? [];
  const list = t?.children ?? [];
  const doneCount = list.filter((c) => doneToday.has(c.child_id)).length;
  const consented = kids.filter((k) => k.consent_status === 'granted').length;
  const pendingConsent = kids.length - consented;
  const ladders = content?.bootstrap.ladders;
  const firstName = (auth?.user.display_name ?? '').split(' ')[0];
  const nextUp = list.find((c) => !doneToday.has(c.child_id) && byId.get(c.child_id)?.consent_status === 'granted');

  return (
    <AppShell title={hi.greeting(firstName)} subtitle={todayHeading()}>
      {!content && <Notice tone="warn">{hi.firstSyncNeeded}</Notice>}

      {/* ---- hero: today's progress + next child ---------------------------------------- */}
      <section className="hero">
        <div className="hero-text">
          <div className="hero-kicker">{hi.todayCheck}</div>
          <div className="hero-title">
            {list.length === 0 ? hi.todayNoneShort : doneCount >= list.length ? hi.todayAllDone : hi.todayRemaining(list.length - doneCount)}
          </div>
          {nextUp ? (
            <button className="btn btn-hero" onClick={() => nav(`/kiosk/${nextUp.child_id}`)}>
              <Icon name="play" size={18} />
              {hi.startWith(childLabel(byId.get(nextUp.child_id)))}
            </button>
          ) : (
            <span className="hero-note">{list.length ? hi.todayGreat : hi.firstSyncNeeded}</span>
          )}
        </div>
        <ProgressRing done={doneCount} total={list.length} size={88} />
      </section>
      {stale && <Notice tone="warn">{hi.todayStale(formatDay(t.day))}</Notice>}

      {/* ---- stats ------------------------------------------------------------------------ */}
      <div className="stats">
        <StatTile icon="users" value={`${consented}/${kids.length}`} label={hi.statConsented} tone="brand" onClick={() => nav('/roster')} />
        <StatTile
          icon="review"
          value={unsureCount ?? '–'}
          label={hi.statReview}
          tone={unsureCount ? 'warn' : 'ok'}
          onClick={() => nav('/unsure')}
        />
        <StatTile icon="clipboard" value={card?.card.groups.length ?? '–'} label={hi.statGroups} tone="violet" onClick={() => nav('/card')} />
      </div>
      {pendingConsent > 0 && (
        <Link to="/roster?filter=consent" className="banner banner-warn">
          <Icon name="pen" size={18} />
          <span className="banner-text">{hi.consentPendingN(pendingConsent)}</span>
          <Icon name="chevronRight" size={18} className="banner-go" />
        </Link>
      )}

      <div className="dash-grid">
        <div className="dash-col">
          {/* ---- today's children -------------------------------------------------------- */}
          <Panel title={hi.todayListTitle} icon="users" hint={hi.todayListHint}>
            {!t && <EmptyState icon="sync" title={hi.firstSyncNeeded} />}
            {t && list.length === 0 && <EmptyState icon="checkCircle" title={hi.todayNone} />}
            <ul className="people">
              {list.map((c) => {
                const kid = byId.get(c.child_id);
                const consent = kid?.consent_status === 'granted';
                const done = doneToday.has(c.child_id);
                return (
                  <li key={c.child_id} className={`person ${done ? 'person-done' : ''}`}>
                    <Link to={`/child/${c.child_id}`} className="person-main">
                      <Avatar id={c.child_id} name={kid?.name ?? ''} slot={kid?.aruco_slot} />
                      <span className="person-text">
                        <span className="person-name">{childLabel(kid)}</span>
                        <span className="person-meta">
                          {kid && <span>{hi.gradeN(kid.grade)}</span>}
                          {c.reasons.map((r) => (
                            <span key={r} className={`tag tag-${r}`}>
                              {hi.reasons[r] ?? r}
                            </span>
                          ))}
                        </span>
                      </span>
                    </Link>
                    {!consent ? (
                      <Link className="btn btn-small btn-warn" to={`/roster/${c.child_id}`}>
                        {hi.needsConsent}
                      </Link>
                    ) : done ? (
                      <span className="done-pill">
                        <Icon name="check" size={14} /> {hi.done}
                      </span>
                    ) : (
                      <Link className="btn btn-primary btn-play" to={`/kiosk/${c.child_id}`} aria-label={`${hi.start} ${childLabel(kid)}`}>
                        <Icon name="play" size={18} />
                      </Link>
                    )}
                  </li>
                );
              })}
            </ul>
          </Panel>

          {/* ---- slate --------------------------------------------------------------------- */}
          <Link to="/slate" className="panel panel-link">
            <div className="panel-head">
              <div className="panel-titles">
                <h2>
                  <Icon name="calc" size={18} className="panel-ico" />
                  {hi.todaySlate}
                </h2>
              </div>
              <span className="link-go">
                {hi.slateScan} <Icon name="chevronRight" size={16} />
              </span>
            </div>
            {problems.length ? (
              <div className="slate-problems">
                {problems.map((p) => (
                  <span key={p.item_id} className="slate-chip">
                    {p.a} {opSymbol(p.op)} {p.b}
                  </span>
                ))}
              </div>
            ) : (
              <p className="muted">{hi.slateNoProblems}</p>
            )}
          </Link>
        </div>

        <div className="dash-col">
          {/* ---- card teaser --------------------------------------------------------------- */}
          <Link to="/card" className="panel panel-link card-teaser">
            <div className="panel-head">
              <div className="panel-titles">
                <h2>
                  <Icon name="clipboard" size={18} className="panel-ico" />
                  {hi.actionCard}
                </h2>
              </div>
              <span className="link-go">
                {hi.open} <Icon name="chevronRight" size={16} />
              </span>
            </div>
            {card ? (
              <ul className="teaser-groups">
                {card.card.groups.slice(0, 3).map((g) => (
                  <li key={g.group_key}>
                    <b>{g.title_hi}</b>
                    <span className="muted small">{g.why_hi}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="muted">{hi.cardNone}</p>
            )}
          </Link>

          {/* ---- class picture ------------------------------------------------------------- */}
          {overview && ladders && (
            <Panel title={hi.classPicture} icon="chart" hint={hi.classPictureHint}>
              <LevelBars title={hi.domains.literacy} rows={levelDistribution(overview.literacy_levels, ladders.literacy ?? [])} />
              <LevelBars title={hi.domains.numeracy} rows={levelDistribution(overview.numeracy_levels, ladders.numeracy ?? [])} />
            </Panel>
          )}
        </div>
      </div>
    </AppShell>
  );
}
