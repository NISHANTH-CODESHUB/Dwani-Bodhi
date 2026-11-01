/**
 * Offline-first sync engine. Triggers: `online` event, a periodic timer, app becoming visible, the
 * end of a kiosk session, and the teacher's "Sync now" button. Order of work:
 *   1. roster (child UUID/grade/slot/consent — never names) and deletions
 *   2. queued sessions/responses/audio + slate photos, in ≤5 MB batches, idempotent by UUID
 *   3. refresh caches: bootstrap (if version changed), today, card, unsure count, roster
 * Failures back off exponentially; permanent per-object errors are isolated and marked rejected.
 */
import { useSyncExternalStore } from 'react';
import { ApiError, api } from './api';
import { getAuth, setAuth, getClassroomId } from './auth';
import { SYNC_INTERVAL_MS, SYNC_MAX_BATCH_BYTES } from './config';
import { cachedContentVersion, loadContent, saveContent } from './content';
import { KV_KEYS, closeStaleSessions, db, getDeviceId, kvGet, kvSet, type MediaBlob } from './db';
import {
  backoffMs,
  buildManifest,
  audioToDelete,
  interpretResult,
  photoUnitBytes,
  planBatches,
  sessionUnitBytes,
  toChildOut,
  type PhotoBundle,
  type SessionBundle,
  type UploadUnit,
} from './sync-core';
import type { TodayResponse } from './types';

export interface SyncStatus {
  online: boolean;
  running: boolean;
  queued: number;
  rejected: number;
  lastSync: string | null;
  lastError: string | null;
  nextAttemptAt: number | null;
}

let status: SyncStatus = {
  online: typeof navigator === 'undefined' ? true : navigator.onLine,
  running: false,
  queued: 0,
  rejected: 0,
  lastSync: null,
  lastError: null,
  nextAttemptAt: null,
};
const listeners = new Set<() => void>();
let attempt = 0;

function setStatus(patch: Partial<SyncStatus>): void {
  status = { ...status, ...patch };
  listeners.forEach((l) => l());
}

export function useSyncStatus(): SyncStatus {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l);
      return () => listeners.delete(l);
    },
    () => status,
  );
}

/** Number of objects waiting for upload (finished sessions, slate photos, roster changes). */
export async function refreshQueueCount(): Promise<number> {
  const [sessions, photos, kids, rejS, rejP] = await Promise.all([
    db.sessions.where('[done+synced]').equals([1, 0]).count(),
    db.slatePhotos.where('synced').equals(0).count(),
    db.children.filter((c) => c.dirty === 1 || c.deleted === 1).count(),
    db.sessions.where('[done+synced]').equals([1, 2]).count(),
    db.slatePhotos.where('synced').equals(2).count(),
  ]);
  const queued = sessions + photos + kids;
  const last = await kvGet<string>(KV_KEYS.lastSync);
  setStatus({ queued, rejected: rejS + rejP, lastSync: last ?? null });
  return queued;
}

// --------------------------------------------------------------------------------- roster
function httpError(e: unknown): ApiError | null {
  return e instanceof ApiError && !e.retryable ? e : null;
}

/** Errors that should abort the whole run (no connectivity / not logged in) rather than one object. */
function isFatal(e: unknown): boolean {
  return !(e instanceof ApiError) || e.kind !== 'http' || e.status === 401 || e.status === 403;
}

/**
 * Roster first (sessions of a child can only be accepted once the server knows the child). A failure
 * on one child is recorded on that child and never blocks the rest of the queue.
 */
async function pushRoster(): Promise<void> {
  const deleted = await db.children.where('deleted').equals(1).toArray();
  for (const c of deleted) {
    try {
      await api.deleteChild(c.id);
    } catch (e) {
      const gone = e instanceof ApiError && e.kind === 'http' && (e.status === 404 || e.status === 403);
      if (!gone) {
        if (e instanceof ApiError && e.kind !== 'http') throw e;
        await db.children.update(c.id, { sync_error: e instanceof ApiError ? e.detail : String(e) });
        continue;
      }
    }
    await eraseChildLocally(c.id);
  }
  const dirty = await db.children.where('dirty').equals(1).toArray();
  for (const c of dirty) {
    if (c.deleted) continue;
    try {
      const saved = await api.upsertChild(c.classroom_id, toChildOut(c));
      if (saved.register_no && saved.register_no !== c.register_no) {
        await db.children.update(c.id, { register_no: saved.register_no }); // server-owned: always take it
      }
      // Clear the flag only if the teacher didn't edit the child while the request was in flight
      // (otherwise e.g. a consent change made during a slow 2G upload would never reach the server).
      await db.children
        .where('id')
        .equals(c.id)
        .and((now) => now.updated_at === c.updated_at)
        .modify({ dirty: 0, sync_error: null });
      if (c.consent_status === 'granted') await requeueSessions(c.id, 'consent');
    } catch (e) {
      if (isFatal(e)) throw e;
      const he = e as ApiError;
      if (he.status === 410) {
        await eraseChildLocally(c.id); // erased on the server (e.g. from another phone): erase here too
        continue;
      }
      const clash = he.status === 409 && /ID card/i.test(he.detail);
      await db.children.update(c.id, { sync_error: clash ? 'slot_clash' : `${he.status}: ${he.detail}` });
    }
  }
}

