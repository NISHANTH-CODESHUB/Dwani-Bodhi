import { Notice, useLive } from '../components/common';
import { Icon } from '../components/icons';
import { EmptyState, Page } from '../components/ui';
import { hi } from '../i18n/hi';
import { useClassroom } from '../lib/auth';
import { childLabel, db, type LocalChild } from '../lib/db';

/** Hint screen: which ID-card number belongs to which child (printable via the browser's print). */
export default function IdCardsPage() {
  const room = useClassroom()!;
  const kids = useLive(
    () => db.children.where('classroom_id').equals(room.id).filter((c) => !c.deleted).sortBy('aruco_slot'),
    [room.id],
    [] as LocalChild[],
  );
  return (
    <Page
      title={hi.idCardsTitle}
      back="/roster"
      right={
        <button className="btn btn-small btn-outline appbar-btn" onClick={() => window.print()} aria-label={hi.print}>
          <Icon name="print" size={18} />
          <span className="appbar-btn-label">{hi.print}</span>
        </button>
      }
    >
      <Notice>{hi.idCardsHint}</Notice>
      {kids.length === 0 && <EmptyState icon="idcard" title={hi.noChildren} />}
      <div className="idcard-grid">
        {kids.map((k) => (
          <div key={k.id} className="idcard">
            <span className="idcard-slot">{k.aruco_slot}</span>
            <span className="idcard-name">{childLabel(k)}</span>
            <span className="muted small">{hi.gradeN(k.grade)}</span>
          </div>
        ))}
      </div>
    </Page>
  );
}
