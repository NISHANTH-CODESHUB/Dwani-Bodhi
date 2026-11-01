/** Login state kept in localStorage (tiny, synchronous; needed before IndexedDB opens). */
import { useSyncExternalStore } from 'react';
import type { ClassroomInfo, User } from './types';

// v2: teacher-only accounts (fresh start). Older keys are removed on load.
const KEY = 'db.auth.v2';
const ROOM_KEY = 'db.classroom.v2';
const LEGACY_KEYS = ['db.auth.v1', 'db.classroom.v1'];

if (typeof localStorage !== 'undefined') for (const k of LEGACY_KEYS) localStorage.removeItem(k);

export interface AuthState {
  token: string;
  user: User;
  classrooms: ClassroomInfo[];
}

type Listener = () => void;
const listeners = new Set<Listener>();

function read(): AuthState | null {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as AuthState) : null;
  } catch {
    return null;
  }
}

let current: AuthState | null = typeof localStorage === 'undefined' ? null : read();
let currentRoom: string | null = typeof localStorage === 'undefined' ? null : localStorage.getItem(ROOM_KEY);

function emit(): void {
  listeners.forEach((l) => l());
}

export function getAuth(): AuthState | null {
  return current;
}

export function getToken(): string | null {
  return current?.token ?? null;
}

export function setAuth(a: AuthState): void {
  current = a;
  localStorage.setItem(KEY, JSON.stringify(a));
  if (!currentRoom || !a.classrooms.some((c) => c.id === currentRoom)) {
    setClassroom(a.classrooms.length === 1 ? a.classrooms[0].id : null);
  }
  emit();
}

/** Clears the token only. Local data (roster names, queued sessions) stays on the teacher's phone. */
export function logout(): void {
  current = null;
  localStorage.removeItem(KEY);
  emit();
}

export function getClassroomId(): string | null {
  return currentRoom;
}

export function setClassroom(id: string | null): void {
  currentRoom = id;
  if (id) localStorage.setItem(ROOM_KEY, id);
  else localStorage.removeItem(ROOM_KEY);
  emit();
}

function subscribe(l: Listener): () => void {
  listeners.add(l);
  return () => listeners.delete(l);
}

export function useAuth(): AuthState | null {
  return useSyncExternalStore(subscribe, getAuth);
}

export function useClassroom(): ClassroomInfo | null {
  const auth = useAuth();
  const id = useSyncExternalStore(subscribe, getClassroomId);
  return auth?.classrooms.find((c) => c.id === id) ?? null;
}
