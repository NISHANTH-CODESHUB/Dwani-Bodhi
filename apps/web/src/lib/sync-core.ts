/**
 * Pure (I/O-free) parts of the sync engine: batching, manifest building, result interpretation and
 * backoff. Kept separate so they are unit-testable without IndexedDB or network.
 */
import type { LocalChild, LocalResponse, LocalSession, LocalSlatePhoto, MediaBlob } from './db';
import type { ChildOut, SyncManifest, SyncResult, SyncSessionIn, SyncSlatePhotoIn } from './types';

/** Rough JSON size of the manifest entries (bytes), used to keep each request under the cap. */
const SESSION_JSON_BYTES = 400;
const RESPONSE_JSON_BYTES = 300;
const PHOTO_JSON_BYTES = 400;

export interface SessionBundle {
  session: LocalSession;
  responses: LocalResponse[];
  /** audio blobs keyed by response id (may be missing for tap responses or simulated voice) */
  audio: Map<string, MediaBlob>;
}

export interface PhotoBundle {
  photo: LocalSlatePhoto;
  image: MediaBlob | undefined;
}

export type UploadUnit =
  | { kind: 'session'; id: string; bytes: number }
  | { kind: 'photo'; id: string; bytes: number };

export function sessionUnitBytes(responses: Pick<LocalResponse, 'id'>[], audioSizes: number[]): number {
  return SESSION_JSON_BYTES + responses.length * RESPONSE_JSON_BYTES + audioSizes.reduce((a, b) => a + b, 0);
}

export function photoUnitBytes(imageSize: number): number {
  return PHOTO_JSON_BYTES + imageSize;
}

/**
 * Greedy, order-preserving packing of upload units into batches of at most `maxBytes`.
 * A unit larger than the cap still goes alone in its own batch (the server enforces per-file limits).
 * `maxUnits` bounds the number of objects per request so one bad object can't stall a huge batch.
 */
export function planBatches<T extends { bytes: number }>(units: T[], maxBytes: number, maxUnits = 25): T[][] {
  const batches: T[][] = [];
  let cur: T[] = [];
  let curBytes = 0;
  for (const u of units) {
    const fitsBytes = curBytes + u.bytes <= maxBytes;
    if (cur.length > 0 && (!fitsBytes || cur.length >= maxUnits)) {
      batches.push(cur);
      cur = [];
      curBytes = 0;
    }
    cur.push(u);
    curBytes += u.bytes;
  }
  if (cur.length) batches.push(cur);
  return batches;
}

export interface FilePart {
  name: string;
  blob: Blob;
  filename: string;
}

export function extForMime(mime: string): string {
  const m = mime.split(';')[0].trim().toLowerCase();
  const map: Record<string, string> = {
    'audio/webm': 'webm',
    'audio/ogg': 'ogg',
    'audio/mp4': 'm4a',
    'audio/aac': 'aac',
    'audio/mpeg': 'mp3',
    'audio/wav': 'wav',
    'audio/x-wav': 'wav',
    'image/jpeg': 'jpg',
    'image/png': 'png',
    'image/webp': 'webp',
  };
  return map[m] ?? 'bin';
}

export const audioPartName = (responseId: string): string => `a_${responseId}`;
export const imagePartName = (photoId: string): string => `i_${photoId}`;

/** Builds the `manifest` JSON plus the file parts for one /v1/sync request. No names, only UUIDs. */
export function buildManifest(
  deviceId: string,
  sessions: SessionBundle[],
  photos: PhotoBundle[],
): { manifest: SyncManifest; parts: FilePart[] } {
  const parts: FilePart[] = [];
  const sessionsIn: SyncSessionIn[] = sessions.map(({ session, responses, audio }) => ({
    id: session.id,
    child_id: session.child_id,
    classroom_id: session.classroom_id,
    started_at: session.started_at,
    ended_at: session.ended_at,
    plan_id: session.plan_id,
    discontinued: session.discontinued,
    responses: responses.map((r) => {
      const blob = r.modality === 'voice' ? audio.get(r.id) : undefined;
      let audio_part: string | null = null;
      if (blob) {
        audio_part = audioPartName(r.id);
        parts.push({ name: audio_part, blob: blob.blob, filename: `${r.id}.${extForMime(blob.mime)}` });
      }
      return {
        id: r.id,
        item_id: r.item_id,
        modality: r.modality,
        payload: r.payload,
        created_at: r.created_at,
        audio_part,
      };
    }),
  }));
  const photosIn: SyncSlatePhotoIn[] = [];
  for (const { photo, image } of photos) {
    if (!image) continue; // nothing to upload; caller marks it as rejected locally
    const image_part = imagePartName(photo.id);
    parts.push({ name: image_part, blob: image.blob, filename: `${photo.id}.${extForMime(image.mime)}` });
    photosIn.push({
      id: photo.id,
      classroom_id: photo.classroom_id,
      taken_at: photo.taken_at,
      problems: photo.problems.map(({ item_id, a, b, op }) => ({ item_id, a, b, op })),
      image_part,
    });
  }
  return { manifest: { device_id: deviceId, sessions: sessionsIn, slate_photos: photosIn }, parts };
}

