/**
 * JobPulse's API, on the hadoku jobplatform API (https://hadoku.me/jobplatform/api).
 *
 * The method names and return types are the ones the components were written
 * against when this talked to the local FastAPI backend; each is now a mapping
 * onto hadoku (src/api/hadoku.ts holds the transport and the shape mappings,
 * docs/HADOKU_MERGE.md the table). Every call rides the visitor's own
 * hadoku.me session, so each person sees their own pipeline and profiles.
 */
import type {
  AutofillPayload,
  DiscoveredJob,
  FitBreakdown,
  Job,
  JobId,
  Metrics,
  Profile,
  SearchProfile,
  Skill,
} from '../types';
import {
  hadoku,
  HadokuApiError,
  hadokuPriority,
  jobFromDetail,
  jobFromPipeline,
  jobPath,
  json,
  stateOf,
  type HadokuJob,
  type HadokuState,
  type JobEvent,
  type PipelineItem,
} from './hadoku';

// ── hadoku shapes used only here ─────────────────────────────────────────────

interface FeedPage {
  jobs: HadokuJob[];
  total: number;
  page: number;
  limit: number;
  has_more: boolean;
}

interface HadokuProfile {
  id: string;
  name: string;
  keywords: string[];
  track: 'ic' | 'manager' | 'either';
  levels: SearchProfile['levels'];
  remote_pref: SearchProfile['remote_pref'];
  created_at: string;
  is_default: boolean;
  location?: string | null;
  radius_miles?: number | null;
  min_salary?: number | null;
  include_undisclosed_salary?: boolean | null;
  us_only?: boolean | null;
}

interface ProfileCompany {
  id: string;
  ats: string;
  slug: string;
  display_name: string;
}

interface CompanyMatch {
  query: string;
  matched: boolean;
  ats: string | null;
  slug: string | null;
  company_name: string | null;
  n_jobs: number;
  sample_titles: string[];
  domain: string | null;
}

interface ApplicantProfile {
  name: string;
  email: string;
  phone?: string;
  location?: string;
  headline?: string;
  summary?: string;
  linkedin?: string;
  github?: string;
  portfolio?: string;
  work_authorization?: string;
  desired_salary?: string;
  notice_period?: string;
  master_resume_text?: string;
  [other: string]: unknown;
}

interface Insights {
  states: Record<string, number>;
  reached: { applied: number; responded: number; interviewed: number; offered: number };
  rates: { response: number | null; interview: number | null; offer: number | null };
  weekly_applied: { week: string; count: number }[];
  workplace: { workplace_type: string; count: number }[];
  skills: { skill: string; postings: number; in_stack: boolean }[];
  skill_postings: number;
}

interface ApplicationExtras {
  cover_letter_markdown: string;
  intro_email: string;
  why_hook: string;
  screening_answers: { q: string; a: string }[];
  salary_line: string;
  linkedin_note: string;
  talking_points: string[];
  standard_fields: string;
  cached: boolean;
}

export type ApplicationStatus = 'queued' | 'filled' | 'approved' | 'submitted' | 'needs_manual' | 'failed' | 'job_closed';

/** One posting handed to hadoku's form runner (GET /applications). */
export interface ApplicationEntry {
  id: string;
  job_id: JobId;
  variant_slug: string;
  mode: 'review' | 'auto';
  status: ApplicationStatus;
  error: string | null;
  created_at: string;
  updated_at: string;
  title: string;
  company: string;
  location: string;
  form_url: string;
  still_unanswered?: string[];
}

/** A tailored résumé + cover letter page minted for a posting (GET /jobs/packets). */
export interface PacketEntry {
  job_id: JobId;
  title: string;
  company: string;
  location: string;
  state: string;
  variant_slug: string;
  updated_at: string;
}

/** A form question the runner met and could not answer (GET /unanswered-questions). */
export interface UnansweredQuestion {
  question_key: string;
  question: string;
  companies: string[];
  applications: number;
  blocking: number;
  /** The form's choices; empty for free text. An answer must match one verbatim. */
  options: string[];
  multi: boolean;
}

// ── mappings ─────────────────────────────────────────────────────────────────

const PIPELINE_STATES: HadokuState[] = ['saved', 'interested', 'applied', 'interviewing', 'offered', 'rejected'];

