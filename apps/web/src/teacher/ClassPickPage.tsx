import { useNavigate } from 'react-router-dom';
import { Notice } from '../components/common';
import { Icon } from '../components/icons';
import { Page } from '../components/ui';
import { hi } from '../i18n/hi';
import { setClassroom, useAuth, useClassroom } from '../lib/auth';
import { runSync } from '../lib/sync';
import { LogoutButton } from './LogoutButton';

export function ClassPickPage() {
  const auth = useAuth();
  const current = useClassroom();
  const nav = useNavigate();
  const rooms = auth?.classrooms ?? [];

  const pick = (id: string) => {
    setClassroom(id);
    void runSync({ manual: true });
    nav('/', { replace: true });
  };

  return (
    <Page narrow title={hi.chooseClass} back={current ? '/' : undefined} right={current ? undefined : <LogoutButton />}>
      {rooms.length === 0 && <Notice tone="warn">{hi.noClassrooms}</Notice>}
      <div className="list">
        {rooms.map((r) => (
          <button key={r.id} className={`row-link ${r.id === current?.id ? 'row-active' : ''}`} onClick={() => pick(r.id)}>
            <span className="row-icon" aria-hidden>
              <Icon name="school" />
            </span>
            <span className="row-text">
              <span className="row-title">{r.name}</span>
              <span className="row-sub">
                {r.school ?? ''} · {r.grades.map((g) => hi.gradeN(g)).join(', ')}
              </span>
            </span>
            {r.id === current?.id ? <Icon name="checkCircle" className="row-check" /> : <Icon name="chevronRight" className="row-chev" />}
          </button>
        ))}
      </div>
    </Page>
  );
}