/**
 * Sessions the server rejected for a reason that has since been fixed (e.g. consent recorded later) go
 * back into the upload queue. Their recordings were kept on the phone for exactly this case.
 */
async function requeueSessions(childId: string, reasonPart: string): Promise<void> {
  const rejected = await db.sessions
    .where('child_id')
    .equals(childId)
    .filter((s) => s.synced === 2 && (s.sync_error ?? '').includes(reasonPart))
    .toArray();
  for (const s of rejected) {
    await db.sessions.update(s.id, { synced: 0, sync_error: null });
    await db.responses.where('session_id').equals(s.id).modify({ synced: 0 });
  }
}

/** Right to erasure on the phone: child record, sessions, responses and media. */
export async function eraseChildLocally(childId: string): Promise<void> {
  await db.transaction('rw', [db.children, db.sessions, db.responses, db.audio, db.kv], async () => {
    const sessions = await db.sessions.where('child_id').equals(childId).primaryKeys();
    for (const sid of sessions) {
      const rids = await db.responses.where('session_id').equals(sid).primaryKeys();
      await db.audio.bulkDelete(rids);
      await db.responses.bulkDelete(rids);
    }
    await db.sessions.bulkDelete(sessions);
    await db.kv.bulkDelete([KV_KEYS.profile(childId), KV_KEYS.plan(childId)]);
    await db.children.delete(childId);
  });
}

/** Merge the server roster into the local one (server children unknown here get an empty name). */
export async function pullRoster(classroomId: string): Promise<void> {
  const remote = await api.listChildren(classroomId);
  await db.transaction('rw', db.children, async () => {
    for (const r of remote) {
      const local = await db.children.get(r.id);
      if (!local) {
        await db.children.add({
          id: r.id,
          classroom_id: classroomId,
          name: '',
          grade: r.grade,
          aruco_slot: r.aruco_slot,
          register_no: r.register_no ?? null,
          gender: r.gender,
          consent_status: r.consent_status,
          consent_date: null,
          dirty: 0,
          deleted: 0,
          sync_error: null,
          updated_at: new Date().toISOString(),
        });
      } else {
        // The register number is assigned by the server and never edited here: take it even when dirty.
        if (r.register_no && r.register_no !== local.register_no) await db.children.update(r.id, { register_no: r.register_no });
      }
      if (local && !local.dirty && !local.deleted) {
        await db.children.update(r.id, {
          grade: r.grade,
          aruco_slot: r.aruco_slot,
          gender: r.gender,
          consent_status: r.consent_status,
        });
      }
    }
  });
}

// --------------------------------------------------------------------------------- uploads
async function collectUnits(): Promise<UploadUnit[]> {
  const units: UploadUnit[] = [];
  const sessions = await db.sessions.where('[done+synced]').equals([1, 0]).sortBy('started_at');
  for (const s of sessions) {
    const child = await db.children.get(s.child_id);
    if (child && (child.dirty || child.deleted)) continue; // roster must reach the server first
    const responses = await db.responses.where('session_id').equals(s.id).toArray();
    const audio = await db.audio.bulkGet(responses.map((r) => r.id));
    const sizes = audio.filter((a): a is MediaBlob => !!a).map((a) => a.size);
    units.push({ kind: 'session', id: s.id, bytes: sessionUnitBytes(responses, sizes) });
  }
  const photos = await db.slatePhotos.where('synced').equals(0).sortBy('taken_at');
  for (const p of photos) units.push({ kind: 'photo', id: p.id, bytes: photoUnitBytes(p.size) });
  return units;
}

