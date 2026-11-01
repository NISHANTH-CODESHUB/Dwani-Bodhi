/** Notification store: polled while the app is open and online, shared by the bell and nav badges. */
import { useSyncExternalStore } from 'react';
import { api } from './api';
import { getAuth } from './auth';
import type { NotificationList } from './types';

const POLL_MS = 60_000;
const EMPTY: NotificationList = { unread: 0, items: [] };

let state: NotificationList = EMPTY;
let owner: string | null = null; // account the state belongs to (cleared on logout / account switch)
const listeners = new Set<() => void>();

function set(next: NotificationList): void {
  state = next;
  listeners.forEach((l) => l());
}

export async function refreshNotifications(): Promise<void> {
  const auth = getAuth();
  if (!auth) {
    owner = null;
    set(EMPTY);
    return;
  }
  if (typeof navigator !== 'undefined' && !navigator.onLine) return;
  try {
    const res = await api.notifications();
    if (getAuth()?.user.id !== auth.user.id) return; // logged out / switched while in flight
    owner = auth.user.id;
    set(res);
  } catch {
    /* offline or server busy: keep the last list */
  }
}

export async function markRead(id: string): Promise<void> {
  set({
    unread: Math.max(0, state.unread - (state.items.some((n) => n.id === id && !n.read) ? 1 : 0)),
    items: state.items.map((n) => (n.id === id ? { ...n, read: true } : n)),
  });
  try {
    await api.readNotification(id);
  } catch {
    /* next refresh reconciles */
  }
}

export async function markAllRead(): Promise<void> {
  set({ unread: 0, items: state.items.map((n) => ({ ...n, read: true })) });
  try {
    set(await api.readAllNotifications());
  } catch {
    /* next refresh reconciles */
  }
}

let timer: number | null = null;

/** Starts polling once per page load; safe to call from every render path. */
export function startNotificationPolling(): void {
  if (timer !== null || typeof window === 'undefined') return;
  void refreshNotifications();
  timer = window.setInterval(() => void refreshNotifications(), POLL_MS);
  window.addEventListener('focus', () => void refreshNotifications());
  window.addEventListener('online', () => void refreshNotifications());
}

export function useNotifications(): NotificationList {
  const snap = useSyncExternalStore(
    (l) => {
      listeners.add(l);
      return () => listeners.delete(l);
    },
    () => state,
  );
  const me = getAuth()?.user.id ?? null;
  return owner === me ? snap : EMPTY;
}

/** Sign-up requests still waiting (unread) — the admin nav badge. */
export function pendingRequestCount(list: NotificationList): number {
  return list.items.filter((n) => n.kind === 'signup_request' && !n.read).length;
}