/** hadoku's source_site is a domain ('greenhouse.io'); Discovery names sources short. */
function sourceName(site: string): string {
  const s = site.toLowerCase();
  for (const name of ['greenhouse', 'ashby', 'lever', 'remoteok', 'remotive']) {
    if (s.includes(name)) return name;
  }
  return s.replace(/\.(io|com|co|org|net)$/, '');
}

function discoveredFrom(j: HadokuJob): DiscoveredJob {
  return {
    id: j.id,
    title: j.title,
    company: j.company,
    location: j.location,
    workplace_type: j.workplace_type,
    url: j.application_url ?? j.url ?? '',
    salary_min: j.salary_min ?? undefined,
    salary_max: j.salary_max ?? undefined,
    description: '',
    source: sourceName(j.source_site),
    role_track: j.role_track ?? undefined,
    role_level: (j.role_level as DiscoveredJob['role_level']) ?? null,
    fit_score: Math.round(j.score * 100),
    posted_date: j.posted_date ?? undefined,
  };
}

function searchProfileFrom(p: HadokuProfile, companies: ProfileCompany[]): SearchProfile {
  return {
    id: p.id,
    name: p.name,
    is_default: p.is_default,
    keywords: p.keywords,
    target_companies: companies.map(c => c.display_name || c.slug),
    track: p.track,
    levels: p.levels,
    remote_pref: p.remote_pref,
    location: p.location ?? '',
    radius_miles: p.radius_miles ?? 25,
    min_salary: p.min_salary ?? null,
    include_undisclosed_salary: p.include_undisclosed_salary ?? true,
    us_only: p.us_only ?? false,
    created_at: p.created_at,
  };
}

function profileBody(p: Partial<SearchProfile>): Record<string, unknown> {
  const body: Record<string, unknown> = {};
  for (const k of [
    'name',
    'keywords',
    'track',
    'levels',
    'remote_pref',
    'radius_miles',
    'min_salary',
    'include_undisclosed_salary',
    'us_only',
  ] as const) {
    if (p[k] !== undefined) body[k] = p[k];
  }
  if (p.location !== undefined) body.location = p.location.trim() || null;
  return body;
}

function profileFromApplicant(a: ApplicantProfile | null): Profile {
  return {
    full_name: a?.name ?? '',
    email: a?.email ?? '',
    phone: a?.phone ?? '',
    location: a?.location ?? '',
    title: a?.headline ?? '',
    summary: a?.summary ?? '',
    linkedin_url: a?.linkedin ?? '',
    github_url: a?.github ?? '',
    portfolio_url: a?.portfolio ?? '',
    work_authorization: a?.work_authorization ?? '',
    desired_salary: a?.desired_salary ?? '',
    notice_period: a?.notice_period ?? '',
    master_resume_text: a?.master_resume_text ?? '',
  };
}

const PROFILE_KEYS: Record<keyof Profile, keyof ApplicantProfile | null> = {
  id: null,
  updated_at: null,
  full_name: 'name',
  email: 'email',
  phone: 'phone',
  location: 'location',
  title: 'headline',
  summary: 'summary',
  linkedin_url: 'linkedin',
  github_url: 'github',
  portfolio_url: 'portfolio',
  work_authorization: 'work_authorization',
  desired_salary: 'desired_salary',
  notice_period: 'notice_period',
  master_resume_text: 'master_resume_text',
};

/** A résumé tailored to the posting: every document below is built on it. */
async function tailoredResume(jobId: JobId): Promise<string> {
  const r = await hadoku<{ resume_markdown: string }>(`${jobPath(jobId)}/resume`, json('POST', {}));
  return r.resume_markdown;
}

const percent = (rate: number | null) => (rate === null ? 0 : Math.round(rate * 100));

// ── the API ──────────────────────────────────────────────────────────────────