async function loadBundles(batch: UploadUnit[]): Promise<{ sessions: SessionBundle[]; photos: PhotoBundle[] }> {
  const sessions: SessionBundle[] = [];
  const photos: PhotoBundle[] = [];
  for (const u of batch) {
    if (u.kind === 'session') {
      const session = await db.sessions.get(u.id);
      if (!session) continue;
      const responses = await db.responses.where('session_id').equals(u.id).sortBy('created_at');
      const blobs = await db.audio.bulkGet(responses.map((r) => r.id));
      const audio = new Map<string, MediaBlob>();
      blobs.forEach((b) => b && audio.set(b.id, b));
      sessions.push({ session, responses, audio });
    } else {
      const photo = await db.slatePhotos.get(u.id);
      if (!photo) continue;
      photos.push({ photo, image: await db.images.get(u.id) });
    }
  }
  return { sessions, photos };
}

async function markRejected(u: UploadUnit, reason: string): Promise<void> {
  if (u.kind === 'session') {
    await db.sessions.update(u.id, { synced: 2, sync_error: reason });
    await db.responses.where('session_id').equals(u.id).modify({ synced: 2 });
  } else {
    await db.slatePhotos.update(u.id, { synced: 2, sync_error: reason });
  }
}

/** Server jobs still queued after the last upload (serverless deploys score inside requests). */
let pendingJobs = 0;

async function uploadBatch(deviceId: string, batch: UploadUnit[]): Promise<void> {
  const { sessions, photos } = await loadBundles(batch);
  for (const p of photos) if (!p.image) await markRejected({ kind: 'photo', id: p.photo.id, bytes: 0 }, 'image missing');
  const { manifest, parts } = buildManifest(deviceId, sessions, photos);
  if (manifest.sessions.length === 0 && manifest.slate_photos.length === 0) return;
  const form = new FormData();
  form.append('manifest', JSON.stringify(manifest));
  for (const p of parts) form.append(p.name, p.blob, p.filename);
  const bytes = parts.reduce((n, p) => n + p.blob.size, 0);
  const result = await api.sync(form, bytes);
  pendingJobs = result.jobs?.pending ?? 0;
  const o = interpretResult(manifest, result);
  const dropAudio = audioToDelete(manifest, o);
  await db.transaction('rw', [db.sessions, db.responses, db.audio, db.slatePhotos, db.images], async () => {
    await db.responses.bulkUpdate(o.responsesSynced.map((key) => ({ key, changes: { synced: 1 as const } })));
    await db.responses.bulkUpdate(o.responsesRejected.map((key) => ({ key, changes: { synced: 2 as const } })));
    // Raw audio and photos leave the phone once the server has them (data minimisation + storage).
    await db.audio.bulkDelete(dropAudio);
    await db.sessions.bulkUpdate(o.sessionsSynced.map((key) => ({ key, changes: { synced: 1 as const, sync_error: null } })));
    for (const r of o.sessionsRejected) await db.sessions.update(r.id, { synced: 2, sync_error: r.reason });
    await db.slatePhotos.bulkUpdate(o.photosSynced.map((key) => ({ key, changes: { synced: 1 as const, sync_error: null } })));
    for (const r of o.photosRejected) await db.slatePhotos.update(r.id, { synced: 2, sync_error: r.reason });
    await db.images.bulkDelete([...o.photosSynced, ...o.photosRejected.map((r) => r.id)]);
  });
  if (result.content_version && result.content_version !== cachedContentVersion()) {
    serverContentVersion = result.content_version;
  }
}

async function uploadAll(): Promise<void> {
  const deviceId = await getDeviceId();
  const queue = planBatches(await collectUnits(), SYNC_MAX_BATCH_BYTES);
  while (queue.length) {
    const batch = queue.shift()!;
    try {
      await uploadBatch(deviceId, batch);
    } catch (e) {
      const he = httpError(e);
      if (!he || he.status === 401 || he.status === 403) throw e;
      // Permanent error: isolate the bad object by retrying one by one, then reject it alone.
      if (batch.length > 1) queue.unshift(...batch.map((u) => [u]));
      else await markRejected(batch[0], `${he.status}: ${he.detail}`);
    }
  }
}

/**
 * Serverless deploys have no background worker: ask the server to finish queued scoring so today's list,
 * profiles and the review queue are up to date right after a sync. Stops when nothing is left or no
 * progress is made; anything remaining is finished by the next sync or the daily cron.
 */
async function pumpJobs(): Promise<void> {
  for (let i = 0; i < 4 && pendingJobs > 0; i += 1) {
    const r = await api.runJobs();
    pendingJobs = r.pending;
    if (r.ran === 0) break;
  }
}

// --------------------------------------------------------------------------------- refresh
let serverContentVersion: string | null = null;

