import { Component, type ErrorInfo, type ReactNode } from 'react';
import { hi } from '../i18n/hi';

/**
 * Last line of defence: a render error or a lazy page that fails to load (old cache after a deploy) would
 * otherwise leave a blank white screen with no way back. Data in IndexedDB is untouched by a reload.
 */
export class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  override state = { failed: false };

  static getDerivedStateFromError(): { failed: boolean } {
    return { failed: true };
  }

  override componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('UI crashed', error, info.componentStack);
  }

  override render(): ReactNode {
    if (!this.state.failed) return this.props.children;
    return (
      <div className="login">
        <main className="login-main">
          <div className="login-card" role="alert">
            <div className="login-card-head">
              <h1>{hi.crashTitle}</h1>
              <p className="muted">{hi.crashSub}</p>
            </div>
            <button className="btn btn-primary btn-block btn-lg" onClick={() => window.location.reload()}>
              {hi.crashReload}
            </button>
          </div>
        </main>
      </div>
    );
  }
}