export const api = {
  // Jobs: the pipeline. A posting is in a person's pipeline exactly when they
  // have a state for it; ARCHIVED is hadoku's 'dismissed', which GET /pipeline
  // includes on request (include_dismissed).
  async getJobs(status?: string, priority?: string): Promise<Job[]> {
    const { items } = await hadoku<{ items: PipelineItem[] }>('/pipeline?include_dismissed=true');
    const jobs = items.map(jobFromPipeline);
    return jobs.filter(j => (!status || j.status === status) && (!priority || j.priority === priority));
  },

  async getJob(id: JobId): Promise<Job> {
    const [detail, events] = await Promise.all([
      hadoku<{ job: HadokuJob }>(jobPath(id)),
      hadoku<{ events: JobEvent[] }>(`${jobPath(id)}/events`).catch((err: unknown) => {
        // 409: the caller tracks no state for it, so it has no timeline yet.
        if (err instanceof HadokuApiError && err.status === 409) return { events: [] };
        throw err;
      }),
    ]);
    return jobFromDetail(detail.job, events.events);
  },

  /**
   * Into the pipeline. A posting hadoku already holds (from Discovery or an
   * import: it carries an `id`) just gets a state. Anything else is a posting
   * typed in by hand: hadoku stores it for this person only.
   */
  async createJob(job: Partial<Job>): Promise<Job> {
    const state = stateOf(job.status ?? 'TO_APPLY');
    let id = job.id;
    if (id) {
      await hadoku(`${jobPath(id)}/state`, json('PUT', { state }));
    } else {
      const res = await hadoku<{ job: { id: JobId } }>(
        '/jobs/import',
        json('POST', {
          ...(job.url ? { url: job.url } : {}),
          state,
          manual: {
            title: job.title ?? '',
            company: job.company ?? '',
            location: job.location ?? '',
            description: job.description ?? '',
            ...(job.salary_min ? { salary_min: job.salary_min } : {}),
            ...(job.salary_max ? { salary_max: job.salary_max } : {}),
            ...(job.workplace_type ? { workplace_type: job.workplace_type } : {}),
          },
        }),
      );
      id = res.job.id;
    }
    if (job.priority && job.priority !== 'medium') {
      await hadoku(`${jobPath(id)}/tracking`, json('PATCH', { priority: hadokuPriority(job.priority) }));
    }
    return this.getJob(id);
  },

  /** status → PUT /state; priority, notes, deadline and contact → PATCH /tracking. */
  async updateJob(id: JobId, updates: Partial<Job>): Promise<Job> {
    if (updates.status) {
      await hadoku(`${jobPath(id)}/state`, json('PUT', { state: stateOf(updates.status) }));
    }
    const tracking: Record<string, unknown> = {};
    if (updates.priority !== undefined) tracking.priority = hadokuPriority(updates.priority);
    if (updates.notes !== undefined) tracking.notes = updates.notes || null;
    if (updates.deadline !== undefined) tracking.follow_up_at = updates.deadline ? updates.deadline.slice(0, 10) : null;
    if (updates.contact_person !== undefined) tracking.contact_name = updates.contact_person || null;
    if (updates.contact_email !== undefined) tracking.contact_email = updates.contact_email || null;
    if (Object.keys(tracking).length > 0) {
      await hadoku(`${jobPath(id)}/tracking`, json('PATCH', tracking));
    }
    return this.getJob(id);
  },

  /** Out of this person's pipeline; the posting stays in the shared corpus. */
  async deleteJob(id: JobId): Promise<void> {
    await hadoku(`${jobPath(id)}/state`, { method: 'DELETE' });
  },

  /** hadoku logs one text per row: the title, then the details on the lines after. */
  async addActivity(jobId: JobId, activity: { activity_type: string; title: string; details?: string }): Promise<void> {
    const kinds = ['note', 'interview', 'contact', 'follow_up'];
    const kind = kinds.includes(activity.activity_type) ? activity.activity_type : 'note';
    const note = [activity.title, activity.details].filter(Boolean).join('\n');
    await hadoku(`${jobPath(jobId)}/events`, json('POST', { kind, note }));
  },

  /**
   * Whether a posting is still up. hadoku's nightly scrape answers this for
   * every posting it tracks (`closed`: its board stopped listing it), so this
   * reads that rather than fetching the employer's page from the browser.
   */
  async checkJobStatus(id: JobId): Promise<Job> {
    return this.getJob(id);
  },

  async checkAllJobStatuses(): Promise<{ checked: number; expired_found: number; jobs: Job[] }> {
    const jobs = await this.getJobs();
    return { checked: jobs.length, expired_found: jobs.filter(j => j.is_expired).length, jobs };
  },

  // Discovery: hadoku's corpus (Greenhouse, Ashby and Lever boards, plus
  // RemoteOK and Remotive), searched on the server.
  async searchDiscoveredJobs(opts: {
    query?: string;
    source?: string;
    location?: string;
    radius?: number;
    includeRemote?: boolean;
    minSalary?: number;
    includeUndisclosedSalary?: boolean;
    track?: string;
    profileId?: string;
    pages?: number;
  }): Promise<DiscoveredJob[]> {
    const params = new URLSearchParams({ limit: '100' });
    if (opts.query?.trim()) params.set('q', opts.query.trim());
    if (opts.source && opts.source !== 'all') params.set('source', opts.source);
    if (opts.location?.trim()) {
      params.set('near', opts.location.trim());
      if (opts.radius) params.set('radius_miles', String(opts.radius));
      params.set('include_remote', String(opts.includeRemote ?? true));
    }
    if (opts.minSalary && opts.minSalary > 0) params.set('min_salary', String(opts.minSalary));
    if (opts.track === 'ic' || opts.track === 'manager') params.set('track', opts.track);
    if (opts.profileId) {
      params.set('profile_id', opts.profileId);
      params.set('sort', 'score');
    } else {
      params.set('sort', 'date');
    }
    const pages = Math.max(1, opts.pages ?? 2);
    const results = await Promise.all(
      Array.from({ length: pages }, (_, i) => {
        const p = new URLSearchParams(params);
        p.set('page', String(i + 1));
        return hadoku<FeedPage>(`/jobs?${p}`);
      }),
    );
    const seen = new Set<string>();
    const jobs: DiscoveredJob[] = [];
    for (const page of results) {
      for (const j of page.jobs) {
        if (seen.has(j.id)) continue;
        seen.add(j.id);
        // hadoku keeps postings with no listed salary in a min_salary view;
        // this switch is JobPulse's, so it is applied here.
        if (opts.includeUndisclosedSalary === false && opts.minSalary && !j.salary_max && !j.salary_min) continue;
        jobs.push(discoveredFrom(j));
      }
    }
    return jobs;
  },

  /**
   * Read a posting from its URL. hadoku stores it and puts it in the pipeline
   * as To Apply in the same step, so the preview the import dialog shows is
   * already tracked; confirming keeps it there.
   */
  async importJobUrl(url: string): Promise<Partial<Job>> {
    const res = await hadoku<{ job: { id: JobId } }>('/jobs/import', json('POST', { url, state: 'saved' }));
    return this.getJob(res.job.id);
  },

  // Profile & skills
  async getProfile(): Promise<Profile> {
    const data = await hadoku<{ profile: ApplicantProfile | null }>('/applicant-profile');
    return profileFromApplicant(data.profile);
  },

  /** PUT replaces the whole record, so the change is merged onto what is stored. */
  async updateProfile(profile: Partial<Profile>): Promise<Profile> {
    const current = (await hadoku<{ profile: ApplicantProfile | null }>('/applicant-profile')).profile ?? {
      name: '',
      email: '',
    };
    const next: ApplicantProfile = { ...current };
    for (const [k, v] of Object.entries(profile) as [keyof Profile, unknown][]) {
      const target = PROFILE_KEYS[k];
      if (target && typeof v === 'string') next[target] = v;
    }
    await hadoku('/applicant-profile', json('PUT', next));
    return this.getProfile();
  },

  async getSkills(): Promise<Skill[]> {
    const data = await hadoku<{ skills: (Omit<Skill, 'category'> & { category: string | null })[] }>('/skills');
    return data.skills.map(s => ({ ...s, category: s.category ?? '' }));
  },

  async addSkill(name: string, category: string, proficiency: string): Promise<Skill> {
    const data = await hadoku<{ skill: Omit<Skill, 'category'> & { category: string | null } }>(
      '/skills',
      json('POST', { name, ...(category ? { category } : {}), proficiency }),
    );
    return { ...data.skill, category: data.skill.category ?? '' };
  },

  async deleteSkill(id: number): Promise<void> {
    await hadoku(`/skills/${id}`, { method: 'DELETE' });
  },

  // Search profiles: hadoku's scoring profiles. Target companies are the
  // profile's company slice, the boards hadoku's scraper reads for it.
  async getSearchProfiles(): Promise<SearchProfile[]> {
    const { profiles } = await hadoku<{ profiles: HadokuProfile[] }>('/profiles');
    return Promise.all(
      profiles.map(async p => {
        const { companies } = await hadoku<{ companies: ProfileCompany[] }>(
          `/profiles/${encodeURIComponent(p.id)}/companies`,
        ).catch(() => ({ companies: [] as ProfileCompany[] }));
        return searchProfileFrom(p, companies);
      }),
    );
  },

  async createSearchProfile(profile: Omit<SearchProfile, 'id' | 'created_at' | 'updated_at'>): Promise<SearchProfile> {
    const { profile: created } = await hadoku<{ profile: HadokuProfile }>('/profiles', json('POST', profileBody(profile)));
    await this.setTargetCompanies(created.id, profile.target_companies ?? []);
    return (await this.getSearchProfiles()).find(p => p.id === created.id) ?? searchProfileFrom(created, []);
  },

  async updateSearchProfile(id: string, updates: Partial<SearchProfile>): Promise<SearchProfile> {
    const body = profileBody(updates);
    if (Object.keys(body).length > 0) {
      await hadoku(`/profiles/${encodeURIComponent(id)}`, json('PUT', body));
    }
    if (updates.target_companies) await this.setTargetCompanies(id, updates.target_companies);
    const found = (await this.getSearchProfiles()).find(p => p.id === id);
    if (!found) throw new HadokuApiError('That profile is gone.', 404);
    return found;
  },

  async deleteSearchProfile(id: string): Promise<void> {
    await hadoku(`/profiles/${encodeURIComponent(id)}`, { method: 'DELETE' });
  },

  /**
   * Make a profile's company slice match a list of names: names already there
   * stay, removed ones are dropped, and new ones are matched to a board by the
   * scraper (POST /companies/match) and added. A name no board matches is
   * reported back rather than silently skipped.
   */
  async setTargetCompanies(profileId: string, names: string[]): Promise<{ unmatched: string[] }> {
    const base = `/profiles/${encodeURIComponent(profileId)}/companies`;
    const { companies } = await hadoku<{ companies: ProfileCompany[] }>(base);
    const want = new Map<string, string>(
      names.map(n => [n.trim().toLowerCase(), n.trim()] as [string, string]).filter(([k]) => k),
    );
    const have = new Map(companies.map(c => [(c.display_name || c.slug).toLowerCase(), c]));
    for (const [key, c] of have) {
      if (!want.has(key)) await hadoku(`${base}/${encodeURIComponent(c.id)}`, { method: 'DELETE' });
    }
    const toAdd = [...want].filter(([key]) => !have.has(key)).map(([, name]) => name);
    if (toAdd.length === 0) return { unmatched: [] };
    const { results } = await hadoku<{ results: CompanyMatch[] }>('/companies/match', json('POST', { names: toAdd }));
    const unmatched: string[] = [];
    for (const m of results) {
      if (!m.matched || !m.ats || !m.slug) {
        unmatched.push(m.query);
        continue;
      }
      await hadoku(base, json('POST', { ats: m.ats, slug: m.slug, display_name: m.company_name ?? m.query }));
    }
    return { unmatched };
  },

  /** The pipeline, each posting scored against one profile (hadoku scores live). */
  async scorePipelineWithProfile(id: string): Promise<{ profile_id: string; profile_name: string; jobs_scored: number; jobs: Job[] }> {
    const [jobs, profiles, ...scored] = await Promise.all([
      this.getJobs(),
      hadoku<{ profiles: HadokuProfile[] }>('/profiles'),
      ...PIPELINE_STATES.map(state =>
        hadoku<FeedPage>(`/jobs?state=${state}&profile_id=${encodeURIComponent(id)}&limit=100`),
      ),
    ]);
    const score = new Map(scored.flatMap(p => p.jobs.map(j => [j.id, Math.round(j.score * 100)] as const)));
    const withScores = jobs.map(j => (score.has(j.id) ? { ...j, fit_score: score.get(j.id) } : j));
    return {
      profile_id: id,
      profile_name: profiles.profiles.find(p => p.id === id)?.name ?? '',
      jobs_scored: score.size,
      jobs: withScores,
    };
  },

  async getDirectives(): Promise<{ companies: string[]; keywords: string[]; profiles_count: number }> {
    const d = await hadoku<{ companies: { ats: string; slug: string }[]; keywords: string[] }>('/directives');
    const profiles = await hadoku<{ profiles: HadokuProfile[] }>('/profiles');
    return { companies: d.companies.map(c => `${c.ats}:${c.slug}`), keywords: d.keywords, profiles_count: profiles.profiles.length };
  },

  // Assistant: documents from hadoku's résumé service, tailored per posting.
  async analyzeJobMatch(jobId: JobId): Promise<FitBreakdown> {
    const m = await hadoku<{ matched: string[]; missing: string[]; detected: string[]; score: number; summary: string }>(
      `${jobPath(jobId)}/match`,
    );
    return {
      score: m.score,
      matched_skills: m.matched,
      missing_skills: m.missing,
      detected_requirements: m.detected,
      summary: m.summary,
    };
  },

  /**
   * One document for a posting. hadoku tailors the résumé and writes the cover
   * letter itself (its résumé service). The cover letter takes a tone; the
   * free-form instructions and provider JobPulse's own generator took have no
   * counterpart there.
   */
  async generateDocument(
    jobId: JobId,
    docType: string,
    tone: 'formal' | 'conversational' = 'formal',
  ): Promise<{ doc_type: string; content: string; provider_used: string }> {
    if (docType === 'cover_letter') {
      const r = await hadoku<{ cover_letter_markdown: string }>(`${jobPath(jobId)}/cover-letter`, json('POST', { tone }));
      return { doc_type: docType, content: r.cover_letter_markdown, provider_used: 'hadoku' };
    }
    const resume = await tailoredResume(jobId);
    if (docType === 'tailored_resume') return { doc_type: docType, content: resume, provider_used: 'hadoku' };
    const kit = await hadoku<ApplicationExtras>(`${jobPath(jobId)}/application-extras`, json('POST', { resume_markdown: resume }));
    if (docType === 'pitch') return { doc_type: docType, content: `${kit.why_hook}\n\n${kit.intro_email}`, provider_used: 'hadoku' };
    if (docType === 'resume_bullets') {
      return { doc_type: docType, content: kit.talking_points.map(t => `- ${t}`).join('\n'), provider_used: 'hadoku' };
    }
    return { doc_type: docType, content: kit.cover_letter_markdown, provider_used: 'hadoku' };
  },

  /** The applicant's own facts, as the autofill copy panel lays them out. */
  async getAutofillPayload(jobId: JobId): Promise<AutofillPayload> {
    const [profile, letter] = await Promise.all([
      this.getProfile(),
      hadoku<{ cover_letter_markdown: string }>(`${jobPath(jobId)}/cover-letter`, json('POST', {})).catch(() => null),
    ]);
    const [first = '', ...rest] = profile.full_name.trim().split(/\s+/);
    return {
      first_name: first,
      last_name: rest.join(' '),
      full_name: profile.full_name,
      email: profile.email,
      phone: profile.phone,
      location: profile.location,
      linkedin_url: profile.linkedin_url,
      github_url: profile.github_url,
      portfolio_url: profile.portfolio_url,
      work_authorization: profile.work_authorization,
      desired_salary: profile.desired_salary,
      notice_period: profile.notice_period,
      summary: profile.summary,
      cover_letter_snippet: letter ? letter.cover_letter_markdown.split('\n\n')[0] ?? '' : '',
    };
  },

  async generateApplicationKit(jobId: JobId): Promise<{
    provider_used: string;
    why_hook: string;
    intro_email: string;
    linkedin_note: string;
    salary_line: string;
    talking_points: string[];
    screening_answers: { q: string; a: string }[];
    cover_letter_markdown: string;
  }> {
    const resume = await tailoredResume(jobId);
    const kit = await hadoku<ApplicationExtras>(`${jobPath(jobId)}/application-extras`, json('POST', { resume_markdown: resume }));
    return {
      provider_used: 'hadoku',
      why_hook: kit.why_hook,
      intro_email: kit.intro_email,
      linkedin_note: kit.linkedin_note,
      salary_line: kit.salary_line,
      talking_points: kit.talking_points,
      screening_answers: kit.screening_answers,
      cover_letter_markdown: kit.cover_letter_markdown,
    };
  },

  /** A shareable résumé + cover letter page for this posting (hadoku.me/resume?v=). */
  async mintResumePacket(jobId: JobId): Promise<{ slug: string; label: string; url: string; pdf_url: string }> {
    const resume = await tailoredResume(jobId);
    const letter = await hadoku<{ cover_letter_markdown: string }>(`${jobPath(jobId)}/cover-letter`, json('POST', {})).catch(
      () => null,
    );
    const packet = await hadoku<{ slug: string; url: string }>(
      `${jobPath(jobId)}/packet-link`,
      json('POST', { resume_markdown: resume, ...(letter ? { cover_letter_markdown: letter.cover_letter_markdown } : {}) }),
    );
    return {
      slug: packet.slug,
      label: 'Application packet',
      url: packet.url,
      pdf_url: `https://hadoku.me/resume/api/resume.pdf?v=${encodeURIComponent(packet.slug)}`,
    };
  },

  // Company matching for search profiles (the scraper's /match, read-only).
  async matchScraperCompanies(names: string[]): Promise<{ results: CompanyMatch[] }> {
    return hadoku<{ results: CompanyMatch[] }>('/companies/match', json('POST', { names }));
  },

  // The application runner: hadoku fills a posting's form for you, you
  // approve the filled form, and only then is it submitted.
  /**
   * Hand a posting to the runner. It needs a packet (tailored résumé + cover
   * letter page) to fill from, so one is minted first if this posting has none.
   */
  async queueApplication(jobId: JobId): Promise<ApplicationEntry> {
    const packets = await hadoku<{ packets: PacketEntry[] }>('/jobs/packets');
    if (!packets.packets.some(p => p.job_id === jobId)) await this.mintResumePacket(jobId);
    const res = await hadoku<{ application: ApplicationEntry }>(`${jobPath(jobId)}/apply`, json('POST', { mode: 'review' }));
    return res.application;
  },

  async getApplications(): Promise<ApplicationEntry[]> {
    return (await hadoku<{ applications: ApplicationEntry[] }>('/applications')).applications;
  },

  async approveApplication(id: string): Promise<ApplicationEntry> {
    const res = await hadoku<{ application: ApplicationEntry }>(
      `/applications/${encodeURIComponent(id)}/approve`,
      { method: 'POST' },
    );
    return res.application;
  },

  async getPackets(): Promise<PacketEntry[]> {
    return (await hadoku<{ packets: PacketEntry[] }>('/jobs/packets')).packets;
  },

  async getUnansweredQuestions(): Promise<UnansweredQuestion[]> {
    return (await hadoku<{ questions: UnansweredQuestion[] }>('/unanswered-questions')).questions;
  },

  /** A standing answer: the runner uses it on every form that asks this question. */
  async saveAnswer(question: string, answer: string): Promise<void> {
    await hadoku('/application-answers', json('PUT', { question, answer }));
  },

  /** Up/down vote a posting, which steers what the feed ranks for you; null clears it. */
  async voteJob(jobId: JobId, vote: 1 | -1 | null): Promise<void> {
    if (vote === null) {
      await hadoku(`${jobPath(jobId)}/feedback`, { method: 'DELETE' });
    } else {
      await hadoku(`${jobPath(jobId)}/feedback`, json('PUT', { vote, reasons: [] }));
    }
  },

  /** Employers hidden from your Discover feed (matched on the company name). */
  async getBlockedCompanies(): Promise<string[]> {
    const data = await hadoku<{ companies: { company: string }[] }>('/blocked-companies');
    return data.companies.map(c => c.company);
  },

  async blockCompany(company: string): Promise<void> {
    await hadoku('/blocked-companies', json('PUT', { company }));
  },

  async unblockCompany(company: string): Promise<void> {
    await hadoku(`/blocked-companies?company=${encodeURIComponent(company)}`, { method: 'DELETE' });
  },

  // Analytics: hadoku's insights over this person's own pipeline.
  async getMetrics(): Promise<Metrics> {
    const i = await hadoku<Insights>('/insights');
    const n = (k: string) => i.states[k] ?? 0;
    return {
      funnel: {
        total_tracked: Object.values(i.states).reduce((a, b) => a + b, 0),
        wishlist: 0,
        to_apply: n('saved') + n('interested'),
        applied: n('applied'),
        interviewing: n('interviewing'),
        offer: n('offered'),
        rejected: n('rejected'),
        response_rate_percent: percent(i.rates.response),
        interview_rate_percent: percent(i.rates.interview),
      },
      top_demanded_skills: i.skills.map(s => ({ name: s.skill, count: s.postings })),
      workplace_distribution: Object.fromEntries(i.workplace.map(w => [w.workplace_type, w.count])),
    };
  },
};
