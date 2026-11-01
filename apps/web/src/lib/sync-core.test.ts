import { describe, expect, it } from 'vitest';
import type { LocalResponse, LocalSession, LocalSlatePhoto, MediaBlob } from './db';
import {
  audioToDelete,
  backoffMs,
  buildManifest,
  extForMime,
  interpretResult,
  planBatches,
  sessionUnitBytes,
  toChildOut,
  type SessionBundle,
} from './sync-core';

const MB = 1024 * 1024;

function session(id: string, over: Partial<LocalSession> = {}): LocalSession {
  return {
    id,
    child_id: `child-${id}`,
    classroom_id: 'room-1',
    plan_id: 'plan-1',
    started_at: '2026-10-17T09:00:00.000Z',
    ended_at: '2026-10-17T09:03:00.000Z',
    discontinued: false,
    done: 1,
    synced: 0,
    sync_error: null,
    ...over,
  };
}

function resp(id: string, sessionId: string, modality: 'voice' | 'tap', payload: Record<string, unknown> = {}): LocalResponse {
  return { id, session_id: sessionId, item_id: `item-${id}`, modality, payload, created_at: '2026-10-17T09:01:00.000Z', has_audio: modality === 'voice' ? 1 : 0, synced: 0 };
}

const blob = (id: string, size: number, mime = 'audio/webm;codecs=opus'): MediaBlob => ({ id, blob: new Blob([new Uint8Array(size)], { type: mime }), mime, size });

describe('planBatches', () => {
  it('packs units greedily under the byte cap, preserving order', () => {
    const units = [1, 2, 1.5, 0.5, 3, 4.5].map((m, i) => ({ id: `u${i}`, bytes: m * MB }));
    const b = planBatches(units, 5 * MB);
    expect(b.map((x) => x.map((u) => u.id))).toEqual([['u0', 'u1', 'u2', 'u3'], ['u4'], ['u5']]);
    for (const batch of b) expect(batch.reduce((a, u) => a + u.bytes, 0)).toBeLessThanOrEqual(5 * MB);
  });

  it('puts an oversized unit alone instead of dropping it', () => {
    const b = planBatches([{ bytes: 100 }, { bytes: 9 * MB }, { bytes: 100 }], 5 * MB);
    expect(b.map((x) => x.length)).toEqual([1, 1, 1]);
  });

  it('limits the number of objects per batch', () => {
    const units = Array.from({ length: 60 }, () => ({ bytes: 10 }));
    expect(planBatches(units, 5 * MB, 25).map((x) => x.length)).toEqual([25, 25, 10]);
  });

  it('handles empty input', () => {
    expect(planBatches([], 5 * MB)).toEqual([]);
  });
});

describe('buildManifest', () => {
  it('builds the /v1/sync manifest with file parts named by audio_part/image_part', () => {
    const s = session('s1', { discontinued: true });
    const r1 = resp('r1', 's1', 'voice', { duration_ms: 2100 });
    const r2 = resp('r2', 's1', 'tap', { chosen: '47' });
    const r3 = resp('r3', 's1', 'voice', { simulated_utterance: 'नदि' }); // demo: no audio
    const bundle: SessionBundle = { session: s, responses: [r1, r2, r3], audio: new Map([['r1', blob('r1', 2000)]]) };
    const photo: LocalSlatePhoto = {
      id: 'p1',
      classroom_id: 'room-1',
      taken_at: '2026-10-17T10:00:00.000Z',
      problems: [{ item_id: 'm.slate.x', a: 52, b: 19, op: '-', skills: ['M9'] }],
      size: 1000,
      synced: 0,
      sync_error: null,
    };
    const { manifest, parts } = buildManifest('dev-1', [bundle], [{ photo, image: blob('p1', 1000, 'image/jpeg') }]);
    expect(manifest.device_id).toBe('dev-1');
    expect(manifest.sessions).toHaveLength(1);
    const ms = manifest.sessions[0];
    expect(ms).toMatchObject({ id: 's1', child_id: 'child-s1', classroom_id: 'room-1', plan_id: 'plan-1', discontinued: true });
    expect(ms.responses.map((r) => r.audio_part)).toEqual(['a_r1', null, null]);
    expect(ms.responses[1]).toMatchObject({ modality: 'tap', payload: { chosen: '47' } });
    expect(ms.responses[2].payload).toEqual({ simulated_utterance: 'नदि' });
    expect(manifest.slate_photos).toEqual([
      { id: 'p1', classroom_id: 'room-1', taken_at: '2026-10-17T10:00:00.000Z', problems: [{ item_id: 'm.slate.x', a: 52, b: 19, op: '-' }], image_part: 'i_p1' },
    ]);
    expect(parts.map((p) => [p.name, p.filename])).toEqual([
      ['a_r1', 'r1.webm'],
      ['i_p1', 'p1.jpg'],
    ]);
    // privacy: nothing that looks like a name field
    expect(JSON.stringify(manifest)).not.toMatch(/"name"/);
  });

  it('skips photos whose image blob is missing', () => {
    const photo = { id: 'p2', classroom_id: 'r', taken_at: 't', problems: [], size: 0, synced: 0 as const, sync_error: null };
    const { manifest, parts } = buildManifest('d', [], [{ photo, image: undefined }]);
    expect(manifest.slate_photos).toEqual([]);
    expect(parts).toEqual([]);
  });

  it('estimates unit bytes from audio sizes', () => {
    expect(sessionUnitBytes([{ id: 'a' }, { id: 'b' }], [1000, 2000])).toBe(400 + 600 + 3000);
  });

  it('maps mime types to extensions', () => {
    expect(extForMime('audio/webm;codecs=opus')).toBe('webm');
    expect(extForMime('audio/mp4')).toBe('m4a');
    expect(extForMime('image/webp')).toBe('webp');
    expect(extForMime('x/unknown')).toBe('bin');
  });
});

