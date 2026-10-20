export type JobStatus = 
  | 'WISHLIST' 
  | 'TO_APPLY' 
  | 'APPLIED' 
  | 'INTERVIEWING' 
  | 'OFFER' 
  | 'REJECTED' 
  | 'ARCHIVED';

export type Priority = 'low' | 'medium' | 'high';

export interface Activity {
  id: number;
  job_id: number;
  activity_type: string;
  title: string;
  details?: string;
  created_at?: string;
}

export interface TailoredDocument {
  id: number;
  job_id: number;
  doc_type: string;
  content: string;
  created_at?: string;
}

export interface FitBreakdown {
  score: number;
  matched_skills: string[];
  missing_skills: string[];
  detected_requirements: string[];
  summary: string;
}

export interface Job {
  id: number;
  title: string;
  company: string;
  location?: string;
  workplace_type?: string;
  url?: string;
  salary_min?: number;
  salary_max?: number;
  salary_currency?: string;
  description?: string;
  requirements?: string;
  source?: string;
  status: JobStatus;
  priority: Priority;
  fit_score?: number;
  fit_breakdown?: FitBreakdown;
  notes?: string;
  applied_at?: string;
  deadline?: string | null;
  is_expired?: boolean;
  expired_at?: string | null;
  expired_reason?: string | null;
  contact_person?: string;
  contact_email?: string;
  created_at?: string;
  updated_at?: string;
  activities?: Activity[];
  tailored_documents?: TailoredDocument[];
}

export interface Profile {
  id?: number;
  full_name: string;
  email: string;
  phone: string;
  location: string;
  title: string;
  summary: string;
  linkedin_url: string;
  github_url: string;
  portfolio_url: string;
  work_authorization: string;
  desired_salary: string;
  notice_period: string;
  master_resume_text: string;
  updated_at?: string;
}

export interface Skill {
  id: number;
  name: string;
  category: string;
  proficiency: 'beginner' | 'intermediate' | 'expert';
}

export interface DiscoveredJob {
  title: string;
  company: string;
  location?: string;
  workplace_type?: string;
  url: string;
  salary_min?: number;
  salary_max?: number;
  salary_currency?: string;
  tags?: string[];
  description: string;
  source: string;
}

export interface Metrics {
  funnel: {
    total_tracked: number;
    wishlist: number;
    to_apply: number;
    applied: number;
    interviewing: number;
    offer: number;
    rejected: number;
    response_rate_percent: number;
    interview_rate_percent: number;
  };
  top_demanded_skills: { name: string; count: number }[];
  workplace_distribution: Record<string, number>;
}

export interface AutofillPayload {
  first_name: string;
  last_name: string;
  full_name: string;
  email: string;
  phone: string;
  location: string;
  linkedin_url: string;
  github_url: string;
  portfolio_url: string;
  work_authorization: string;
  desired_salary: string;
  notice_period: string;
  summary: string;
  cover_letter_snippet: string;
}
