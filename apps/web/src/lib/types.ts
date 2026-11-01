// API shapes, mirrored from services/api (the Python files are the source of truth).

export interface User {
  id: string;
  role: 'teacher';
  display_name: string;
}

export interface ClassroomInfo {
  id: string;
  name: string;
  grades: number[];
  school: string | null;
  region_profile: string;
  daily_kiosk_budget_min: number;
}

export interface LoginResponse {
  token: string;
  user: User;
  classrooms: ClassroomInfo[];
  /** The PIN used is too weak: `token` can only change the PIN (15 min), nothing else. */
  pin_change_required?: boolean;
  pin_problem?: string;
}

export interface PinChangeBody {
  current_pin: string;
  new_pin: string;
  phone?: string;
}

export interface MeResponse {
  user: User;
  classrooms: ClassroomInfo[];
  /** Server content-pack version: a mismatch with the cached pack triggers a bootstrap download. */
  content_version?: string;
}

// ------------------------------------------------------------------ content pack (bootstrap)
export type ItemType =
  | 'akshara'
  | 'word'
  | 'nonword'
  | 'passage'
  | 'repeat'
  | 'comprehension'
  | 'tap_number'
  | 'tap_compare'
  | 'tap_count'
  | 'tap_missing'
  | 'slate';

export interface ItemOption {
  value: string;
  label?: string;
  probe?: string;
}

export interface ItemQuestion {
  id: string;
  prompt_hi: string;
  options: ItemOption[];
  answer: string;
}

export interface Item {
  id: string;
  type: ItemType;
  grade?: number;
  band?: number;
  form?: string;
  text?: string;
  prompt_hi?: string;
  skills: string[];
  probes?: string[];
  pair?: string;
  options?: ItemOption[];
  answer?: string;
  questions?: ItemQuestion[];
  a?: number;
  b?: number;
  op?: '+' | '-';
}

export interface Skill {
  id: string;
  domain: string;
  name_hi: string;
  name_en: string;
}

export interface Rung {
  id: string;
  name_hi: string;
  name_en: string;
}

export interface ActivityInfo {
  title_hi: string;
  materials: string[];
  minutes: number;
}

export interface Bootstrap {
  version: string;
  language: string;
  items: Item[];
  prompts: Record<string, string>;
  skills: Skill[];
  ladders: Record<string, Rung[]>;
  benchmarks: Record<string, unknown>;
  activities: Record<string, ActivityInfo>;
}

// --------------------------------------------------------------------------------- roster
export type ConsentStatus = 'pending' | 'granted' | 'withdrawn';
export type Gender = 'f' | 'm' | 'x';

export interface ChildOut {
  id: string;
  /** Server-generated permanent register number (STU-<year>-<seq>); absent until the first sync. */
  register_no?: string | null;
  grade: number;
  aruco_slot: number;
  gender: Gender | null;
  consent_status: ConsentStatus;
}

// ---------------------------------------------------------------------------------- plans
export interface PlannedItem {
  item_id: string;
  type: ItemType;
  block: string;
  gain: number;
  reason: string;
}

export interface PlanRules {
  silence_timeout_s?: number;
  max_item_seconds?: Partial<Record<ItemType, number>>;
  discontinue_after_silent_aksharas?: number;
  on_discontinue?: string;
  passage_has_questions?: boolean;
  /** Skip the rest of a block after this many silent voice items in a row (frustration rule). */
  stop_block_after_silent?: number;
}

export interface SessionPlan {
  plan_id?: string;
  child_id: string;
  items: PlannedItem[];
  est_seconds: number;
  rules: PlanRules;
  content_version?: string;
}

export interface SlateProblem {
  item_id: string;
  a: number;
  b: number;
  op: '+' | '-';
  skills?: string[];
}

export interface TodayChild {
  child_id: string;
  priority: number;
  reasons: string[];
  plan: SessionPlan | null;
}

export interface TodayResponse {
  day: string;
  slate_problems: SlateProblem[];
  children: TodayChild[];
}

// ---------------------------------------------------------------------------------- cards
export interface CardGroup {
  group_key: string;
  activity_id: string;
  title_hi: string;
  why_hi: string;
  steps_hi: string[];
  example_items: string[];
}

export interface CardBody {
  headline_hi: string;
  groups: CardGroup[];
  teacher_tip_hi: string;
}

export interface SummaryGroup {
  key: string;
  domain: string;
  level_id: string;
  level_name_hi: string;
  n_children: number;
  top_confusions?: {
    id: string;
    n_children: number;
    /** Children for whom the confusion is verified (≥2 reproductions); absent on cards made before v2.1. */
    n_confirmed?: number;
    n_suspected?: number;
    description_hi: string;
    examples: string[];
  }[];
}

export interface CardResponse {
  id: string;
  week: string;
  source: string;
  card: CardBody;
  summary: { n_children: number; groups: SummaryGroup[]; last_week?: Record<string, number> };
  created_at: string;
}

// ------------------------------------------------------------------------------- profiles
export interface LevelInfo {
  domain: string;
  rung_index: number;
  rung_id: string;
  name_en: string;
  name_hi: string;
  certain: boolean;
  next_rung_id: string | null;
  blocking_skills: string[];
}

export interface Confusion {
  id: string;
  description_hi: string;
  description_en?: string;
  domain: string;
  status: string;
  mean: number;
  certainty_hi: string;
  examples: string[];
}

export interface ProfileSkill {
  id: string;
  name_hi: string;
  domain: string;
  p: number | null;
  checking: boolean;
}

