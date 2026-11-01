/** Kiosk persistence: every response (and its audio) is written to IndexedDB the moment it exists. */
import { db, type LocalSession } from '../lib/db';
import { uuid } from '../lib/uuid';

export async function createSession(childId: string, classroomId: string, planId: string | null): Promise<string> {
  const s: LocalSession = {
    id: uuid(),
    child_id: childId,
    classroom_id: classroomId,
    plan_id: planId,
    started_at: new Date().toISOString(),
    ended_at: null,
    discontinued: false,
    done: 0,
    synced: 0,
    sync_error: null,
  };
  await db.sessions.add(s);
  return s.id;
}

export async function finishSession(id: string, discontinued: boolean): Promise<void> {
  await db.sessions.update(id, { done: 1, ended_at: new Date().toISOString(), discontinued });
}

export async function saveResponse(opts: {
  sessionId: string;
  itemId: string;
  modality: 'voice' | 'tap';
  payload: Record<string, unknown>;
  audio?: { blob: Blob; mime: string };
}): Promise<string> {
  const id = uuid();
  await db.transaction('rw', db.sessions, db.responses, db.audio, async () => {
    // The session may have been auto-closed and uploaded while the child sat on one question: put it back
    // in the queue so this answer is uploaded too (the server treats the session itself as a duplicate).
    const session = await db.sessions.get(opts.sessionId);
    if (session && session.synced !== 0) await db.sessions.update(opts.sessionId, { synced: 0, sync_error: null });
    await db.responses.add({
      id,
      session_id: opts.sessionId,
      item_id: opts.itemId,
      modality: opts.modality,
      payload: opts.payload,
      created_at: new Date().toISOString(),
      has_audio: opts.audio ? 1 : 0,
      synced: 0,
    });
    if (opts.audio) {
      await db.audio.add({ id, blob: opts.audio.blob, mime: opts.audio.mime, size: opts.audio.blob.size });
    }
  });
  return id;
}
