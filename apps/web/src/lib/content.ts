/** Cached content pack (from GET /v1/bootstrap), kept in IndexedDB for offline kiosk sessions. */
import { useEffect, useState } from 'react';
import { KV_KEYS, kvGet, kvSet } from './db';
import type { Bootstrap, Item } from './types';

export interface Content {
  bootstrap: Bootstrap;
  items: Map<string, Item>;
  rungName: (domain: string | null, rungId: string) => string;
}

let cached: Content | null = null;
let loading: Promise<Content | null> | null = null;
const listeners = new Set<() => void>();

const SPECIAL_RUNGS: Record<string, string> = {
  beginner: 'Beginner',
  unassessed: 'Not checked yet',
};

function wrap(b: Bootstrap): Content {
  const items = new Map(b.items.map((i) => [i.id, i]));
  const names = new Map<string, string>();
  for (const [dom, rungs] of Object.entries(b.ladders)) {
    for (const r of rungs) {
      names.set(`${dom}:${r.id}`, r.name_hi);
      if (!names.has(r.id)) names.set(r.id, r.name_hi);
    }
  }
  return {
    bootstrap: b,
    items,
    rungName: (domain, rungId) =>
      SPECIAL_RUNGS[rungId] ?? names.get(domain ? `${domain}:${rungId}` : rungId) ?? names.get(rungId) ?? rungId,
  };
}

export async function loadContent(): Promise<Content | null> {
  if (cached) return cached;
  loading ??= kvGet<Bootstrap>(KV_KEYS.bootstrap).then((b) => {
    cached = b ? wrap(b) : null;
    loading = null;
    return cached;
  });
  return loading;
}

export async function saveContent(b: Bootstrap): Promise<void> {
  await kvSet(KV_KEYS.bootstrap, b);
  cached = wrap(b);
  listeners.forEach((l) => l());
}

export function cachedContentVersion(): string | null {
  return cached?.bootstrap.version ?? null;
}

/** React hook: the cached content pack, or null while loading / when never downloaded. */
export function useContent(): Content | null {
  const [c, setC] = useState<Content | null>(cached);
  useEffect(() => {
    let alive = true;
    const update = () => {
      void loadContent().then((v) => alive && setC(v));
    };
    update();
    listeners.add(update);
    return () => {
      alive = false;
      listeners.delete(update);
    };
  }, []);
  return c;
}
