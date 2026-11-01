import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { RegisterNo, StudentActivityPanels, StudentStats } from '../components/activity';
import { ErrorBox, Notice, Spinner, useLive } from '../components/common';
import { Icon } from '../components/icons';
import { Avatar, BandChip, EmptyState, Ladder, Page, Panel } from '../components/ui';
import { formatTime, hi } from '../i18n/hi';
import { api } from '../lib/api';
import { skillBand } from '../lib/childUi';
import { useContent } from '../lib/content';
import { KV_KEYS, childLabel, db, kvGetWithTime, kvSet } from '../lib/db';
import type { ChildProfile, Explanation, ProfileSkill, StudentActivity } from '../lib/types';
import { WcpmChart } from './WcpmChart';

/** The server text refers to the child as {{child}}; the real name only exists on this phone. */
export function fillChild(text: string, name: string): string {
  return text.replace(/\{\{\s*child\s*\}\}/g, name);
}

function SkillList({ skills }: { skills: ProfileSkill[] }) {
  // learning first (most actionable), then not-yet, then known, unknown last
  const order = { learning: 0, notyet: 1, known: 2, unknown: 3 } as const;
  const sorted = [...skills].sort((a, b) => order[skillBand(a.p)] - order[skillBand(b.p)]);
  return (
    <ul className="skill-list">
      {sorted.map((s) => (
        <li key={s.id} className="skill-item">
          <span className="skill-item-name">{s.name_hi}</span>
          <BandChip p={s.p} checking={s.checking} />
        </li>
      ))}
    </ul>
  );
}