export async function refreshBootstrap(force = false): Promise<void> {
  await loadContent();
  const have = cachedContentVersion();
  if (!force && have && (serverContentVersion === null || serverContentVersion === have)) return;
  await saveContent(await api.bootstrap());
  serverContentVersion = null;
}

/** Pulls today's plan/list, roster, unsure count and (best effort) the Action Card for a classroom. */
export async function refreshClassroom(cid: string): Promise<void> {
  const today: TodayResponse = await api.today(cid);
  await kvSet(KV_KEYS.today(cid), today);
  for (const c of today.children) if (c.plan && c.plan.items?.length) await kvSet(KV_KEYS.plan(c.child_id), c.plan);
  await pullRoster(cid);
  try {
    const unsure = await api.unsure(cid);
    await kvSet(KV_KEYS.unsureCount(cid), unsure.length);
  } catch {
    /* non-critical */
  }
  try {
    await kvSet(KV_KEYS.overview(cid), await api.overview(cid));
  } catch {
    /* dashboard keeps the cached overview */
  }
  try {
    await kvSet(KV_KEYS.card(cid), await api.card(cid));
  } catch {
    /* card generation can be slow; the cached card stays */
  }
}

// ------------------------------------------------------------------------------------ run
let inFlight: Promise<boolean> | null = null;

/** Runs one full sync. Returns true on success. Concurrent calls share the same run. */
export function runSync(opts: { manual?: boolean } = {}): Promise<boolean> {
  if (inFlight) return inFlight;
  inFlight = doSync(!!opts.manual).finally(() => {
    inFlight = null;
  });
  return inFlight;
}

async function doSync(manual: boolean): Promise<boolean> {
  const auth = getAuth();
  if (!auth) return false;
  if (!manual && typeof navigator !== 'undefined' && !navigator.onLine) return false;
  setStatus({ running: true, lastError: null });
  try {
    // Refresh the account: classrooms may have been reassigned (setAuth drops a classroom that no
    // longer belongs to this teacher and falls back to the picker; a deleted account gets a 401 → logout).
    const me = await api.me();
    // The teacher may have logged out or changed the PIN while /me was in flight: never write an old
    // token back (that would silently log a shared phone in again, or restore a revoked token).
    const live = getAuth();
    if (!live || live.token !== auth.token) {
      setStatus({ running: false });
      return false;
    }
    setAuth({ ...live, user: me.user, classrooms: me.classrooms });
    if (me.content_version && me.content_version !== cachedContentVersion()) serverContentVersion = me.content_version;
    await closeStaleSessions();
    await pushRoster();
    await uploadAll();
    try {
      await pumpJobs();
    } catch {
      /* best effort: results arrive with a later sync */
    }
    await refreshBootstrap();
    const cid = getClassroomId();
    if (cid) await refreshClassroom(cid);
    const now = new Date().toISOString();
    await kvSet(KV_KEYS.lastSync, now);
    attempt = 0;
    setStatus({ running: false, lastSync: now, nextAttemptAt: null, online: true });
    await refreshQueueCount();
    return true;
  } catch (e) {
    attempt += 1;
    const wait = backoffMs(attempt);
    const offline = e instanceof ApiError && (e.kind === 'network' || e.kind === 'timeout');
    setStatus({
      running: false,
      lastError: e instanceof ApiError ? e.kind === 'http' ? `http_${e.status}` : e.kind : 'unknown',
      nextAttemptAt: Date.now() + wait,
      online: offline ? false : status.online,
    });
    await refreshQueueCount();
    return false;
  }
}

/** Soft trigger (e.g. after a kiosk session): runs now if online and not backing off. */
export function requestSync(): void {
  void refreshQueueCount();
  if (status.nextAttemptAt && Date.now() < status.nextAttemptAt) return;
  void runSync();
}

let started = false;

export function startSyncLoop(): void {
  if (started || typeof window === 'undefined') return;
  started = true;
  window.addEventListener('online', () => {
    attempt = 0;
    setStatus({ online: true, nextAttemptAt: null });
    void runSync();
  });
  window.addEventListener('offline', () => setStatus({ online: false }));
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') requestSync();
  });
  setInterval(() => {
    if (!navigator.onLine) return;
    if (status.nextAttemptAt && Date.now() < status.nextAttemptAt) return;
    const stale = !status.lastSync || Date.now() - Date.parse(status.lastSync) > 30 * 60_000;
    if (status.queued > 0 || stale) void runSync();
  }, SYNC_INTERVAL_MS);
  void refreshQueueCount().then(() => runSync());
}
