/** Build-time configuration (Vite env). */
const rawBase = (import.meta.env.VITE_API_BASE as string | undefined) ?? '';

/** API origin without trailing slash; empty string = same origin as the app. */
export const API_BASE = rawBase.replace(/\/+$/, '');

/** Demo build (`VITE_DEMO=1`): voice items show a text box for the backend's simulated scoring. */
export const DEMO = import.meta.env.VITE_DEMO === '1' || import.meta.env.VITE_DEMO === 'true';

/** No-login build (`VITE_NO_LOGIN=1`, needs AUTH_DISABLED=1 on the API): one tap opens the app as a role. */
export const NO_LOGIN = import.meta.env.VITE_NO_LOGIN === '1' || import.meta.env.VITE_NO_LOGIN === 'true';

/**
 * Max bytes per /v1/sync request (server caps: 2 MB/audio, 6 MB/image). Small batches commit progress
 * often on 2G; a single larger object still goes alone in its own batch.
 */
export const SYNC_MAX_BATCH_BYTES = 1.5 * 1024 * 1024;

/** Background sync interval while the app is open. */
export const SYNC_INTERVAL_MS = 2 * 60 * 1000;
