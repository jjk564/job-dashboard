/**
 * The hadoku jobplatform API (https://hadoku.me/jobplatform/api), and the
 * mappings between its shapes and this UI's types.
 *
 * Every call rides the visitor's own hadoku_session cookie: on hadoku.me the
 * page is same-origin with the API, and the dev server proxies both
 * /jobplatform/api and /session (vite.config.ts). There is no key in the
 * browser, so each person sees their own pipeline, profiles and documents.
 *
 * Responses are wrapped: `{ success: true, data }` or
 * `{ success: false, error, message }`. The message is written for a person.
 */
import type { Activity, Job, JobStatus, Priority } from '../types';
import { trackedFetch } from '../telemetry';

export const HADOKU_API = '/jobplatform/api';

export class HadokuApiError extends Error {
  readonly status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = 'HadokuApiError';
    this.status = status;
  }
}

interface Wrapped<T> {
  success: boolean;
  data?: T;
  error?: string;
  message?: string;
}

export async function hadoku<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body !== undefined && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }
  const res = await trackedFetch(`${HADOKU_API}${path}`, { ...init, headers, credentials: 'include' });
  let body: Wrapped<T> | null = null;
  try {
    body = (await res.json()) as Wrapped<T>;
  } catch {
    // Not JSON (an edge error page): reported below by status alone.
    body = null;
  }
  if (!res.ok || !body?.success) {
    const said = body?.message ?? body?.error;
    throw new HadokuApiError(said ?? `hadoku.me answered ${res.status}`, res.status);
  }
  return body.data as T;
}

export const json = (method: string, payload: unknown): RequestInit => ({
  method,
  body: JSON.stringify(payload),
});

export const jobPath = (id: string) => `/jobs/${encodeURIComponent(id)}`;

// ── The pipeline ─────────────────────────────────────────────────────────────

/** hadoku's per-person triage state (job_states.state). */
export type HadokuState =
  | 'saved'
  | 'interested'
  | 'applied'
  | 'interviewing'
  | 'offered'
  | 'rejected'
  | 'dismissed';

const STATUS_OF: Record<HadokuState, JobStatus> = {
  saved: 'TO_APPLY',
  interested: 'TO_APPLY',
  applied: 'APPLIED',
  interviewing: 'INTERVIEWING',
  offered: 'OFFER',
  rejected: 'REJECTED',
  dismissed: 'ARCHIVED',
};

export const statusOf = (state: string | null | undefined): JobStatus =>
  STATUS_OF[(state ?? 'saved') as HadokuState] ?? 'TO_APPLY';

/** WISHLIST is JobPulse's retired first column; it lands where TO_APPLY does. */
export function stateOf(status: JobStatus): HadokuState {
  switch (status) {
    case 'APPLIED':
      return 'applied';
    case 'INTERVIEWING':
      return 'interviewing';
    case 'OFFER':
      return 'offered';
    case 'REJECTED':
      return 'rejected';
    case 'ARCHIVED':
      return 'dismissed';
    default:
      return 'saved';
  }
}

/** hadoku: 1 high · 2 normal · 3 low (null: never set, shown as medium). */
export type HadokuPriority = 1 | 2 | 3;

export const priorityOf = (p: HadokuPriority | null | undefined): Priority =>
  p === 1 ? 'high' : p === 3 ? 'low' : 'medium';

export const hadokuPriority = (p: Priority): HadokuPriority =>
  p === 'high' ? 1 : p === 'low' ? 3 : 2;

export interface Tracking {
  notes: string | null;
  priority: HadokuPriority | null;
  /** YYYY-MM-DD. */
  follow_up_at: string | null;
  contact_name: string | null;
  contact_email: string | null;
}

export interface PipelineItem {
  job_id: string;
  title: string;
  company: string;
  location: string;
  workplace_type: string;
  salary_min: number | null;
  salary_max: number | null;
  url: string | null;
  posted_date: string | null;
  state: HadokuState;
  updated_at: string;
  tracking: Tracking;
  variant_slug: string | null;
  application_status: string | null;
  applied_at: string | null;
  last_event_at: string | null;
  /** When the nightly scrape last saw it on its board (null: never scraped). */
  last_seen_at?: string | null;
  /** The board no longer lists it. */
  closed?: boolean;
}

