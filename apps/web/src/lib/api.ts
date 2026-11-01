/** Thin typed client for the Dhwani-Bodhi REST API (services/api). Never sends child names. */
import { API_BASE } from './config';
import { getToken, logout } from './auth';
import type {
  AdminDashboard,
  AdminStudentPage,
  AppNotification,
  ClassActivity,
  ConsentStatus,
  NotificationList,
  StudentActivity,
  StudentFilter,
  StudentRow,
  TeacherRow,
  AdminClassroom,
  AdminUser,
  NewUserBody,
  SignupBody,
  Approver,
  SignupOptions,
  OrgKind,
  OrgUnitOut,
  SchoolOut,
  Bootstrap,
  CardResponse,
  ChildOut,
  ChildProfile,
  ConfirmBody,
  Explanation,
  LoginResponse,
  PinChangeBody,
  MeResponse,
  Overview,
  SessionPlan,
  SyncResult,
  TodayResponse,
  UnsureEntry,
} from './types';

export type ApiErrorKind = 'network' | 'timeout' | 'http';

export class ApiError extends Error {
  constructor(
    public readonly kind: ApiErrorKind,
    public readonly status: number,
    public readonly detail: string,
  ) {
    super(`${kind} ${status}: ${detail}`);
    this.name = 'ApiError';
  }

  /** Errors worth retrying later (connectivity, server overload) vs. permanent client errors. */
  get retryable(): boolean {
    return this.kind !== 'http' || this.status >= 500 || this.status === 408 || this.status === 429;
  }
}

interface RequestOpts {
  body?: unknown;
  form?: FormData;
  timeoutMs?: number;
  auth?: boolean;
  /** Explicit bearer token (e.g. the short-lived PIN-change token before the user is signed in). */
  token?: string;
  as?: 'json' | 'blob';
}

export function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
}

async function request<T>(method: string, path: string, opts: RequestOpts = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: opts.as === 'blob' ? '*/*' : 'application/json' };
  const token = opts.token ?? (opts.auth === false ? null : getToken());
  if (token) headers.Authorization = `Bearer ${token}`;
  let body: BodyInit | undefined;
  if (opts.form) body = opts.form;
  else if (opts.body !== undefined) {
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify(opts.body);
  }
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), opts.timeoutMs ?? 30_000);
  let res: Response;
  try {
    res = await fetch(apiUrl(path), { method, headers, body, signal: ctrl.signal });
  } catch (e) {
    const aborted = e instanceof DOMException && e.name === 'AbortError';
    throw new ApiError(aborted ? 'timeout' : 'network', 0, String(e));
  } finally {
    clearTimeout(timer);
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const j = (await res.json()) as { detail?: unknown };
      if (j && j.detail !== undefined) detail = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail);
    } catch {
      /* not JSON */
    }
    // Only if this request used the *current* token: a late 401 for a token replaced by a PIN change
    // must not end the new session.
    if (res.status === 401 && token && !opts.token && getToken() === token) logout();
    throw new ApiError('http', res.status, detail);
  }
  if (opts.as === 'blob') return (await res.blob()) as T;
  return (await res.json()) as T;
}

const enc = encodeURIComponent;