export default function ProfilePage() {
  const { id = '' } = useParams();
  const content = useContent();
  const child = useLive(() => db.children.get(id), [id], undefined);
  const cached = useLive(() => kvGetWithTime<ChildProfile>(KV_KEYS.profile(id)), [id], undefined);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [explain, setExplain] = useState<Explanation | null>(null);
  const [explainBusy, setExplainBusy] = useState(false);
  const [explainErr, setExplainErr] = useState<unknown>(null);
  const [tab, setTab] = useState<'literacy' | 'numeracy'>('literacy');
  const [activity, setActivity] = useState<StudentActivity | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      await kvSet(KV_KEYS.profile(id), await api.profile(id));
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    let live = true;
    setActivity(null);
    // Activity timeline: online only (it is a server-side history); the profile above works offline.
    api.studentActivity(id).then((a) => live && setActivity(a), () => undefined);
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const p = cached?.value;
  const name = childLabel(child, p?.aruco_slot);

  const doExplain = async () => {
    setExplainBusy(true);
    setExplainErr(null);
    try {
      setExplain(await api.explain(id));
    } catch (e) {
      setExplainErr(e);
    } finally {
      setExplainBusy(false);
    }
  };

  const bench = (() => {
    const g = p?.grade ?? child?.grade;
    const table = content?.bootstrap.benchmarks.wcpm_by_grade as Record<string, number> | undefined;
    return g !== undefined && table ? table[String(g)] : undefined;
  })();
  const ladders = content?.bootstrap.ladders ?? {};
  const domains: ('literacy' | 'numeracy')[] = ['literacy', 'numeracy'];
  const confirmed = p?.confusions.filter((c) => c.status === 'confirmed') ?? [];
  const suspected = p?.confusions.filter((c) => c.status !== 'confirmed') ?? [];

  return (
    <Page
      title={hi.profile}
      back={true}
      right={
        child ? (
          <Link to={`/roster/${id}`} className="btn btn-small btn-outline appbar-btn" title={hi.editChild}>
            <Icon name="edit" size={18} />
            <span className="appbar-btn-label">{hi.editChild}</span>
          </Link>
        ) : undefined
      }
    >
      {loading && !p && <Spinner />}
      {error && p ? <Notice tone="warn">{hi.offlineCached}</Notice> : <ErrorBox error={p ? null : error} onRetry={load} />}

      <section className="profile-hero">
        <Avatar id={id} name={child?.name ?? ''} slot={p?.aruco_slot ?? child?.aruco_slot} size={72} />
        <div className="profile-hero-text">
          <div className="profile-name">{name}</div>
          <div className="profile-meta">
            {p ? hi.gradeN(p.grade) : child ? hi.gradeN(child.grade) : ''} · {hi.idCard} #{p?.aruco_slot ?? child?.aruco_slot}
          </div>
          <div className="profile-meta">
            {hi.lastAssessed}: {formatTime(p?.last_assessed)}
          </div>
          <div className="profile-meta">
            {hi.act.registerNo}: <RegisterNo value={activity?.student.register_no ?? child?.register_no} />
          </div>
        </div>
        {child?.consent_status === 'granted' && (
          <Link to={`/kiosk/${id}`} className="btn btn-primary" aria-label={hi.check}>
            <Icon name="play" size={18} />
            <span>{hi.check}</span>
          </Link>
        )}
      </section>
      {child && !child.name.trim() && (
        <Link to={`/roster/${id}`} className="banner banner-warn">
          <Icon name="pen" size={18} />
          <span className="banner-text">{hi.nameMissing}</span>
          <Icon name="chevronRight" size={18} className="banner-go" />
        </Link>
      )}

      {p && (
        <>
          {/* ---- levels ------------------------------------------------------------- */}
          <div className="dash-grid">
          <div className="dash-col">
          <Panel title={hi.levelTitle} icon="chart" hint={hi.levelHint}>
            {domains.map((d) => {
              const lv = p.levels[d];
              return (
                <div key={d} className="level-block">
                  <div className="level-block-head">
                    <strong className="with-ico">
                      <Icon name={d === 'literacy' ? 'book' : 'calc'} size={16} /> {hi.domains[d]}
                    </strong>
                    {lv ? (
                      <span className={`band ${lv.certain ? 'band-known' : 'band-learning'}`}>
                        <span className="band-dot" aria-hidden />
                        {lv.name_hi} · {lv.certain ? hi.levelSure : hi.levelUnsure}
                      </span>
                    ) : (
                      <span className="muted small">{hi.notYet}</span>
                    )}
                  </div>
                  {lv && ladders[d] && <Ladder rungs={ladders[d]} current={lv.rung_index} certain={lv.certain} />}
                </div>
              );
            })}
          </Panel>

          {/* ---- confusions ---------------------------------------------------------- */}
          <Panel title={hi.confusions} icon="alert" hint={hi.confusionsHint}>
            {p.confusions.length === 0 && <EmptyState icon="checkCircle" title={hi.noConfusions} />}
            {[...confirmed, ...suspected].map((c) => (
              <div key={c.id} className={`confusion ${c.status === 'confirmed' ? 'confusion-sure' : ''}`}>
                <div className="confusion-head">
                  <span className="confusion-icon" aria-hidden>
                    <Icon name={c.domain === 'numeracy' ? 'calc' : 'book'} size={16} />
                  </span>
                  <span className="confusion-title">{c.description_hi}</span>
                  <span className={`band ${c.status === 'confirmed' ? 'band-notyet' : 'band-learning'}`}>{c.certainty_hi}</span>
                </div>
                {c.examples.length > 0 && (
                  <div className="evidence-ex">
                    {c.examples.map((x) => (
                      <span key={x} className="ex">
                        {x}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </Panel>
          </div>

          <div className="dash-col">
          {/* ---- skills -------------------------------------------------------------- */}
          <Panel title={hi.skillsTitle} icon="checkCircle">
            <div className="seg-tabs" role="tablist">
              {domains.map((d) => (
                <button key={d} role="tab" aria-selected={tab === d} className={`seg-tab ${tab === d ? 'seg-tab-on' : ''}`} onClick={() => setTab(d)}>
                  {hi.domains[d]}
                </button>
              ))}
            </div>
            <SkillList skills={p.skills.filter((s) => s.domain === tab)} />
          </Panel>

          {p.wcpm_history.length > 0 && (
            <Panel title={hi.wcpm} icon="chart" hint={bench !== undefined ? hi.wcpmGoal(bench) : undefined}>
              <WcpmChart points={p.wcpm_history} benchmark={bench} />
            </Panel>
          )}

          <section className="panel explain-panel">
            <button className="btn btn-primary btn-block" onClick={doExplain} disabled={explainBusy}>
              <Icon name="sparkle" size={18} />
              {explainBusy ? hi.explaining : hi.explain}
            </button>
            <ErrorBox error={explainErr} />
            {explain && (
              <div className="explain">
                <p className="explain-summary">{fillChild(explain.summary_hi, name)}</p>
                <ul>
                  {explain.bullets_hi.map((b, i) => (
                    <li key={i}>{fillChild(b, name)}</li>
                  ))}
                </ul>
                <p className="explain-next">
                  <strong>{hi.nextStep}:</strong> {fillChild(explain.next_step_hi, name)}
                </p>
              </div>
            )}
          </section>
          </div>
          </div>
        </>
      )}

      {activity && (
        <section className="activity-section" aria-label={hi.act.timeline}>
          <h2 className="section-title">
            <Icon name="activity" size={20} /> {hi.navActivity}
          </h2>
          <StudentStats s={activity.student} />
          <div className="dash-grid">
            <div className="dash-col">
              <StudentActivityPanels data={activity} />
            </div>
          </div>
        </section>
      )}
    </Page>
  );
}
