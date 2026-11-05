
/** Build-time configuration (Vite env). */
const rawBase =
  (import.meta.env.VITE_API_BASE as string | undefined) ??
  'https://dwani-bodhi-api.onrender.com';

/** API origin without trailing slash. */
export const API_BASE = rawBase.replace(/\/+$/, '');

/** Demo build. */
export const DEMO =
  import.meta.env.VITE_DEMO === '1' ||
  import.meta.env.VITE_DEMO === 'true';

/** No-login build. */
export const NO_LOGIN =
  import.meta.env.VITE_NO_LOGIN === '1' ||
  import.meta.env.VITE_NO_LOGIN === 'true';

/** Maximum bytes per sync request. */
export const SYNC_MAX_BATCH_BYTES = 1.5 * 1024 * 1024;

/** Background sync interval. */
export const SYNC_INTERVAL_MS = 2 * 60 * 1000;