export const api = {
  login: (phone: string, pin: string) =>
    request<LoginResponse>('POST', '/v1/auth/login', { body: { phone, pin }, auth: false }),
  openSession: (role: string) =>
    request<LoginResponse>('POST', '/v1/auth/open', { body: { role }, auth: false }),
  me: () => request<MeResponse>('GET', '/v1/me'),
  changePin: (body: PinChangeBody, token?: string) =>
    request<LoginResponse>('POST', '/v1/auth/pin', { body, ...(token ? { token } : {}) }),
  bootstrap: () => request<Bootstrap>('GET', '/v1/bootstrap', { timeoutMs: 90_000 }),

  listChildren: (cid: string) => request<ChildOut[]>('GET', `/v1/classrooms/${enc(cid)}/children`),
  upsertChild: (cid: string, child: ChildOut) =>
    request<ChildOut>('POST', `/v1/classrooms/${enc(cid)}/children`, { body: child }),
  deleteChild: (id: string) => request<{ deleted: string }>('DELETE', `/v1/children/${enc(id)}`),

  today: (cid: string) => request<TodayResponse>('GET', `/v1/classrooms/${enc(cid)}/today`, { timeoutMs: 60_000 }),
  childPlan: (id: string) => request<Partial<SessionPlan>>('GET', `/v1/children/${enc(id)}/plan`),
  card: (cid: string, regenerate = false) =>
    request<CardResponse>('GET', `/v1/classrooms/${enc(cid)}/card${regenerate ? '?regenerate=true' : ''}`, {
      timeoutMs: 120_000,
    }),
  overview: (cid: string) => request<Overview>('GET', `/v1/classrooms/${enc(cid)}/overview`),
  profile: (id: string) => request<ChildProfile>('GET', `/v1/children/${enc(id)}/profile`),
  explain: (id: string) => request<Explanation>('GET', `/v1/children/${enc(id)}/explain`, { timeoutMs: 90_000 }),
  unsure: (cid: string) => request<UnsureEntry[]>('GET', `/v1/classrooms/${enc(cid)}/unsure`),
  /** `path` is the server-provided media URL, e.g. /v1/responses/{rid}/media. */
  media: (path: string) => request<Blob>('GET', path, { as: 'blob', timeoutMs: 60_000 }),
  confirm: (rid: string, body: ConfirmBody) =>
    request<{ id: string; status: string }>('POST', `/v1/responses/${enc(rid)}/confirm`, { body }),

  notifications: () => request<NotificationList>('GET', '/v1/notifications'),
  readNotification: (id: string) => request<AppNotification>('POST', `/v1/notifications/${enc(id)}/read`),
  readAllNotifications: () => request<NotificationList>('POST', '/v1/notifications/read-all'),

  classActivity: (cid: string) =>
    request<ClassActivity>('GET', `/v1/classrooms/${enc(cid)}/activity`, { timeoutMs: 60_000 }),
  studentActivity: (id: string) =>
    request<StudentActivity>('GET', `/v1/children/${enc(id)}/activity`, { timeoutMs: 60_000 }),

  adminDashboard: () => request<AdminDashboard>('GET', '/v1/admin/dashboard', { timeoutMs: 60_000 }),
  adminTeachers: () => request<TeacherRow[]>('GET', '/v1/admin/teachers'),
  adminStudents: (f: StudentFilter) => {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(f)) if (v !== undefined && v !== null && v !== '') qs.set(k, String(v));
    return request<AdminStudentPage>('GET', `/v1/admin/students?${qs.toString()}`);
  },
  updateStudent: (id: string, body: { grade?: number; consent_status?: ConsentStatus }) =>
    request<StudentRow>('PATCH', `/v1/admin/students/${enc(id)}`, { body }),

  /** Timeout grows with the upload size: 2G uplinks can be as slow as ~8 KB/s. */
  sync: (form: FormData, bytes = 0) =>
    request<SyncResult>('POST', '/v1/sync', { form, timeoutMs: 120_000 + Math.ceil(bytes / 8_000) * 1000 }),

  setupStatus: () => request<{ needed: boolean }>('GET', '/v1/auth/setup', { auth: false }),
  setup: (body: { phone: string; pin: string; display_name: string }) =>
    request<LoginResponse>('POST', '/v1/auth/setup', { body, auth: false }),

  signupOptions: () => request<SignupOptions>('GET', '/v1/auth/signup-options', { auth: false }),
  approvers: (role: string, place: { org_unit_id?: string; classroom_id?: string }) =>
    request<Approver[]>('GET', `/v1/auth/approvers?${new URLSearchParams({ role, ...place }).toString()}`, { auth: false }),
  /** Teachers: pending request. Admins: active at once — the response then also carries a session. */
  signup: (body: SignupBody) =>
    request<{ id: string; pending: boolean } & Partial<LoginResponse>>('POST', '/v1/auth/signup', { body, auth: false }),
  approveUser: (id: string) => request<AdminUser>('POST', `/v1/admin/users/${enc(id)}/approve`),
  rejectUser: (id: string) => request<{ deleted: string }>('DELETE', `/v1/admin/users/${enc(id)}`),

  orgUnits: () => request<OrgUnitOut[]>('GET', '/v1/admin/org-units'),
  createOrgUnit: (body: { kind: OrgKind; name: string; parent_id: string | null }) =>
    request<{ id: string }>('POST', '/v1/admin/org-units', { body }),
  schools: () => request<SchoolOut[]>('GET', '/v1/admin/schools'),
  createSchool: (body: { name: string; udise_code?: string; org_unit_id: string | null }) =>
    request<{ id: string }>('POST', '/v1/admin/schools', { body }),
  adminClassrooms: () => request<AdminClassroom[]>('GET', '/v1/admin/classrooms'),
  createClassroom: (body: { school_id: string; name: string; grades: number[] }) =>
    request<{ id: string }>('POST', '/v1/admin/classrooms', { body }),
  users: () => request<AdminUser[]>('GET', '/v1/admin/users'),
  createUser: (body: NewUserBody) => request<{ id: string; pin?: string }>('POST', '/v1/admin/users', { body }),
  updateUser: (id: string, body: { active?: boolean; display_name?: string; classroom_ids?: string[] }) =>
    request<AdminUser>('PATCH', `/v1/admin/users/${enc(id)}`, { body }),
  resetPin: (id: string) => request<{ id: string; pin: string }>('POST', `/v1/admin/users/${enc(id)}/reset-pin`),
};
