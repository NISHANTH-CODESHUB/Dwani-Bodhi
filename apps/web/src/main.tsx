import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { registerSW } from 'virtual:pwa-register';
import { App } from './App';
import { ErrorBoundary } from './components/ErrorBoundary';
import './app.css';
import './kiosk.css';

// Service worker: offline app shell, auto-updates in the background (Workbox, registerType=autoUpdate).
// A new version activates whenever its download finishes, which can be in the middle of a child's kiosk
// session: reload right away on teacher screens, but wait until the kiosk is closed.
if ('serviceWorker' in navigator) {
  const inKiosk = () => window.location.pathname.startsWith('/kiosk');
  registerSW({
    immediate: true,
    onNeedReload() {
      if (!inKiosk()) return window.location.reload();
      const wait = window.setInterval(() => {
        if (!inKiosk()) {
          window.clearInterval(wait);
          window.location.reload();
        }
      }, 2000);
    },
  });
}

// Ask the browser not to evict our IndexedDB (queued recordings) under storage pressure.
if (navigator.storage?.persist) {
  void navigator.storage.persisted().then((p) => (p ? undefined : navigator.storage.persist()));
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </StrictMode>,
);
