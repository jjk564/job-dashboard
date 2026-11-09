import { Job, JobId, Profile, Skill, DiscoveredJob, Metrics, AutofillPayload, FitBreakdown, SearchProfile } from '../types';
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
  type JobEvent,
  type PipelineItem,
} from './hadoku';

const API_BASE = '/api';

export const api = {
  // Jobs: the pipeline, on hadoku (docs/HADOKU_MERGE.md). A posting is in a
  // person's pipeline exactly when they have a state for it; ARCHIVED is
  // hadoku's 'dismissed', which GET /pipeline leaves out and the feed's
  // state= filter returns.
  async getJobs(status?: string, priority?: string): Promise<Job[]> {
    const [inPlay, archived] = await Promise.all([
      hadoku<{ items: PipelineItem[] }>('/pipeline'),
      status && status !== 'ARCHIVED'
        ? Promise.resolve({ jobs: [] as HadokuJob[] })
        : hadoku<{ jobs: HadokuJob[] }>('/jobs?state=dismissed&limit=100&sort=date'),
    ]);
    const jobs = [
      ...inPlay.items.map(jobFromPipeline),
      ...archived.jobs.map(j => jobFromDetail(j)),
    ];
    return jobs.filter(j => (!status || j.status === status) && (!priority || j.priority === priority));
  },

  async getJob(id: JobId): Promise<Job> {
    const [detail, events] = await Promise.all([
      hadoku<{ job: HadokuJob }>(jobPath(id)),
      hadoku<{ events: JobEvent[] }>(`${jobPath(id)}/events`).catch((err: unknown) => {
        // 409: the caller tracks no state for it yet, so it has no timeline.
        if (err instanceof HadokuApiError && err.status === 409) return { events: [] };
        throw err;
      }),
    ]);
    return jobFromDetail(detail.job, events.events);
  },

  /**
   * A posting typed in by hand. hadoku stores it for this person only (the
   * feed shows it to no one else) and puts it straight into the pipeline.
   */
  async createJob(job: Partial<Job>): Promise<Job> {
    if (!job.url) {
      throw new HadokuApiError('Add the posting\'s URL: hadoku keys a posting by it.', 400);
    }
    const res = await hadoku<{ job: { id: JobId } }>(
      '/jobs/import',
      json('POST', {
        url: job.url,
        state: stateOf(job.status ?? 'TO_APPLY'),
        manual: {
          title: job.title ?? '',
          company: job.company ?? '',
          location: job.location ?? '',
          description: job.description ?? '',
        },
      }),
    );
    if (job.priority && job.priority !== 'medium') {
      await hadoku(`${jobPath(res.job.id)}/tracking`, json('PATCH', { priority: hadokuPriority(job.priority) }));
    }
    return this.getJob(res.job.id);
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

  /** Out of this person's pipeline; the posting itself stays in the shared corpus. */
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

  async checkJobStatus(id: JobId): Promise<Job> {
    const res = await fetch(`${API_BASE}/jobs/${id}/check-status`, { method: 'POST' });
    if (!res.ok) throw new Error('Failed to verify job status');
    return res.json();
  },

  async checkAllJobStatuses(): Promise<{ checked: number; expired_found: number; jobs: Job[] }> {
    const res = await fetch(`${API_BASE}/jobs/check-all-status`, { method: 'POST' });
    if (!res.ok) throw new Error('Failed to verify pipeline jobs');
    return res.json();
  },

  // Discovery & URL import
  async searchDiscoveredJobs(
    query?: string,
    source?: string,
    adzunaAppId?: string,
    adzunaAppKey?: string,
    usOnly: boolean = true,
    location?: string,
    radius?: number,
    includeRemote: boolean = true,
    minSalary?: number,
    includeUndisclosedSalary: boolean = true,
    forceRefresh: boolean = false,
    track?: string
  ): Promise<DiscoveredJob[]> {
    const params = new URLSearchParams();
    if (query) params.append('query', query);
    if (source && source !== 'all') params.append('source', source);
    if (adzunaAppId) params.append('adzuna_app_id', adzunaAppId);
    if (adzunaAppKey) params.append('adzuna_app_key', adzunaAppKey);
    params.append('us_only', String(usOnly));
    if (location && location.trim()) params.append('location', location.trim());
    if (radius) params.append('radius', String(radius));
    params.append('include_remote', String(includeRemote));
    if (minSalary && minSalary > 0) params.append('min_salary', String(minSalary));
    params.append('include_undisclosed_salary', String(includeUndisclosedSalary));
    if (track && track !== 'either' && track !== 'all') params.append('track', track);
    if (forceRefresh) params.append('force_refresh', 'true');

    const res = await fetch(`${API_BASE}/discovery/search?${params.toString()}`);
    if (!res.ok) throw new Error('Failed to search jobs');
    return res.json();
  },

  async importJobUrl(url: string): Promise<Partial<Job>> {
    const res = await fetch(`${API_BASE}/discovery/import-url`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Import failed' }));
      throw new Error(err.detail || 'Failed to import from URL');
    }
    return res.json();
  },

  // Profile & Skills
  async getProfile(): Promise<Profile> {
    const res = await fetch(`${API_BASE}/profile`);
    if (!res.ok) throw new Error('Failed to fetch profile');
    return res.json();
  },

  async updateProfile(profile: Partial<Profile>): Promise<Profile> {
    const res = await fetch(`${API_BASE}/profile`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(profile),
    });
    if (!res.ok) throw new Error('Failed to update profile');
    return res.json();
  },

  async getSkills(): Promise<Skill[]> {
    const res = await fetch(`${API_BASE}/profile/skills`);
    if (!res.ok) throw new Error('Failed to fetch skills');
    return res.json();
  },

  async addSkill(name: string, category: string, proficiency: string): Promise<Skill> {
    const res = await fetch(`${API_BASE}/profile/skills`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, category, proficiency }),
    });
    if (!res.ok) throw new Error('Failed to add skill');
    return res.json();
  },

  async deleteSkill(id: number): Promise<void> {
    const res = await fetch(`${API_BASE}/profile/skills/${id}`, { method: 'DELETE' });
    if (!res.ok) throw new Error('Failed to delete skill');
  },

  // Search Profiles (Multi-Profile per-user search criteria & directives)
  async getSearchProfiles(): Promise<SearchProfile[]> {
    const res = await fetch(`${API_BASE}/search-profiles`);
    if (!res.ok) throw new Error('Failed to fetch search profiles');
    return res.json();
  },

  async createSearchProfile(profile: Omit<SearchProfile, 'id' | 'created_at' | 'updated_at'>): Promise<SearchProfile> {
    const res = await fetch(`${API_BASE}/search-profiles`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(profile),
    });
    if (!res.ok) throw new Error('Failed to create search profile');
    return res.json();
  },

  async updateSearchProfile(id: number, updates: Partial<SearchProfile>): Promise<SearchProfile> {
    const res = await fetch(`${API_BASE}/search-profiles/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(updates),
    });
    if (!res.ok) throw new Error('Failed to update search profile');
    return res.json();
  },

  async deleteSearchProfile(id: number): Promise<void> {
    const res = await fetch(`${API_BASE}/search-profiles/${id}`, { method: 'DELETE' });
    if (!res.ok) throw new Error('Failed to delete search profile');
  },

  async scorePipelineWithProfile(id: number): Promise<{ profile_id: number; profile_name: string; jobs_scored: number; jobs: Job[] }> {
    const res = await fetch(`${API_BASE}/search-profiles/${id}/score-pipeline`, { method: 'POST' });
    if (!res.ok) throw new Error('Failed to score pipeline with profile');
    return res.json();
  },

  async getDirectives(): Promise<{ companies: string[]; keywords: string[]; profiles_count: number }> {
    const res = await fetch(`${API_BASE}/directives`);
    if (!res.ok) throw new Error('Failed to fetch directives');
    return res.json();
  },

  // Assistant & Copilot
  async analyzeJobMatch(jobId: JobId): Promise<FitBreakdown> {
    const res = await fetch(`${API_BASE}/assistant/${jobId}/match`, { method: 'POST' });
    if (!res.ok) throw new Error('Failed to analyze match');
    return res.json();
  },

  async generateDocument(
    jobId: JobId,
    docType: string,
    tone: string = 'professional',
    customInstructions?: string,
    provider: string = 'template',
    apiKey?: string
  ): Promise<{ doc_type: string; content: string; provider_used: string }> {
    const res = await fetch(`${API_BASE}/assistant/${jobId}/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        doc_type: docType,
        tone,
        custom_instructions: customInstructions,
        provider,
        api_key: apiKey,
      }),
    });
    if (!res.ok) throw new Error('Failed to generate document');
    return res.json();
  },

  async getAutofillPayload(jobId: JobId): Promise<AutofillPayload> {
    const res = await fetch(`${API_BASE}/assistant/${jobId}/autofill-payload`);
    if (!res.ok) throw new Error('Failed to fetch autofill payload');
    return res.json();
  },

  async launchBrowserAssistant(jobId: JobId): Promise<{ success: boolean; message: string }> {
    const res = await fetch(`${API_BASE}/assistant/${jobId}/launch-browser`, { method: 'POST' });
    if (!res.ok) throw new Error('Failed to launch browser assistant');
    return res.json();
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
    const res = await fetch(`${API_BASE}/assistant/${jobId}/application-kit`, { method: 'POST' });
    if (!res.ok) throw new Error('Failed to generate application kit');
    return res.json();
  },

  async mintResumePacket(jobId: JobId): Promise<{
    slug: string;
    label: string;
    url: string;
    pdf_url: string;
  }> {
    const res = await fetch(`${API_BASE}/assistant/${jobId}/mint-packet`, { method: 'POST' });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Failed to mint packet' }));
      throw new Error(err.detail || 'Failed to mint packet');
    }
    return res.json();
  },

  async getResumeBlocks(): Promise<{
    count: number;
    blocks: { id: string; type: string; tags: string[]; title: string; content: string; priority: number }[];
  }> {
    const res = await fetch(`${API_BASE}/profile/resume-blocks`);
    if (!res.ok) throw new Error('Failed to chunk resume blocks');
    return res.json();
  },

  // Hadoku Scraper Worker & Corpus Sync
  async getScraperStatus(): Promise<{
    vault_key_configured: boolean;
    vault_key_source: string;
    resume_api: { online: boolean; status: number | null };
    jobplatform_api: { online: boolean; status: number | null };
    scraper_api: { online: boolean; active_targets: number };
  }> {
    const res = await fetch(`${API_BASE}/scraper/status`);
    if (!res.ok) throw new Error('Failed to fetch scraper status');
    return res.json();
  },

  async matchScraperCompanies(names: string[]): Promise<{
    results: {
      query: string;
      matched: boolean;
      ats: string | null;
      slug: string | null;
      company_name: string | null;
      n_jobs: number;
      sample_titles: string[];
      domain: string | null;
    }[];
  }> {
    const res = await fetch(`${API_BASE}/scraper/match-companies`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ names }),
    });
    if (!res.ok) throw new Error('Failed to match companies on scraper');
    return res.json();
  },

  async triggerScraperRun(): Promise<{ triggered: boolean; status_code?: number; error?: string }> {
    const res = await fetch(`${API_BASE}/scraper/trigger`, { method: 'POST' });
    if (!res.ok) throw new Error('Failed to trigger scraper');
    return res.json();
  },

  async syncScraperCorpus(limit: number = 40, minScore: number = 65): Promise<{
    fetched: number;
    inserted: number;
    skipped: number;
    profile_used: string;
  }> {
    const res = await fetch(`${API_BASE}/scraper/sync-corpus?limit=${limit}&min_score=${minScore}`, {
      method: 'POST',
    });
    if (!res.ok) throw new Error('Failed to sync scraper corpus');
    return res.json();
  },

  // Analytics
  async getMetrics(): Promise<Metrics> {
    const res = await fetch(`${API_BASE}/analytics/metrics`);
    if (!res.ok) throw new Error('Failed to fetch metrics');
    return res.json();
  },

  // Health & Live Reload Sync
  async getHealth(): Promise<{ status: string; service: string; boot_id?: string }> {
    const res = await fetch(`${API_BASE}/health`, { cache: 'no-store' });
    if (!res.ok) throw new Error('Health check failed');
    return res.json();
  },
};