describe('interpretResult', () => {
  const s1 = { ...session('s1'), responses: [] };
  const manifest = {
    device_id: 'd',
    sessions: [
      { ...s1, id: 's1', responses: [{ id: 'r1' }, { id: 'r2' }] },
      { ...s1, id: 's2', responses: [{ id: 'r3' }] },
      { ...s1, id: 's3', responses: [{ id: 'r4' }, { id: 'r5' }] },
    ].map((s) => ({ ...s, responses: s.responses.map((r) => ({ ...r, item_id: 'i', modality: 'tap' as const, payload: {}, created_at: 't' })) })),
    slate_photos: [
      { id: 'p1', classroom_id: 'r', taken_at: 't', problems: [], image_part: 'i_p1' },
      { id: 'p2', classroom_id: 'r', taken_at: 't', problems: [], image_part: 'i_p2' },
    ],
  };

  it('marks accepted and duplicate objects as synced, rejected ones as rejected', () => {
    const o = interpretResult(manifest, {
      // s1 was uploaded before (retry after a dropped connection): its responses come back as duplicates
      accepted: { sessions: ['s3'], responses: ['r4'], slate_photos: ['p1'] },
      duplicates: ['r1', 'r2', 'p2'],
      rejected: [
        { id: 's2', reason: 'no parental consent recorded' },
        { id: 'r5', reason: 'unknown item x' },
      ],
      content_version: 'v2',
    });
    expect(o.sessionsSynced).toEqual(['s1', 's3']);
    expect(o.sessionsRejected).toEqual([{ id: 's2', reason: 'no parental consent recorded' }]);
    expect(o.responsesSynced).toEqual(['r1', 'r2', 'r4']);
    expect(o.responsesRejected.sort()).toEqual(['r3', 'r5']);
    expect(o.photosSynced).toEqual(['p1', 'p2']);
    expect(o.pending).toEqual([]);
  });

  it('keeps the audio of a refused session (re-queued once consent is recorded), drops the rest', () => {
    const o = interpretResult(manifest, {
      accepted: { sessions: ['s3'], responses: ['r4'], slate_photos: [] },
      duplicates: ['r1', 'r2'],
      rejected: [
        { id: 's2', reason: 'no parental consent recorded' },
        { id: 'r5', reason: 'unsupported media type audio/3gpp' },
      ],
      content_version: 'v2',
    });
    expect(audioToDelete(manifest, o).sort()).toEqual(['r1', 'r2', 'r4', 'r5']); // r3 (session s2) is kept
  });

  it('keeps objects the server did not mention queued', () => {
    const o = interpretResult(manifest, {
      accepted: { sessions: ['s1'], responses: ['r1'], slate_photos: [] },
      duplicates: [],
      rejected: [],
      content_version: 'v1',
    });
    expect(o.sessionsSynced).toEqual([]);
    expect(o.pending).toEqual(expect.arrayContaining(['r2', 's1', 'r3', 's2', 'p1', 'p2']));
  });
});

describe('backoffMs', () => {
  it('grows exponentially with jitter and is capped', () => {
    expect(backoffMs(0)).toBe(0);
    expect(backoffMs(1, () => 0)).toBe(7_500);
    expect(backoffMs(1, () => 1)).toBe(15_000);
    expect(backoffMs(3, () => 1)).toBe(60_000);
    expect(backoffMs(30, () => 1)).toBe(30 * 60_000);
  });
});

describe('toChildOut', () => {
  it('never includes the child name', () => {
    const out = toChildOut({
      id: '11111111-1111-4111-8111-111111111111',
      classroom_id: 'room',
      name: 'रानी कुमारी',
      grade: 2,
      aruco_slot: 7,
      gender: 'f',
      consent_status: 'granted',
      consent_date: null,
      dirty: 1,
      deleted: 0,
      sync_error: null,
      updated_at: 't',
    });
    expect(out).toEqual({ id: '11111111-1111-4111-8111-111111111111', grade: 2, aruco_slot: 7, gender: 'f', consent_status: 'granted' });
    expect(JSON.stringify(out)).not.toContain('रानी');
  });
});
