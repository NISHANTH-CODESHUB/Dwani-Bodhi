/**
 * On-phone store (IndexedDB via Dexie). This is the ONLY place child names exist — they are never
 * included in any request. Everything captured in the kiosk/slate flows is written here first and
 * uploaded later by the sync engine.
 */
import Dexie, { type EntityTable } from 'dexie';
import type { ConsentStatus, Gender, SlateProblem } from './types';
import { uuid } from './uuid';

/** 0 = waiting to upload, 1 = uploaded, 2 = rejected by the server (kept for the teacher to see). */
export type SyncFlag = 0 | 1 | 2;

export interface LocalChild {
  id: string;
  classroom_id: string;
  name: string; // NEVER leaves the device
  grade: number;
  aruco_slot: number;
  /** Server-generated register number; null until the child has reached the server once. */
  register_no?: string | null;
  gender: Gender | null;
  consent_status: ConsentStatus;
  consent_date: string | null;
  dirty: 0 | 1; // needs POST to server
  deleted: 0 | 1; // needs DELETE on server, then removal
  sync_error: string | null;
  updated_at: string;
}

export interface LocalSession {
  id: string;
  child_id: string;
  classroom_id: string;
  plan_id: string | null;
  started_at: string;
  ended_at: string | null;
  discontinued: boolean;
  done: 0 | 1; // finished (or abandoned) → eligible for upload
  synced: SyncFlag;
  sync_error: string | null;
}

export interface LocalResponse {
  id: string;
  session_id: string;
  item_id: string;
  modality: 'voice' | 'tap';
  payload: Record<string, unknown>;
  created_at: string;
  has_audio: 0 | 1;
  synced: SyncFlag;
}

export interface MediaBlob {
  id: string; // response id or slate photo id
  blob: Blob;
  mime: string;
  size: number;
}

export interface LocalSlatePhoto {
  id: string;
  classroom_id: string;
  taken_at: string;
  problems: SlateProblem[];
  size: number;
  synced: SyncFlag;
  sync_error: string | null;
}

export interface KV {
  key: string;
  value: unknown;
  updated_at: string;
}

/**
 * v2 = teacher-only accounts with a fresh server database. The pre-v2 store held rosters and recordings
 * for classes that no longer exist on the server, so it is deleted once (the "fresh start").
 */
const DB_NAME = 'dhwani-bodhi-v2';
const LEGACY_DB_NAMES = ['dhwani-bodhi'];

if (typeof indexedDB !== 'undefined') {
  for (const name of LEGACY_DB_NAMES) void Dexie.delete(name).catch(() => undefined);
}

export class DhwaniDB extends Dexie {
  children!: EntityTable<LocalChild, 'id'>;
  sessions!: EntityTable<LocalSession, 'id'>;
  responses!: EntityTable<LocalResponse, 'id'>;
  audio!: EntityTable<MediaBlob, 'id'>;
  slatePhotos!: EntityTable<LocalSlatePhoto, 'id'>;
  images!: EntityTable<MediaBlob, 'id'>;
  kv!: EntityTable<KV, 'key'>;

  constructor() {
    super(DB_NAME);
    this.version(1).stores({
      children: 'id, classroom_id, aruco_slot, dirty, deleted',
      sessions: 'id, child_id, classroom_id, started_at, [done+synced]',
      responses: 'id, session_id, synced',
      audio: 'id',
      slatePhotos: 'id, classroom_id, taken_at, synced',
      images: 'id',
      kv: 'key',
    });
  }
}

export const db = new DhwaniDB();

// ------------------------------------------------------------------------------ key/value cache
export const KV_KEYS = {
  deviceId: 'device_id',
  bootstrap: 'bootstrap',
  today: (cid: string) => `today:${cid}`,
  card: (cid: string) => `card:${cid}`,
  overview: (cid: string) => `overview:${cid}`,
  unsureCount: (cid: string) => `unsure_count:${cid}`,
  profile: (childId: string) => `profile:${childId}`,
  plan: (childId: string) => `plan:${childId}`,
  explain: (childId: string) => `explain:${childId}`,
  lastSync: 'last_sync',
  classActivity: (cid: string) => `class_activity:${cid}`,
} as const;

export async function kvGet<T>(key: string): Promise<T | undefined> {
  const row = await db.kv.get(key);
  return row?.value as T | undefined;
}

export async function kvGetWithTime<T>(key: string): Promise<{ value: T; updated_at: string } | undefined> {
  const row = await db.kv.get(key);
  return row ? { value: row.value as T, updated_at: row.updated_at } : undefined;
}

export async function kvSet(key: string, value: unknown): Promise<void> {
  await db.kv.put({ key, value, updated_at: new Date().toISOString() });
}

export async function getDeviceId(): Promise<string> {
  const existing = await kvGet<string>(KV_KEYS.deviceId);
  if (existing) return existing;
  const id = uuid();
  await kvSet(KV_KEYS.deviceId, id);
  return id;
}

/** Display label for a child: local name, or the ID-card number when the name isn't on this phone. */
export function childLabel(c: Pick<LocalChild, 'name' | 'aruco_slot'> | undefined, fallbackSlot?: number): string {
  if (c && c.name.trim()) return c.name.trim();
  const slot = c?.aruco_slot ?? fallbackSlot;
  return slot === undefined ? 'Child' : `Child #${slot}`;
}

/** Sessions left open (app closed mid-session) for > 30 min are closed so they can be uploaded. */
export async function closeStaleSessions(now = Date.now()): Promise<void> {
  const open = await db.sessions.where('[done+synced]').equals([0, 0]).toArray();
  for (const s of open) {
    if (now - Date.parse(s.started_at) > 30 * 60_000) {
      await db.sessions.update(s.id, { done: 1, ended_at: s.ended_at ?? new Date(now).toISOString() });
    }
  }
}
