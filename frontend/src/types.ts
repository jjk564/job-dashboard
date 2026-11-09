/** hadoku's posting id: `<ats>_<board id>` (greenhouse_123), or manual_<hash> for one typed in. */
export type JobId = string;

export type JobStatus = 
  | 'TO_APPLY' 
  | 'APPLIED' 
  | 'INTERVIEWING' 
  | 'OFFER' 
  | 'REJECTED' 
  | 'ARCHIVED'
  | 'WISHLIST';

export type Priority = 'low' | 'medium' | 'high';

export type RoleTrack = 'ic' | 'manager' | 'unknown';
export type IcLevel = 'junior' | 'mid' | 'senior' | 'staff' | 'principal' | 'fellow';
export type ManagerLevel = 'manager' | 'senior_manager' | 'director' | 'vp' | 'cxo';
export type RoleLevel = IcLevel | ManagerLevel;
export type RoleDiscipline = 'eng' | 'adjacent' | 'unknown';

export interface SearchProfile {
  /** hadoku's profile id (a UUID, or 'default'). */
  id: string;
  user_id?: string;
  name: string;
  is_default: boolean;
  keywords: string[];
  target_companies: string[];
  track: 'ic' | 'manager' | 'either';
  levels: RoleLevel[];
  remote_pref: 'remote' | 'hybrid' | 'onsite' | 'any';
  location: string;
  radius_miles: number;
  min_salary?: number | null;
  include_undisclosed_salary: boolean;
  us_only: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface Activity {
  id: number;
  job_id: JobId;
  activity_type: string;
  title: string;
  details?: string;
  created_at?: string;
}

export interface TailoredDocument {
  id: number;
  job_id: JobId;
  doc_type: string;
  content: string;
  created_at?: string;
}

export interface FitBreakdown {
  score: number;
  matched_skills: string[];
  missing_skills: string[];
  detected_requirements: string[];
  role_track?: RoleTrack;
  role_level?: RoleLevel | null;
  score_breakdown?: {
    keyword_match: number;
    title_match: number;
    level_match: number;
    remote_match: number;
  };
  summary: string;
}

export interface Job {
  id: JobId;
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
  role_track?: RoleTrack;
  role_level?: RoleLevel | null;
  role_discipline?: RoleDiscipline;
  notes?: string;
  applied_at?: string;
  deadline?: string | null;
  /** hadoku's nightly scrape stopped seeing it on its board. */
  is_expired?: boolean;
  last_seen_at?: string | null;
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
  /** hadoku's id for the posting: adding it to the pipeline tracks this posting. */
  id?: JobId;
  /** 0–100 against the search profile, when one was searched with. */
  fit_score?: number;
  posted_date?: string;
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
  role_track?: RoleTrack;
  role_level?: RoleLevel | null;
  role_discipline?: RoleDiscipline;
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