export interface SyncOutcome {
  sessionsSynced: string[];
  sessionsRejected: { id: string; reason: string }[];
  responsesSynced: string[];
  responsesRejected: string[];
  photosSynced: string[];
  photosRejected: { id: string; reason: string }[];
  /** objects the server didn't mention — stay queued */
  pending: string[];
}

/**
 * Maps the server's accepted/duplicates/rejected lists back onto what we sent. A session counts as
 * synced once the server knows it (accepted now, or not rejected) and every response is resolved.
 */
export function interpretResult(manifest: SyncManifest, result: SyncResult): SyncOutcome {
  const ok = new Set<string>([
    ...result.accepted.sessions,
    ...result.accepted.responses,
    ...result.accepted.slate_photos,
    ...result.duplicates,
  ]);
  const rejected = new Map(result.rejected.map((r) => [r.id, r.reason]));
  const out: SyncOutcome = {
    sessionsSynced: [],
    sessionsRejected: [],
    responsesSynced: [],
    responsesRejected: [],
    photosSynced: [],
    photosRejected: [],
    pending: [],
  };
  for (const s of manifest.sessions) {
    const reason = rejected.get(s.id);
    if (reason !== undefined) {
      out.sessionsRejected.push({ id: s.id, reason });
      out.responsesRejected.push(...s.responses.map((r) => r.id));
      continue;
    }
    let allResolved = true;
    for (const r of s.responses) {
      if (ok.has(r.id)) out.responsesSynced.push(r.id);
      else if (rejected.has(r.id)) out.responsesRejected.push(r.id);
      else {
        allResolved = false;
        out.pending.push(r.id);
      }
    }
    if (allResolved) out.sessionsSynced.push(s.id);
    else out.pending.push(s.id);
  }
  for (const p of manifest.slate_photos) {
    const reason = rejected.get(p.id);
    if (ok.has(p.id)) out.photosSynced.push(p.id);
    else if (reason !== undefined) out.photosRejected.push({ id: p.id, reason });
    else out.pending.push(p.id);
  }
  return out;
}

/**
 * Recordings that may leave the phone after a sync: those the server now has, and those it refused on
 * their own (bad file, unknown item). Responses of a *session* the server refused (no consent recorded
 * yet, no access) keep their audio, because that session is re-queued once the cause is fixed.
 */
export function audioToDelete(manifest: SyncManifest, o: SyncOutcome): string[] {
  const refusedSessions = new Set(o.sessionsRejected.map((r) => r.id));
  const keep = new Set(manifest.sessions.filter((s) => refusedSessions.has(s.id)).flatMap((s) => s.responses.map((r) => r.id)));
  return [...o.responsesSynced, ...o.responsesRejected.filter((id) => !keep.has(id))];
}

/** Exponential backoff with full jitter: 15 s, 30 s, 60 s … capped at 30 min. */
export function backoffMs(attempt: number, rand: () => number = Math.random, baseMs = 15_000, maxMs = 30 * 60_000): number {
  if (attempt <= 0) return 0;
  const ceiling = Math.min(maxMs, baseMs * 2 ** (attempt - 1));
  return Math.round(ceiling / 2 + (rand() * ceiling) / 2);
}

/** Roster payload for the server. Deliberately field-by-field: the child's name must never be serialised. */
export function toChildOut(c: LocalChild): ChildOut {
  return { id: c.id, grade: c.grade, aruco_slot: c.aruco_slot, gender: c.gender, consent_status: c.consent_status };
}