export interface ChildProfile {
  child_id: string;
  grade: number;
  aruco_slot: number;
  levels: Partial<Record<string, LevelInfo>>;
  skills: ProfileSkill[];
  confusions: Confusion[];
  checking: string[];
  wcpm_history: [string, number][];
  last_assessed: string | null;
}

export interface Explanation {
  source: string;
  summary_hi: string;
  bullets_hi: string[];
  next_step_hi: string;
}

export interface OverviewChild {
  child_id: string;
  grade: number;
  aruco_slot: number;
  consent: ConsentStatus;
  literacy: LevelInfo | null;
  numeracy: LevelInfo | null;
  confirmed_confusions: number;
  last_assessed: string | null;
}

export interface Overview {
  n_children: number;
  literacy_levels: Record<string, number>;
  numeracy_levels: Record<string, number>;
  children: OverviewChild[];
}

// ------------------------------------------------------------------------- unsure queue
export interface UnsureEntry {
  id: string;
  child_id: string;
  item_id: string;
  type: ItemType;
  text: string | null;
  verdict: Record<string, unknown> | null;
  problem: { a?: number; b?: number; op?: string } | null;
  media: string | null;
  /** Server ranking: higher = one confirmation teaches the system more. */
  priority?: number;
  reason?: 'verifies_suspected' | 'needs_reading' | 'expiring' | null;
}

export interface ConfirmBody {
  correct?: boolean;
  rule?: string;
  answer?: string;
}

export interface EfficacyRow {
  activity_id: string;
  target_id: string;
  n: number;
  resolved: number;
  improved: number;
  persists: number;
  resolution_rate: number | null;
}

// ----------------------------------------------------------------------------------- sync
export interface SyncResponseIn {
  id: string;
  item_id: string;
  modality: 'voice' | 'tap';
  payload: Record<string, unknown>;
  created_at: string;
  audio_part?: string | null;
}

export interface SyncSessionIn {
  id: string;
  child_id: string;
  classroom_id: string;
  started_at: string;
  ended_at: string | null;
  plan_id: string | null;
  discontinued: boolean;
  responses: SyncResponseIn[];
}

export interface SyncSlatePhotoIn {
  id: string;
  classroom_id: string;
  taken_at: string;
  problems: { item_id: string; a: number; b: number; op: '+' | '-' }[];
  image_part: string;
}

export interface SyncManifest {
  device_id: string;
  sessions: SyncSessionIn[];
  slate_photos: SyncSlatePhotoIn[];
}

export interface SyncResult {
  accepted: { sessions: string[]; responses: string[]; slate_photos: string[] };
  duplicates: string[];
  rejected: { id: string; reason: string }[];
  content_version: string;
  /** Serverless deploys score uploads inside the request; `pending` jobs are still waiting. */
  jobs?: JobsState;
}

export interface JobsState {
  ran: number;
  pending: number;
}

// ------------------------------------------------------------------------------ accounts + classes
export interface ClassroomBody {
  school_name: string;
  class_name: string;
  grades: number[];
  region_profile?: string;
}

export interface SignupBody extends ClassroomBody {
  display_name: string;
  phone: string;
  pin: string;
}

export interface ClassroomPatch {
  name?: string;
  grades?: number[];
  region_profile?: string;
  daily_kiosk_budget_min?: number;
}

export interface RegionOption {
  id: string;
  name: string;
}

// ------------------------------------------------------------------------------ activity
export type Outcome = 'correct' | 'incorrect' | 'unsure' | 'pending' | 'error';

export interface LevelRef {
  rung_id: string | null;
  name: string | null;
  certain: boolean | null;
}

export interface StudentRow {
  id: string;
  register_no: string | null;
  grade: number;
  aruco_slot: number;
  consent: ConsentStatus;
  classroom_id: string;
  classroom: string | null;
  school: string | null;
  teachers: string[];
  sessions: number;
  sessions_7d: number;
  responses: number;
  correct: number;
  incorrect: number;
  to_review: number;
  accuracy: number | null;
  last_active: string | null;
  last_assessed: string | null;
  literacy: LevelRef | null;
  numeracy: LevelRef | null;
  confirmed_confusions: number;
  created_at: string | null;
}

export interface DailyPoint {
  day: string;
  sessions: number;
  answers: number;
}

export interface ActivityItem {
  id: string;
  item_id: string;
  type: string;
  domain: 'literacy' | 'numeracy';
  label: string;
  outcome: Outcome;
  detail: string | null;
  at: string | null;
}

export interface ActivityEntry {
  kind: 'session' | 'slate';
  id: string;
  at: string | null;
  ended_at: string | null;
  duration_s: number | null;
  discontinued: boolean;
  answers: number;
  correct: number;
  incorrect: number;
  to_review: number;
  waiting: number;
  accuracy: number | null;
  items: ActivityItem[];
}

export interface DomainStats {
  correct: number;
  incorrect: number;
  to_review: number;
  accuracy: number | null;
}

export interface StudentActivity {
  student: StudentRow;
  domains: { literacy: DomainStats; numeracy: DomainStats };
  daily: DailyPoint[];
  timeline: ActivityEntry[];
}

export interface ClassActivity {
  totals: {
    students: number;
    consented: number;
    assessed: number;
    active_7d: number;
    sessions_14d: number;
    answers_14d: number;
    accuracy: number | null;
    to_review: number;
  };
  daily: DailyPoint[];
  students: StudentRow[];
}
