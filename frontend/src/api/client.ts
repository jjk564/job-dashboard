import { Job, Profile, Skill, DiscoveredJob, Metrics, AutofillPayload, FitBreakdown } from '../types';

const API_BASE = '/api';

export const api = {
  // Jobs
  async getJobs(status?: string, priority?: string): Promise<Job[]> {
    const params = new URLSearchParams();
    if (status) params.append('status', status);
    if (priority) params.append('priority', priority);
    const res = await fetch(`${API_BASE}/jobs?${params.toString()}`);
    if (!res.ok) throw new Error('Failed to fetch jobs');
    return res.json();
  },

  async getJob(id: number): Promise<Job> {
    const res = await fetch(`${API_BASE}/jobs/${id}`);
    if (!res.ok) throw new Error('Failed to fetch job');
    return res.json();
  },

  async createJob(job: Partial<Job>): Promise<Job> {
    const res = await fetch(`${API_BASE}/jobs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(job),
    });
    if (!res.ok) throw new Error('Failed to create job');
    return res.json();
  },

  async updateJob(id: number, updates: Partial<Job>): Promise<Job> {
    const res = await fetch(`${API_BASE}/jobs/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(updates),
    });
    if (!res.ok) throw new Error('Failed to update job');
    return res.json();
  },

  async deleteJob(id: number): Promise<void> {
    const res = await fetch(`${API_BASE}/jobs/${id}`, { method: 'DELETE' });
    if (!res.ok) throw new Error('Failed to delete job');
  },

  async addActivity(jobId: number, activity: { activity_type: string; title: string; details?: string }): Promise<void> {
    const res = await fetch(`${API_BASE}/jobs/${jobId}/activities`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(activity),
    });
    if (!res.ok) throw new Error('Failed to add activity');
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
    includeRemote: boolean = true
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

  // Assistant & Copilot
  async analyzeJobMatch(jobId: number): Promise<FitBreakdown> {
    const res = await fetch(`${API_BASE}/assistant/${jobId}/match`, { method: 'POST' });
    if (!res.ok) throw new Error('Failed to analyze match');
    return res.json();
  },

  async generateDocument(
    jobId: number,
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

  async getAutofillPayload(jobId: number): Promise<AutofillPayload> {
    const res = await fetch(`${API_BASE}/assistant/${jobId}/autofill-payload`);
    if (!res.ok) throw new Error('Failed to fetch autofill payload');
    return res.json();
  },

  async launchBrowserAssistant(jobId: number): Promise<{ success: boolean; message: string }> {
    const res = await fetch(`${API_BASE}/assistant/${jobId}/launch-browser`, { method: 'POST' });
    if (!res.ok) throw new Error('Failed to launch browser assistant');
    return res.json();
  },

  // Analytics
  async getMetrics(): Promise<Metrics> {
    const res = await fetch(`${API_BASE}/analytics/metrics`);
    if (!res.ok) throw new Error('Failed to fetch metrics');
    return res.json();
  },
};
