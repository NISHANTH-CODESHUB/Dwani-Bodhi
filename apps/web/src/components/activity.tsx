/** Student-activity building blocks shared by the teacher and admin dashboards. */
import { useState } from 'react';
import { formatDay, formatTime, hi } from '../i18n/hi';
import type { ActivityEntry, DailyPoint, DomainStats, LevelRef, StudentActivity, StudentRow } from '../lib/types';
import { Icon } from './icons';
import { Panel } from './ui';

const t = hi.act;

export function pct(x: number | null | undefined): string {
  return x === null || x === undefined ? '—' : `${Math.round(x * 100)}%`;
}

/** "Today", "Yesterday", "3 days ago", else a date. */
export function relDay(iso: string | null | undefined): string {
  if (!iso) return t.never;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return t.never;
  const days = Math.floor((startOfDay(new Date()) - startOfDay(d)) / 86_400_000);
  if (days <= 0) return 'Today';
  if (days === 1) return 'Yesterday';
  if (days < 7) return `${days} days ago`;
  return formatDay(iso);
}

function startOfDay(d: Date): number {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
}

export function RegisterNo({ value, large }: { value: string | null | undefined; large?: boolean }) {
  return value ? (
    <span className={`regno ${large ? 'regno-lg' : ''}`} title={t.registerNo}>
      {value}
    </span>
  ) : (
    <span className="regno regno-pending" title={t.registerPending}>
      {t.registerPending}
    </span>
  );
}

/** Accuracy as a thin meter plus the number (the number carries the meaning; the bar is a glance aid). */
export function Accuracy({ value }: { value: number | null }) {
  if (value === null) return <span className="muted">—</span>;
  return (
    <span className="acc">
      <span className="acc-track" aria-hidden>
        <span className="acc-fill" style={{ width: `${Math.round(value * 100)}%` }} />
      </span>
      <span className="acc-num">{pct(value)}</span>
    </span>
  );
}

export function LevelText({ level }: { level: LevelRef | null }) {
  if (!level?.name) return <span className="muted">{t.never}</span>;
  return (
    <span className={level.certain === false ? 'level-unsure' : ''} title={level.certain === false ? hi.checking : undefined}>
      {level.name}
    </span>
  );
}

export function ConsentTag({ value }: { value: string }) {
  const tone = value === 'granted' ? 'tag-ok' : 'tag-warn';
  return <span className={`tag ${tone}`}>{t.consentLabel[value] ?? value}</span>;
}

/* ---------------------------------------------------------------------------- daily chart */
/**
 * Sessions per day as thin bars (single series: the title names it, so no legend). Hover/tap a bar for
 * the exact numbers; a table view carries the same data for screen readers and print.
 */
