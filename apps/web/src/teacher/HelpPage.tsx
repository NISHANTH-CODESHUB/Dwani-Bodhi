import { Icon, type IconName } from '../components/icons';
import { Page, Panel } from '../components/ui';
import { hi } from '../i18n/hi';

/** Step-by-step usage guide (Hindi), reachable from the sidebar / menu on every screen. */
export default function HelpPage() {
  return (
    <Page title={hi.helpTitle} back={true}>
      <p className="lead">{hi.helpIntro}</p>
      <ol className="help-steps">
          {hi.helpSteps.map((s) => (
            <li key={s.title} className="help-step">
              <span className="help-step-icon" aria-hidden>
                <Icon name={s.icon as IconName} size={22} />
              </span>
              <span className="help-step-text">
                <strong>{s.title}</strong>
                <span>{s.body}</span>
              </span>
            </li>
          ))}
      </ol>
      <Panel title={hi.helpPrivacyTitle} icon="shield">
        <p>{hi.helpPrivacy}</p>
      </Panel>
    </Page>
  );
}