/** A posting as GET /jobs and GET /jobs/:id return it (JobSummary / JobDetail). */
export interface HadokuJob {
  id: string;
  title: string;
  company: string;
  location: string;
  workplace_type: string;
  salary_min: number | null;
  salary_max: number | null;
  source_site: string;
  /** null for a posting typed in by hand without one. */
  url: string | null;
  application_url: string | null;
  posted_date: string | null;
  scraped_at: string;
  role_track: 'ic' | 'manager' | 'unknown' | null;
  role_level: string | null;
  /** 0–1. */
  score: number;
  state: HadokuState | 'new' | null;
  application_status: string | null;
  // Detail only:
  description?: string;
  state_updated_at?: string | null;
  tracking?: Tracking | null;
  last_seen_at?: string | null;
  closed?: boolean;
}

export interface JobEvent {
  id: number;
  job_id: string;
  kind: 'state' | 'note' | 'interview' | 'contact' | 'follow_up';
  from_state: HadokuState | null;
  to_state: HadokuState | null;
  note: string | null;
  occurred_at: string;
  created_at: string;
}

const STATE_LABEL: Record<HadokuState, string> = {
  saved: 'To Apply',
  interested: 'To Apply',
  applied: 'Applied',
  interviewing: 'Interviewing',
  offered: 'Offer',
  rejected: 'Rejected',
  dismissed: 'Archived',
};

export function activityOf(e: JobEvent): Activity {
  if (e.kind === 'state') {
    return {
      id: e.id,
      job_id: e.job_id,
      activity_type: 'status_change',
      title: e.from_state
        ? `${STATE_LABEL[e.from_state]} → ${e.to_state ? STATE_LABEL[e.to_state] : '?'}`
        : `Added as ${e.to_state ? STATE_LABEL[e.to_state] : '?'}`,
      created_at: e.occurred_at,
    };
  }
  // A person-logged row carries one text; its first line is the title.
  const [title, ...rest] = (e.note ?? '').split('\n');
  return {
    id: e.id,
    job_id: e.job_id,
    activity_type: e.kind,
    title: title || e.kind,
    details: rest.join('\n').trim() || undefined,
    created_at: e.occurred_at,
  };
}

export function jobFromPipeline(p: PipelineItem): Job {
  return {
    id: p.job_id,
    title: p.title,
    company: p.company,
    location: p.location,
    workplace_type: p.workplace_type,
    url: p.url ?? undefined,
    salary_min: p.salary_min ?? undefined,
    salary_max: p.salary_max ?? undefined,
    status: statusOf(p.state),
    priority: priorityOf(p.tracking.priority),
    notes: p.tracking.notes ?? undefined,
    deadline: p.tracking.follow_up_at,
    contact_person: p.tracking.contact_name ?? undefined,
    contact_email: p.tracking.contact_email ?? undefined,
    applied_at: p.applied_at ?? undefined,
    is_expired: p.closed ?? false,
    expired_at: p.closed ? (p.last_seen_at ?? null) : null,
    expired_reason: p.closed ? 'No longer listed on its board' : null,
    last_seen_at: p.last_seen_at ?? null,
    created_at: p.posted_date ?? undefined,
    updated_at: p.updated_at,
  };
}

export function jobFromDetail(j: HadokuJob, events: JobEvent[] = []): Job {
  const t = j.tracking ?? null;
  return {
    id: j.id,
    title: j.title,
    company: j.company,
    location: j.location,
    workplace_type: j.workplace_type,
    url: j.application_url ?? j.url ?? undefined,
    salary_min: j.salary_min ?? undefined,
    salary_max: j.salary_max ?? undefined,
    description: j.description,
    source: j.source_site,
    status: statusOf(j.state === 'new' ? null : j.state),
    priority: priorityOf(t?.priority),
    fit_score: Math.round(j.score * 100),
    role_track: j.role_track ?? undefined,
    role_level: (j.role_level as Job['role_level']) ?? null,
    notes: t?.notes ?? undefined,
    deadline: t?.follow_up_at ?? null,
    contact_person: t?.contact_name ?? undefined,
    contact_email: t?.contact_email ?? undefined,
    is_expired: j.closed ?? false,
    expired_at: j.closed ? (j.last_seen_at ?? null) : null,
    expired_reason: j.closed ? 'No longer listed on its board' : null,
    last_seen_at: j.last_seen_at ?? null,
    created_at: j.posted_date ?? j.scraped_at,
    updated_at: j.state_updated_at ?? undefined,
    activities: events.map(activityOf),
  };
}