export function DailyChart({ data, title }: { data: DailyPoint[]; title: string }) {
  const [hover, setHover] = useState<number | null>(null);
  const [asTable, setAsTable] = useState(false);
  const max = Math.max(1, ...data.map((d) => d.sessions));
  const total = data.reduce((n, d) => n + d.sessions, 0);
  const top = niceMax(max);
  return (
    <Panel
      title={title}
      icon="chart"
      action={
        <button className="btn btn-small btn-ghost" onClick={() => setAsTable((v) => !v)}>
          {asTable ? t.dailyChart : t.dailyTable}
        </button>
      }
    >
      {asTable ? (
        <div className="table-wrap">
          <table className="dtable">
            <thead>
              <tr>
                <th>{t.day}</th>
                <th className="num">{t.sessions}</th>
                <th className="num">{t.answers}</th>
              </tr>
            </thead>
            <tbody>
              {data.map((d) => (
                <tr key={d.day}>
                  <td>{formatDay(d.day)}</td>
                  <td className="num">{d.sessions}</td>
                  <td className="num">{d.answers}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="dchart" role="img" aria-label={`${title}: ${total} ${t.sessions.toLowerCase()}`}>
          {total === 0 && <div className="dchart-empty muted small">{t.noData}</div>}
          <div className="dchart-axis small muted" aria-hidden>
            <span>{top}</span>
            <span>0</span>
          </div>
          <div className="dchart-plot" onMouseLeave={() => setHover(null)}>
            <span className="dchart-grid dchart-grid-top" aria-hidden />
            <span className="dchart-grid dchart-grid-mid" aria-hidden />
            {data.map((d, i) => (
              <button
                key={d.day}
                type="button"
                className={`dchart-col ${hover === i ? 'dchart-col-on' : ''}`}
                onMouseEnter={() => setHover(i)}
                onFocus={() => setHover(i)}
                onBlur={() => setHover(null)}
                onClick={() => setHover(hover === i ? null : i)}
                aria-label={`${formatDay(d.day)}: ${d.sessions} ${t.sessions}, ${d.answers} ${t.answers}`}
              >
                <span className="dchart-bar" style={{ height: d.sessions ? `${Math.max(4, (d.sessions / top) * 100)}%` : 0 }} />
              </button>
            ))}
            {hover !== null && data[hover] && (
              <div
                className="dchart-tip"
                role="status"
                style={{ left: `${((hover + 0.5) / data.length) * 100}%` }}
              >
                <strong>{formatDay(data[hover].day)}</strong>
                <span>
                  {data[hover].sessions} {t.sessions.toLowerCase()} · {data[hover].answers} {t.answers.toLowerCase()}
                </span>
              </div>
            )}
          </div>
          <div className="dchart-x small muted" aria-hidden>
            <span>{formatDay(data[0]?.day ?? '')}</span>
            <span>{formatDay(data[data.length - 1]?.day ?? '')}</span>
          </div>
        </div>
      )}
    </Panel>
  );
}

function niceMax(n: number): number {
  if (n <= 5) return 5;
  if (n <= 10) return 10;
  const p = 10 ** Math.floor(Math.log10(n));
  return Math.ceil(n / p) * p;
}

/* ---------------------------------------------------------------------------- summaries */
export function DomainSummary({ domains }: { domains: { literacy: DomainStats; numeracy: DomainStats } }) {
  const row = (label: string, icon: 'book' | 'calc', d: DomainStats) => (
    <div className="dom-row">
      <span className="dom-name">
        <Icon name={icon} size={18} /> {label}
      </span>
      <span className="dom-figs">
        <span>
          <b>{d.correct}</b> {t.correct.toLowerCase()}
        </span>
        <span>
          <b>{d.incorrect}</b> {t.incorrect.toLowerCase()}
        </span>
        {d.to_review > 0 && (
          <span>
            <b>{d.to_review}</b> {t.toReview.toLowerCase()}
          </span>
        )}
      </span>
      <Accuracy value={d.accuracy} />
    </div>
  );
  return (
    <Panel title={t.byDomain} icon="checkCircle">
      <div className="dom">
        {row(t.literacy, 'book', domains.literacy)}
        {row(t.numeracy, 'calc', domains.numeracy)}
      </div>
    </Panel>
  );
}

export function StudentFacts({ s }: { s: StudentRow }) {
  return (
    <dl className="facts">
      <div>
        <dt>{t.registerNo}</dt>
        <dd>
          <RegisterNo value={s.register_no} />
        </dd>
      </div>
      <div>
        <dt>{t.grade}</dt>
        <dd>{s.grade}</dd>
      </div>
      <div>
        <dt>{t.class}</dt>
        <dd>
          {s.classroom ?? '—'} · {t.idCard(s.aruco_slot)}
        </dd>
      </div>
      <div>
        <dt>{t.school}</dt>
        <dd>{s.school ?? '—'}</dd>
      </div>
      <div>
        <dt>{t.teacher}</dt>
        <dd>{s.teachers.length ? s.teachers.join(', ') : '—'}</dd>
      </div>
      <div>
        <dt>{t.consent}</dt>
        <dd>
          <ConsentTag value={s.consent} />
        </dd>
      </div>
      <div>
        <dt>
          {t.level}: {t.literacy}
        </dt>
        <dd>
          <LevelText level={s.literacy} />
        </dd>
      </div>
      <div>
        <dt>
          {t.level}: {t.numeracy}
        </dt>
        <dd>
          <LevelText level={s.numeracy} />
        </dd>
      </div>
    </dl>
  );
}

export function StudentStats({ s }: { s: StudentRow }) {
  return (
    <div className="kpis">
      <Kpi label={t.sessions} value={s.sessions} sub={`${s.sessions_7d} this week`} />
      <Kpi label={t.answers} value={s.responses} />
      <Kpi label={t.accuracy} value={pct(s.accuracy)} />
      <Kpi label={t.lastActive} value={relDay(s.last_active)} />
    </div>
  );
}

export function Kpi({ label, value, sub, tone }: { label: string; value: string | number; sub?: string; tone?: 'warn' | 'ok' }) {
  return (
    <div className={`kpi ${tone ? `kpi-${tone}` : ''}`}>
      <span className="kpi-value">{value}</span>
      <span className="kpi-label">{label}</span>
      {sub && <span className="kpi-sub">{sub}</span>}
    </div>
  );
}

/* ---------------------------------------------------------------------------- timeline */
function Entry({ e }: { e: ActivityEntry }) {
  const [open, setOpen] = useState(false);
  return (
    <li className="tl-item">
      <span className={`tl-dot ${e.kind === 'slate' ? 'tl-dot-slate' : ''}`} aria-hidden>
        <Icon name={e.kind === 'slate' ? 'camera' : 'play'} size={14} />
      </span>
      <div className="tl-body">
        <div className="tl-head">
          <strong>{e.kind === 'slate' ? t.slateCheck : t.kioskSession}</strong>
          <span className="muted small">{formatTime(e.at)}</span>
          {e.duration_s ? <span className="chip">{t.minutes(e.duration_s)}</span> : null}
          {e.discontinued && <span className="tag tag-warn">{t.stopped}</span>}
        </div>
        <div className="tl-figs small">
          <span>
            {e.answers} {t.answers.toLowerCase()}
          </span>
          <span className="tl-ok">
            <Icon name="check" size={14} /> {e.correct}
          </span>
          <span className="tl-bad">
            <Icon name="alert" size={14} /> {e.incorrect}
          </span>
          {e.to_review > 0 && (
            <span>
              {e.to_review} {t.toReview.toLowerCase()}
            </span>
          )}
          {e.waiting > 0 && (
            <span>
              {e.waiting} {t.waiting.toLowerCase()}
            </span>
          )}
          <Accuracy value={e.accuracy} />
        </div>
        {e.items.length > 0 && (
          <button className="btn btn-small btn-ghost tl-toggle" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
            <Icon name={open ? 'chevronDown' : 'chevronRight'} size={16} />
            {open ? t.hideItems : t.showItems(e.items.length)}
          </button>
        )}
        {open && (
          <ul className="tl-answers">
            {e.items.map((it) => (
              <li key={it.id} className={`tl-ans tl-ans-${it.outcome}`}>
                <span className="tl-ans-label" lang={it.domain === 'literacy' ? 'hi' : undefined}>
                  {it.label}
                </span>
                <span className="tl-ans-detail muted small">{it.detail}</span>
                <span className={`tl-ans-out tl-out-${it.outcome}`}>
                  <Icon name={it.outcome === 'correct' ? 'check' : it.outcome === 'incorrect' ? 'alert' : 'clock'} size={14} />
                  {t.outcome[it.outcome] ?? it.outcome}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </li>
  );
}

export function ActivityTimeline({ entries }: { entries: ActivityEntry[] }) {
  return (
    <Panel title={t.timeline} icon="clock">
      {entries.length === 0 ? (
        <p className="muted">{t.timelineEmpty}</p>
      ) : (
        <ol className="tl">
          {entries.map((e) => (
            <Entry key={e.id} e={e} />
          ))}
        </ol>
      )}
    </Panel>
  );
}

/** Everything about one student's activity: subject results, daily chart, timeline. */
export function StudentActivityPanels({ data }: { data: StudentActivity }) {
  return (
    <>
      <DomainSummary domains={data.domains} />
      <DailyChart data={data.daily} title={t.daily30} />
      <ActivityTimeline entries={data.timeline} />
    </>
  );
}
