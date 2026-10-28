import React, { useState, useEffect, useMemo, useRef } from 'react';
import { 
  Search, 
  Sparkles, 
  Building2, 
  MapPin, 
  DollarSign, 
  ExternalLink, 
  Plus, 
  Check, 
  RefreshCw,
  Compass,
  Filter,
  X,
  Briefcase,
  Code,
  Globe,
  SlidersHorizontal,
  ChevronDown,
  ChevronUp,
  ChevronLeft,
  ChevronRight,
  EyeOff,
  Eye,
  Undo2,
  Navigation
} from 'lucide-react';
import { DiscoveredJob, Job } from '../../types';
import { api } from '../../api/client';
import { checkJobLocationMatchesRange } from '../../utils/locationMatcher';

export interface JobDiscoveryProps {
  pipelineJobs?: Job[];
  onJobAdded: (job: Job) => void;
  onOpenSettings?: (tab?: 'ai' | 'hidden') => void;
}

export const normalizeUrl = (rawUrl?: string): string => {
  if (!rawUrl) return '';
  try {
    const parsed = new URL(rawUrl);
    const keepParams = new URLSearchParams();
    for (const [key, val] of parsed.searchParams.entries()) {
      if (
        !['utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content', 'ref', 'source', 'from', 'fbclid', 'gclid', 'jid'].includes(key.toLowerCase())
      ) {
        keepParams.append(key, val);
      }
    }
    const cleanSearch = keepParams.toString() ? `?${keepParams.toString()}` : '';
    return `${parsed.hostname}${parsed.pathname.replace(/\/+$/, '')}${cleanSearch}`.toLowerCase();
  } catch {
    return rawUrl.replace(/^https?:\/\//i, '').replace(/\/+$/, '').toLowerCase();
  }
};

export const normalizeJobText = (text?: string): string => {
  return (text || '')
    .toLowerCase()
    .replace(/[^\w\s]/g, '')
    .replace(/\s+/g, ' ')
    .trim();
};

export const findMatchingPipelineJob = (
  discovered: DiscoveredJob,
  pipelineJobs: Job[]
): Job | undefined => {
  if (!pipelineJobs || pipelineJobs.length === 0) return undefined;
  const discUrlNorm = normalizeUrl(discovered.url);
  const discTitleNorm = normalizeJobText(discovered.title);
  const discCompNorm = normalizeJobText(discovered.company);

  return pipelineJobs.find((pj) => {
    // 1. Direct or normalized URL match
    if (pj.url) {
      if (pj.url === discovered.url) return true;
      const pjUrlNorm = normalizeUrl(pj.url);
      if (pjUrlNorm && discUrlNorm && pjUrlNorm === discUrlNorm) return true;
    }

    // 2. Exact Title + Company match
    const pjTitleNorm = normalizeJobText(pj.title);
    const pjCompNorm = normalizeJobText(pj.company);
    if (
      discTitleNorm &&
      pjTitleNorm &&
      discCompNorm &&
      pjCompNorm &&
      discTitleNorm === pjTitleNorm &&
      discCompNorm === pjCompNorm
    ) {
      return true;
    }

    // 3. Substring Title match within same company
    if (discCompNorm && pjCompNorm && discCompNorm === pjCompNorm) {
      if (
        (discTitleNorm.length > 5 && pjTitleNorm.includes(discTitleNorm)) ||
        (pjTitleNorm.length > 5 && discTitleNorm.includes(pjTitleNorm))
      ) {
        return true;
      }
    }

    return false;
  });
};

export const PIPELINE_STATUS_LABELS: Record<string, string> = {
  TO_APPLY: 'To Apply',
  APPLIED: 'Applied',
  INTERVIEWING: 'Interviewing',
  OFFER: 'Offer',
  REJECTED: 'Rejected',
  ARCHIVED: 'Archived',
  WISHLIST: 'To Apply',
};

export const parseSalaryStringToAnnual = (str: string): number | null => {
  if (!str) return null;
  const clean = str.trim().toLowerCase();

  // Hourly pattern e.g. $35/hr, $35 / hour, 35/hr
  const hourlyMatch = clean.match(/\$?(\d+(?:\.\d{2})?)\s*(?:\/|\s*(?:per|an)\s*)?(?:hr|hour)\b/);
  if (hourlyMatch) {
    const num = parseFloat(hourlyMatch[1]);
    if (!isNaN(num) && num > 0) return Math.round(num * 2080);
  }

  // Range pattern e.g. $80k - $120k or $80,000 - $120,000
  const rangeMatch = clean.match(/\$?(\d+(?:,\d{3})*(?:\.\d+)?)\s*k?\s*(?:-|to)\s*\$?(\d+(?:,\d{3})*(?:\.\d+)?)\s*(k?)/);
  if (rangeMatch) {
    let num = parseFloat(rangeMatch[1].replace(/,/g, ''));
    if (rangeMatch[3] === 'k' || clean.includes('k')) {
      if (num < 1000) num *= 1000;
    }
    if (!isNaN(num) && num > 0) {
      if (num < 200) num *= 2080;
      return Math.round(num);
    }
  }

  // Single annual figure e.g. $85k, 85000, $85,000
  const singleMatch = clean.match(/\$?(\d+(?:,\d{3})*(?:\.\d+)?)\s*(k?)/);
  if (singleMatch) {
    let num = parseFloat(singleMatch[1].replace(/,/g, ''));
    if (singleMatch[2] === 'k' || clean.includes('k')) {
      if (num < 1000) num *= 1000;
    }
    if (!isNaN(num) && num > 0) {
      if (num < 200) num *= 2080;
      return Math.round(num);
    }
  }

  return null;
};

export const formatSalaryBadge = (
  min?: number,
  max?: number,
  currency = 'USD',
  rateType: 'annual' | 'hourly' = 'annual'
): string | null => {
  if (!min && !max) return null;

  if (rateType === 'hourly') {
    const hMin = min ? Math.round(min / 2080) : null;
    const hMax = max ? Math.round(max / 2080) : null;
    if (hMin && hMax && hMin !== hMax) {
      return `$${hMin} - $${hMax}/hr`;
    }
    if (hMin) return `$${hMin}/hr+`;
    if (hMax) return `Up to $${hMax}/hr`;
  } else {
    const kMin = min ? Math.round(min / 1000) : null;
    const kMax = max ? Math.round(max / 1000) : null;
    if (kMin && kMax && kMin !== kMax) {
      return `$${kMin}k - $${kMax}k`;
    }
    if (kMin) return `$${kMin}k+`;
    if (kMax) return `Up to $${kMax}k`;
  }
  return null;
};

export interface FilterOption {
  id: string;
  label: string;
  category: 'experience' | 'language' | 'role' | 'workplace';
}

export interface FilterGroupConfig {
  id: 'experience' | 'language' | 'role' | 'workplace';
  title: string;
  icon: React.ReactNode;
  options: FilterOption[];
}

const FILTER_GROUPS: FilterGroupConfig[] = [
  {
    id: 'experience',
    title: 'Experience Level',
    icon: <Briefcase className="w-4 h-4 text-purple-400" />,
    options: [
      { id: 'junior', label: 'Junior / Entry', category: 'experience' },
      { id: 'mid', label: 'Mid-Level', category: 'experience' },
      { id: 'senior', label: 'Senior', category: 'experience' },
      { id: 'lead', label: 'Lead / Staff', category: 'experience' },
      { id: 'manager', label: 'Manager / Director', category: 'experience' },
    ],
  },
  {
    id: 'language',
    title: 'Languages & Core Tech',
    icon: <Code className="w-4 h-4 text-emerald-400" />,
    options: [
      { id: 'python', label: 'Python', category: 'language' },
      { id: 'sql', label: 'SQL', category: 'language' },
      { id: 'golang', label: 'Go / Golang', category: 'language' },
      { id: 'active_directory', label: 'Active Directory / IAM', category: 'language' },
      { id: 'm365', label: 'Microsoft 365 / Entra', category: 'language' },
      { id: 'servicenow', label: 'ServiceNow / CRM', category: 'language' },
      { id: 'linux_admin', label: 'Linux / Bash', category: 'language' },
      { id: 'networking', label: 'TCP/IP & VPN', category: 'language' },
      { id: 'javascript', label: 'JavaScript', category: 'language' },
      { id: 'typescript', label: 'TypeScript', category: 'language' },
      { id: 'react', label: 'React', category: 'language' },
      { id: 'nodejs', label: 'Node.js', category: 'language' },
      { id: 'aws', label: 'AWS / Cloud', category: 'language' },
      { id: 'java', label: 'Java', category: 'language' },
      { id: 'csharp', label: 'C# / .NET', category: 'language' },
      { id: 'cpp', label: 'C / C++', category: 'language' },
      { id: 'rust', label: 'Rust', category: 'language' },
    ],
  },
  {
    id: 'role',
    title: 'Role & Discipline',
    icon: <Compass className="w-4 h-4 text-cyan-400" />,
    options: [
      { id: 'it_support', label: 'IT Support & Help Desk', category: 'role' },
      { id: 'sysadmin', label: 'Systems Administration', category: 'role' },
      { id: 'backend', label: 'Backend', category: 'role' },
      { id: 'data_ai', label: 'Data & ETL / AI', category: 'role' },
      { id: 'network', label: 'Network & Infrastructure', category: 'role' },
      { id: 'security', label: 'Cybersecurity / SOC', category: 'role' },
      { id: 'fullstack', label: 'Full Stack', category: 'role' },
      { id: 'frontend', label: 'Frontend', category: 'role' },
      { id: 'devops', label: 'DevOps / SRE', category: 'role' },
      { id: 'qa', label: 'QA / Testing', category: 'role' },
      { id: 'mobile', label: 'Mobile', category: 'role' },
    ],
  },
  {
    id: 'workplace',
    title: 'Workplace & Type',
    icon: <Globe className="w-4 h-4 text-amber-400" />,
    options: [
      { id: 'remote', label: 'Remote', category: 'workplace' },
      { id: 'hybrid', label: 'Hybrid', category: 'workplace' },
      { id: 'onsite', label: 'On-site', category: 'workplace' },
      { id: 'fulltime', label: 'Full-Time', category: 'workplace' },
      { id: 'contract', label: 'Contract', category: 'workplace' },
      { id: 'internship', label: 'Internship', category: 'workplace' },
    ],
  },
];

const ALL_FILTER_OPTIONS: FilterOption[] = FILTER_GROUPS.flatMap((g) => g.options);

const SOURCE_FILTERS = [
  { id: 'all', label: 'All Sources' },
  { id: 'bigtech', label: 'Big Tech (Google, MSFT, AMZN...)' },
  { id: 'company_boards', label: 'Top Tech ATS (OpenAI, Stripe...)' },
  { id: 'simplify', label: 'SimplifyJobs (Entry-Level)' },
  { id: 'linkedin', label: 'LinkedIn' },
  { id: 'glassdoor', label: 'Glassdoor' },
  { id: 'indeed', label: 'Indeed' },
  { id: 'ziprecruiter', label: 'ZipRecruiter' },
  { id: 'themuse', label: 'The Muse' },
  { id: 'arbeitnow', label: 'Arbeitnow' },
  { id: 'jobicy', label: 'Jobicy' },
  { id: 'weworkremotely', label: 'We Work Remotely' },
  { id: 'himalayas', label: 'Himalayas' },
  { id: 'hackernews', label: 'HN "Who is Hiring?"' },
  { id: 'remoteok', label: 'RemoteOK' },
  { id: 'adzuna', label: 'Adzuna API' },
];

// Helper to detect explicit entry-level / junior job titles
const hasExplicitJuniorTitle = (title: string): boolean => {
  const t = (title || '').toLowerCase();
  if (
    /\b(junior|jr\.?|entry[\s-]level|new\s+grad(?:uate)?|recent\s+grad(?:uate)?|fresh\s+grad(?:uate)?|early[\s-]career|apprentice|apprenticeship|intern|internship|trainee|rotational|campus|university\s+grad(?:uate)?|college\s+grad(?:uate)?)\b/i.test(t)
  ) {
    return true;
  }
  if (
    /\bassociate\b/i.test(t) &&
    !/\b(director|vp|vice\s+president|partner|principal|counsel|dean|professor|budtender|retail|store|warehouse|cashier)\b/i.test(t) &&
    /\b(developer|engineer|engineering|programmer|software|web|frontend|backend|full[\s-]stack|data|analyst|qa|devops|cloud|cyber|security|it|systems|tech|technology|technical|application|support|scientist|consultant|designer|product)\b/i.test(t)
  ) {
    return true;
  }
  if (
    /\b(software\s+engineer|developer|engineer|analyst|programmer|specialist|technician|administrator|consultant|scientist|designer|qa|sdet|devops|support|swe|sde)\s*(?:-\s*)?(?:i|1)\b/i.test(t) ||
    /\b(?:level|tier)\s*(?:i|1)\b/i.test(t)
  ) {
    return true;
  }
  return false;
};

// Helper to detect senior, lead, staff, principal, or executive titles
const isSeniorOrStaffTitle = (title: string): boolean => {
  const t = (title || '').toLowerCase();
  if (
    /\b(staff|senior|sr\.?|principal|lead|tech\s+lead|team\s+lead|manager|director|vp|vice\s+president|head\s+of|distinguished|fellow|partner|chief|cto|cio)\b/i.test(t) ||
    /\b(?:enterprise|principal|senior|sr\.?|lead|chief|staff|head)\s+(?:[\w-]+\s+)?architect\b/i.test(t)
  ) {
    if (!/\b(junior|jr\.?|entry[\s-]level|intern|apprentice)\b/i.test(t)) {
      return true;
    }
  }
  if (hasExplicitJuniorTitle(t)) {
    return false;
  }
  return (
    /\b(iii|iv|v|vi)\b/i.test(t) ||
    /\b(?:engineer|developer|programmer|analyst|specialist|scientist|technician|level|tier|swe|sde)\s*(?:-\s*)?(?:3|4|5|6)\b/i.test(t)
  );
};

// Strip company history blurbs and age requirements before checking candidate experience
const cleanExperienceText = (desc: string): string => {
  return (desc || '')
    .toLowerCase()
    .replace(/\b(?:must\s+be\s+|at\s+least\s+)?\d{2}\s*(?:years?|yrs?)\s+of\s+age\b/gi, '')
    .replace(
      /\b(?:company|team|organization|firm|business|industry|leader|legacy|history|combined)\s+(?:with|of|for|celebrating|bringing)\s+(?:more\s+than\s+|over\s+)?\d+\+?\s*(?:years?|yrs?)\b/gi,
      ''
    )
    .replace(/\b(?:more\s+than|over)\s+(?:1[5-9]|[2-9]\d)\s*\+?\s*(?:years?|yrs?)\s+(?:of\s+)?(?:experience|exp)?\b/gi, '');
};

// Helper to detect high experience requirements (e.g. 6+, 7+, 8+, 10+, 12+ years)
const requiresSeniorExperience = (desc: string): boolean => {
  const t = cleanExperienceText(desc);
  if (
    /\b(?:(?:minimum|at\s+least|over|requires?)\s+(?:of\s+)?)?([6-9]|1[0-5])\s*\+?\s*(?:(?:to|-|–|—)\s*\d+\s*)?(?:years?|yrs?)\s+(?:of\s+)?(?:[\w/-]+\s+){0,3}?(?:experience|exp|hands-on|background|development|engineering|programming)\b/i.test(t)
  ) {
    if (!/\b[0-3]\s*(?:to|-|–|—)\s*[4-7]\s*(?:years?|yrs?)\b/i.test(t)) {
      return true;
    }
  }
  if (/\b(6-8|6-10|7-10|8-10|8-12|10-15)\s*(?:years?|yrs?)\b/i.test(t)) {
    return true;
  }
  return false;
};

// Helper to detect mid or senior experience requirements (4+, 5+ years) that disqualify entry level
const requiresMidOrSeniorExperience = (desc: string): boolean => {
  const t = cleanExperienceText(desc);
  if (
    /\b(?:(?:minimum|at\s+least|over|requires?)\s+(?:of\s+)?)?([4-9]|1[0-5])\s*\+?\s*(?:(?:to|-|–|—)\s*\d+\s*)?(?:years?|yrs?)\s+(?:of\s+)?(?:[\w/-]+\s+){0,3}?(?:experience|exp|hands-on|background|development|engineering|programming)\b/i.test(t)
  ) {
    if (!/\b[0-2]\s*(?:to|-|–|—)\s*[1-4]\s*(?:years?|yrs?)\b/i.test(t)) {
      return true;
    }
  }
  if (/\b(4-6|4-7|5-7|5-8)\s*(?:years?|yrs?)\b/i.test(t)) {
    return true;
  }
  return requiresSeniorExperience(desc);
};

const matchesOption = (optionId: string, fullText: string, job: DiscoveredJob): boolean => {
  const loc = (job.location || '').toLowerCase();
  const title = (job.title || '').toLowerCase();
  const workplace = (job.workplace_type || '').toLowerCase();

  switch (optionId) {
    // Experience Level
    case 'junior': {
      // 1. Strict Exclusions for Entry Level:
      // A) Title cannot be senior, staff, lead, principal, manager, architect, Level 3+
      if (isSeniorOrStaffTitle(title)) {
        return false;
      }
      // B) Explicit Mid-Level / Level II / 2 in title is mid-level, not junior
      if (
        !hasExplicitJuniorTitle(title) &&
        (/\b(mid[\s-]level|intermediate|ii)\b/i.test(title) ||
          /\b(?:engineer|developer|programmer|analyst|specialist|scientist|technician|level|tier|swe|sde)\s*(?:-\s*)?2\b/i.test(title))
      ) {
        return false;
      }

      // 2. Explicit Junior Title Match (trusted immediately unless senior title)
      if (hasExplicitJuniorTitle(title)) {
        return true;
      }

      // 3. Description & Salary Exclusions for untitled roles:
      if (requiresMidOrSeniorExperience(fullText)) {
        return false;
      }
      if ((job.salary_min && job.salary_min >= 160000) || (job.salary_max && job.salary_max >= 185000)) {
        return false;
      }

      // Filter out mentorship phrasing false-positives (e.g., 'mentor junior developers')
      const cleanDesc = fullText
        .replace(
          /\b(?:mentor|mentoring|mentors|lead|leading|leads|coach|coaching|coaches|supervise|supervising|guide|guiding)\s+(?:and\s+\w+\s+)?(?:to\s+)?(?:junior|entry|intern|early[\s-]career)\b/gi,
          ''
        )
        .replace(/\bgraduate\s+degree\b/gi, ''); // "graduate degree" means MS/PhD, not entry-level

      if (
        /\b(junior|jr\.?|entry[\s-]level|entrylevel|new\s+grad(?:uate)?|recent\s+grad(?:uate)?|fresh\s+grad(?:uate)?|early[\s-]career|earlycareer|apprentice|apprenticeship|internship|trainee|campus\s+hire|rotational\s+program|university\s+grad(?:uate)?|college\s+grad(?:uate)?|bootcamp)\b/i.test(
          cleanDesc
        ) ||
        /\b(software\s+engineer|developer|engineer|analyst|programmer|specialist|technician)\s+(?:i|1)\b/i.test(cleanDesc) ||
        /\b(?:level|tier)\s+(?:i|1)\b/i.test(cleanDesc) ||
        /\b[0-2]\s*(?:to|-|–|—)\s*[1-3]\s*(?:years?|yrs?)\b/i.test(cleanDesc) ||
        /\b[0-2]\s*\+?\s*(?:years?|yrs?)\s+(?:of\s+)?(?:[\w/-]+\s+){0,2}?(?:experience|exp|hands-on|development|engineering)\b/i.test(
          cleanDesc
        ) ||
        /\b(?:minimum|at\s+least|up\s+to|under|less\s+than)\s+(?:of\s+)?[1-2]\s*(?:years?|yrs?)\b/i.test(cleanDesc) ||
        cleanDesc.includes('no experience required') ||
        cleanDesc.includes('no prior experience') ||
        cleanDesc.includes('on-the-job training') ||
        cleanDesc.includes('on-job-training')
      ) {
        return true;
      }

      // Entry-level compensation band signal when job title is clearly a technical/software role
      const isTechTitle =
        /\b(developer|engineer|programmer|software|web|frontend|front-end|backend|back-end|full[\s-]stack|data|analyst|qa|devops|cloud|cyber|security|it|systems|network|ai|ml)\b/i.test(
          title
        );
      if (isTechTitle) {
        if (job.salary_max && job.salary_max >= 45000 && job.salary_max <= 95000) {
          return true;
        }
        if (
          job.salary_min &&
          job.salary_min >= 45000 &&
          job.salary_min <= 85000 &&
          (!job.salary_max || job.salary_max <= 105000)
        ) {
          return true;
        }
      }

      return false;
    }

    case 'mid': {
      // 1. Strict Exclusions for Mid Level:
      // A) Title cannot be senior, staff, lead, principal, manager, Level 3+
      if (isSeniorOrStaffTitle(title)) {
        return false;
      }
      // B) Title cannot be junior, entry, intern
      if (/\b(junior|jr\.?|entry|intern|internship|apprentice)\b/i.test(title)) {
        return false;
      }
      // C) Cannot require 6+, 7+, 8+, 10+ years senior experience (unless it also explicitly accepts 2-4 or 3-5 years)
      if (requiresSeniorExperience(fullText)) {
        const hasMidExpRequirement = /\b([1-4])\+?\s*(?:(?:to|-|–|—)\s*[3-5]\s*)?(?:years?|yrs?)\s+(?:of\s+)?(?:[\w/-]+\s+){0,3}?(?:experience|exp|hands-on|background)\b/i.test(fullText);
        if (!hasMidExpRequirement) {
          return false;
        }
      }
      // D) High salary ceiling for mid-level:
      // Top-tier companies (OpenAI, Stripe, Datadog) pay mid-level Solutions Engineers $180k-$260k base.
      // Only reject if starting salary is strictly executive level (e.g. >= $285k)
      if (job.salary_min && job.salary_min >= 285000 && !/\b(mid|intermediate|ii|2)\b/i.test(title)) {
        return false;
      }

      // 2. Positive Matching:
      return (
        fullText.includes('mid-level') ||
        fullText.includes('mid level') ||
        fullText.includes('intermediate') ||
        fullText.includes('2-5 years') ||
        fullText.includes('3-5 years') ||
        fullText.includes('2-4 years') ||
        fullText.includes('3-6 years') ||
        /\b(ii|2)\b/i.test(title) ||
        (!isSeniorOrStaffTitle(title) && !/\b(junior|jr\.?|entry|intern|apprentice)\b/i.test(title))
      );
    }

    case 'senior': {
      return (
        title.includes('senior') ||
        /\bsr\.?\b/i.test(title) ||
        fullText.includes('senior engineer') ||
        fullText.includes('senior developer') ||
        fullText.includes('5+ years') ||
        fullText.includes('6+ years') ||
        fullText.includes('7+ years') ||
        fullText.includes('8+ years') ||
        fullText.includes('10+ years') ||
        requiresSeniorExperience(fullText)
      );
    }

    case 'lead': {
      return (
        title.includes('lead') ||
        title.includes('staff') ||
        title.includes('principal') ||
        title.includes('architect') ||
        title.includes('distinguished') ||
        fullText.includes('tech lead') ||
        fullText.includes('team lead') ||
        fullText.includes('staff engineer') ||
        fullText.includes('principal engineer')
      );
    }

    case 'manager': {
      return (
        title.includes('manager') ||
        title.includes('director') ||
        title.includes('vp') ||
        title.includes('head of') ||
        fullText.includes('engineering manager')
      );
    }

    // Languages & Core Tech
    case 'python':
      return (
        fullText.includes('python') ||
        fullText.includes('django') ||
        fullText.includes('fastapi') ||
        fullText.includes('flask') ||
        fullText.includes('pytorch')
      );
    case 'javascript':
      return fullText.includes('javascript') || /\bjs\b/i.test(fullText);
    case 'typescript':
      return fullText.includes('typescript') || /\bts\b/i.test(fullText);
    case 'react':
      return fullText.includes('react') || fullText.includes('next.js') || fullText.includes('nextjs');
    case 'nodejs':
      return (
        fullText.includes('node.js') ||
        fullText.includes('nodejs') ||
        /\bnode\b/i.test(fullText) ||
        fullText.includes('express')
      );
    case 'golang':
      return fullText.includes('golang') || /\bgo\b/i.test(title) || /\bgolang\b/i.test(fullText);
    case 'java':
      return (/\bjava\b/i.test(fullText) && !fullText.includes('javascript')) || fullText.includes('spring boot');
    case 'csharp':
      return (
        fullText.includes('c#') ||
        fullText.includes('.net') ||
        fullText.includes('dotnet') ||
        fullText.includes('csharp')
      );
    case 'cpp':
      return fullText.includes('c++') || fullText.includes('cpp') || /\bc\b/i.test(title);
    case 'rust':
      return /\brust\b/i.test(fullText) || fullText.includes('cargo');
    case 'sql':
      return (
        fullText.includes('sql') ||
        fullText.includes('postgres') ||
        fullText.includes('postgresql') ||
        fullText.includes('mysql') ||
        fullText.includes('database')
      );
    case 'aws':
      return (
        fullText.includes('aws') ||
        fullText.includes('cloud') ||
        fullText.includes('azure') ||
        fullText.includes('gcp') ||
        fullText.includes('kubernetes') ||
        fullText.includes('terraform')
      );
    case 'active_directory':
      return (
        fullText.includes('active directory') ||
        fullText.includes('azure ad') ||
        fullText.includes('entra') ||
        fullText.includes('ldap') ||
        fullText.includes('identity') ||
        fullText.includes('iam')
      );
    case 'm365':
      return (
        fullText.includes('m365') ||
        fullText.includes('microsoft 365') ||
        fullText.includes('office 365') ||
        fullText.includes('exchange') ||
        fullText.includes('intune') ||
        fullText.includes('teams')
      );
    case 'servicenow':
      return (
        fullText.includes('servicenow') ||
        fullText.includes('dynamics 365') ||
        fullText.includes('dynamics') ||
        fullText.includes('ticketing') ||
        fullText.includes('itsm') ||
        fullText.includes('jira service')
      );
    case 'linux_admin':
      return (
        fullText.includes('linux') ||
        fullText.includes('ubuntu') ||
        fullText.includes('debian') ||
        fullText.includes('bash') ||
        fullText.includes('red hat') ||
        fullText.includes('centos') ||
        fullText.includes('shell')
      );
    case 'networking':
      return (
        fullText.includes('tcp/ip') ||
        fullText.includes('vpn') ||
        fullText.includes('dns') ||
        fullText.includes('dhcp') ||
        fullText.includes('lan/wan') ||
        fullText.includes('lan') ||
        fullText.includes('wan') ||
        fullText.includes('firewall') ||
        fullText.includes('wi-fi') ||
        fullText.includes('wifi') ||
        fullText.includes('router') ||
        fullText.includes('switch')
      );

    // Role & Discipline
    case 'it_support':
      return (
        fullText.includes('it support') ||
        fullText.includes('technical support') ||
        fullText.includes('tech support') ||
        fullText.includes('help desk') ||
        fullText.includes('helpdesk') ||
        fullText.includes('desktop support') ||
        fullText.includes('service desk') ||
        fullText.includes('field technician') ||
        fullText.includes('support specialist') ||
        fullText.includes('it technician') ||
        fullText.includes('endpoint support')
      );
    case 'sysadmin':
      return (
        fullText.includes('sysadmin') ||
        fullText.includes('systems administrator') ||
        fullText.includes('system administrator') ||
        fullText.includes('systems admin') ||
        fullText.includes('system admin') ||
        fullText.includes('endpoint administrator') ||
        fullText.includes('it administrator') ||
        fullText.includes('windows administrator')
      );
    case 'network':
      return (
        fullText.includes('network') ||
        fullText.includes('noc') ||
        fullText.includes('lan/wan') ||
        fullText.includes('cisco') ||
        fullText.includes('firewall') ||
        fullText.includes('router') ||
        fullText.includes('switch') ||
        fullText.includes('dns') ||
        fullText.includes('dhcp') ||
        fullText.includes('vpn')
      );
    case 'fullstack':
      return fullText.includes('fullstack') || fullText.includes('full-stack') || fullText.includes('full stack');
    case 'frontend':
      return (
        fullText.includes('frontend') ||
        fullText.includes('front-end') ||
        fullText.includes('front end') ||
        fullText.includes('react') ||
        fullText.includes('vue') ||
        fullText.includes('angular') ||
        fullText.includes('ui')
      );
    case 'backend':
      return (
        fullText.includes('backend') ||
        fullText.includes('back-end') ||
        fullText.includes('back end') ||
        fullText.includes('api') ||
        fullText.includes('server') ||
        fullText.includes('microservices')
      );
    case 'devops':
      return (
        fullText.includes('devops') ||
        fullText.includes('sre') ||
        fullText.includes('infrastructure') ||
        fullText.includes('cloud engineer') ||
        fullText.includes('platform engineer') ||
        fullText.includes('ci/cd') ||
        fullText.includes('kubernetes')
      );
    case 'data_ai':
      return (
        fullText.includes('data') ||
        fullText.includes('machine learning') ||
        fullText.includes('ml') ||
        fullText.includes('ai') ||
        fullText.includes('data engineer') ||
        fullText.includes('data scientist') ||
        fullText.includes('llm')
      );
    case 'mobile':
      return (
        fullText.includes('mobile') ||
        fullText.includes('ios') ||
        fullText.includes('android') ||
        fullText.includes('react native') ||
        fullText.includes('flutter') ||
        fullText.includes('swift') ||
        fullText.includes('kotlin')
      );
    case 'security':
      return (
        fullText.includes('security') ||
        fullText.includes('cyber') ||
        fullText.includes('infosec') ||
        fullText.includes('appsec')
      );
    case 'qa':
      return (
        fullText.includes('qa') ||
        fullText.includes('quality assurance') ||
        fullText.includes('test automation') ||
        fullText.includes('testing') ||
        fullText.includes('sdet')
      );

    // Workplace & Type
    case 'remote':
      if (workplace === 'hybrid' || workplace === 'onsite' || /hybrid|onsite|on-site|in-office/i.test(loc + ' ' + title)) {
        return false;
      }
      return (
        workplace === 'remote' ||
        loc.includes('remote') ||
        title.includes('remote') ||
        fullText.includes('work from home') ||
        fullText.includes('wfh') ||
        fullText.includes('anywhere') ||
        fullText.includes('telecommute') ||
        Boolean(job.tags && job.tags.some((t) => t.toLowerCase().includes('remote')))
      );
    case 'hybrid':
      return (
        workplace === 'hybrid' ||
        loc.includes('hybrid') ||
        title.includes('hybrid') ||
        fullText.includes('flexible')
      );
    case 'onsite':
      return (
        workplace === 'onsite' ||
        workplace === 'in-office' ||
        (!loc.includes('remote') && !title.includes('remote'))
      );
    case 'fulltime':
      return (
        fullText.includes('full-time') ||
        fullText.includes('fulltime') ||
        fullText.includes('permanent')
      );
    case 'contract':
      return (
        fullText.includes('contract') ||
        fullText.includes('freelance') ||
        fullText.includes('contractor') ||
        fullText.includes('1099') ||
        fullText.includes('c2c')
      );
    case 'internship':
      return (
        fullText.includes('intern') ||
        fullText.includes('internship') ||
        fullText.includes('co-op')
      );

    default:
      return fullText.includes(optionId.toLowerCase());
  }
};

const FILTER_SEARCH_TERMS: Record<string, string> = {
  // Experience
  junior: 'junior',
  mid: 'mid-level',
  senior: 'senior',
  lead: 'lead',
  manager: 'manager',

  // Workplace
  remote: 'remote',
  hybrid: 'hybrid',
  onsite: 'onsite',
  contract: 'contract',
  internship: 'intern',
  fulltime: 'full-time',

  // Role
  it_support: 'it support',
  sysadmin: 'systems administrator',
  backend: 'backend developer',
  data_ai: 'data pipeline',
  network: 'network technician',
  security: 'cybersecurity',
  fullstack: 'full stack',
  frontend: 'frontend',
  devops: 'devops',
  mobile: 'mobile',
  qa: 'qa',

  // Tech / Language
  python: 'python',
  sql: 'sql',
  golang: 'golang',
  active_directory: 'active directory',
  m365: 'microsoft 365',
  servicenow: 'servicenow',
  linux_admin: 'linux',
  networking: 'network',
  javascript: 'javascript',
  typescript: 'typescript',
  react: 'react',
  nodejs: 'nodejs',
  java: 'java',
  csharp: 'c#',
  cpp: 'c++',
  rust: 'rust',
  aws: 'aws',
};

const getEffectiveSearchQuery = (
  customQuery: string,
  activeFilterIds: string[],
  track: 'all' | 'software' | 'it_admin' = 'all'
): string => {
  const trimmed = customQuery.trim();
  // When a user provides an explicit search query (e.g. "Solutions Engineer"), use that pure term
  // for upstream board search engines so queries aren't polluted with experience terms like "junior"
  // which causes external scrapers (Indeed, LinkedIn, Glassdoor, ZipRecruiter) to return 0 or very few results.
  if (trimmed) {
    return trimmed;
  }

  const parts: string[] = [];

  // 1. Experience keywords
  const expFilters = activeFilterIds.filter((id) =>
    ['junior', 'mid', 'senior', 'lead', 'manager'].includes(id)
  );
  if (expFilters.length > 0) {
    parts.push(FILTER_SEARCH_TERMS[expFilters[0]] || expFilters[0]);
  }

  // 2. Tech / Language keywords
  const langFilters = activeFilterIds.filter((id) =>
    [
      'python', 'sql', 'golang', 'active_directory', 'm365', 'servicenow',
      'linux_admin', 'networking', 'javascript', 'typescript', 'react',
      'nodejs', 'java', 'csharp', 'cpp', 'rust', 'aws'
    ].includes(id)
  );
  if (langFilters.length > 0) {
    parts.push(FILTER_SEARCH_TERMS[langFilters[0]] || langFilters[0]);
  }

  // 3. Role keywords
  const roleFilters = activeFilterIds.filter((id) =>
    [
      'it_support', 'sysadmin', 'backend', 'data_ai', 'network', 'security',
      'fullstack', 'frontend', 'devops', 'mobile', 'qa'
    ].includes(id)
  );
  if (roleFilters.length > 0) {
    parts.push(FILTER_SEARCH_TERMS[roleFilters[0]] || roleFilters[0]);
  } else if (langFilters.length === 0) {
    if (track === 'it_admin') {
      parts.push('it support');
    } else {
      parts.push('developer');
    }
  }

  // 4. Workplace keywords (e.g. remote)
  const wpFilters = activeFilterIds.filter((id) =>
    ['remote', 'hybrid', 'contract', 'internship'].includes(id)
  );
  if (wpFilters.length > 0) {
    parts.push(FILTER_SEARCH_TERMS[wpFilters[0]] || wpFilters[0]);
  }

  const fallback = track === 'it_admin' ? 'it support' : 'developer';
  return parts.join(' ').trim() || fallback;
};

export const JobDiscovery: React.FC<JobDiscoveryProps> = ({ pipelineJobs, onJobAdded, onOpenSettings }) => {
  const [internalPipelineJobs, setInternalPipelineJobs] = useState<Job[]>([]);
  const [hidePipelineJobs, setHidePipelineJobs] = useState<boolean>(() => {
    try {
      const stored = localStorage.getItem('job_pulse_hide_pipeline_jobs');
      return stored !== null ? JSON.parse(stored) : true;
    } catch {
      return true;
    }
  });

  const toggleHidePipelineJobs = () => {
    const nextVal = !hidePipelineJobs;
    setHidePipelineJobs(nextVal);
    try {
      localStorage.setItem('job_pulse_hide_pipeline_jobs', JSON.stringify(nextVal));
    } catch (err) {
      console.error('Failed to save hidePipelineJobs preference:', err);
    }
  };

  // Fetch pipeline jobs on mount to guarantee fresh pipeline data
  useEffect(() => {
    const syncPipeline = async () => {
      try {
        const data = await api.getJobs();
        setInternalPipelineJobs(data);
      } catch (err) {
        console.error('Failed to fetch pipeline jobs in Discovery:', err);
      }
    };
    syncPipeline();
  }, []);

  const allPipelineJobs = useMemo(() => {
    const combined = [...(pipelineJobs || []), ...internalPipelineJobs];
    const seen = new Set<number>();
    return combined.filter((j) => {
      if (seen.has(j.id)) return false;
      seen.add(j.id);
      return true;
    });
  }, [pipelineJobs, internalPipelineJobs]);

  const [query, setQuery] = useState('');
  const [selectedFilters, setSelectedFilters] = useState<string[]>([]);
  const [selectedSource, setSelectedSource] = useState('all');
  const [activeTrack, setActiveTrack] = useState<'all' | 'software' | 'it_admin'>('all');
  const [usOnly, setUsOnly] = useState(true);
  const [isFiltersExpanded, setIsFiltersExpanded] = useState(true);
  const [loading, setLoading] = useState(false);
  const [jobs, setJobs] = useState<DiscoveredJob[]>([]);
  const [addedUrls, setAddedUrls] = useState<Set<string>>(new Set());
  const [addingUrl, setAddingUrl] = useState<string | null>(null);

  // Location & Radius Filtering State (persisted in localStorage)
  const [searchLocation, setSearchLocation] = useState<string>(() => {
    return localStorage.getItem('job_pulse_search_location') || '';
  });
  const [searchRadius, setSearchRadius] = useState<number>(() => {
    const saved = localStorage.getItem('job_pulse_search_radius');
    return saved !== null ? Number(saved) : 25; // default 25 miles
  });
  const [includeRemote, setIncludeRemote] = useState<boolean>(() => {
    const saved = localStorage.getItem('job_pulse_include_remote');
    return saved !== null ? saved === 'true' : true; // default true
  });
  const [profileLocation, setProfileLocation] = useState<string>('');
  const [detectingLocation, setDetectingLocation] = useState<boolean>(false);

  // Salary / Hourly Compensation Filter State (persisted in localStorage)
  const [salaryRateType, setSalaryRateType] = useState<'annual' | 'hourly'>(() => {
    return (localStorage.getItem('job_pulse_salary_rate_type') as 'annual' | 'hourly') || 'annual';
  });
  const [minSalary, setMinSalary] = useState<number>(() => {
    const saved = localStorage.getItem('job_pulse_min_salary');
    return saved !== null ? Number(saved) : 0; // 0 = no minimum
  });
  const [includeUnlistedSalary, setIncludeUnlistedSalary] = useState<boolean>(() => {
    const saved = localStorage.getItem('job_pulse_include_unlisted_salary');
    return saved !== null ? saved === 'true' : true; // default true
  });
  const [profileSalary, setProfileSalary] = useState<string>('');

  // Map of discovered job URL -> matching pipeline Job
  const pipelineMatchMap = useMemo(() => {
    const map = new Map<string, Job>();
    for (const job of jobs) {
      const match = findMatchingPipelineJob(job, allPipelineJobs);
      if (match) {
        map.set(job.url, match);
      }
    }
    return map;
  }, [jobs, allPipelineJobs]);

  // Count of discovered jobs that match pipeline
  const inPipelineCount = useMemo(() => {
    return pipelineMatchMap.size;
  }, [pipelineMatchMap]);

  // Hidden Jobs State (persisted in localStorage)
  const [hiddenJobsMap, setHiddenJobsMap] = useState<Record<string, DiscoveredJob & { hiddenAt: string }>>(() => {
    try {
      const raw = localStorage.getItem('job_pulse_hidden_jobs');
      return raw ? JSON.parse(raw) : {};
    } catch {
      return {};
    }
  });

  // Blocked Companies & Recruiters (persisted in localStorage)
  const [blockedCompanies, setBlockedCompanies] = useState<string[]>(() => {
    try {
      const raw = localStorage.getItem('job_pulse_blocked_companies');
      return raw ? JSON.parse(raw) : [];
    } catch {
      return [];
    }
  });

  const [showHiddenOnly, setShowHiddenOnly] = useState(false);
  const [isManageHiddenOpen, setIsManageHiddenOpen] = useState(false);
  const [toastJob, setToastJob] = useState<DiscoveredJob | null>(null);

  // Pagination State (Limit 30 listings per page)
  const ITEMS_PER_PAGE = 30;
  const [currentPage, setCurrentPage] = useState(1);
  const mainScrollRef = useRef<HTMLElement | null>(null);

  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const queryDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const toastTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const fetchSequenceRef = useRef<number>(0);
  const lastFetchedQueryRef = useRef<string>('');

  const hiddenUrls = useMemo(() => new Set(Object.keys(hiddenJobsMap)), [hiddenJobsMap]);
  const hiddenCount = hiddenUrls.size;

  const saveHiddenMap = (newMap: Record<string, DiscoveredJob & { hiddenAt: string }>) => {
    setHiddenJobsMap(newMap);
    try {
      localStorage.setItem('job_pulse_hidden_jobs', JSON.stringify(newMap));
      window.dispatchEvent(new Event('job_pulse_storage_updated'));
    } catch (err) {
      console.error('Failed to save hidden jobs to localStorage:', err);
    }
  };

  // Sync hidden jobs and company blacklist whenever modified from Settings modal or other components
  useEffect(() => {
    const handleStorageUpdate = () => {
      try {
        const rawHidden = localStorage.getItem('job_pulse_hidden_jobs');
        setHiddenJobsMap(rawHidden ? JSON.parse(rawHidden) : {});
        const rawBlocked = localStorage.getItem('job_pulse_blocked_companies');
        setBlockedCompanies(rawBlocked ? JSON.parse(rawBlocked) : []);
      } catch (err) {
        console.error('Failed to sync storage:', err);
      }
    };

    window.addEventListener('storage', handleStorageUpdate);
    window.addEventListener('job_pulse_storage_updated', handleStorageUpdate);
    return () => {
      window.removeEventListener('storage', handleStorageUpdate);
      window.removeEventListener('job_pulse_storage_updated', handleStorageUpdate);
    };
  }, []);

  const handleHideJob = (job: DiscoveredJob) => {
    const updated = {
      ...hiddenJobsMap,
      [job.url]: {
        ...job,
        hiddenAt: new Date().toISOString(),
      },
    };
    saveHiddenMap(updated);

    if (toastTimeoutRef.current) clearTimeout(toastTimeoutRef.current);
    setToastJob(job);
    toastTimeoutRef.current = setTimeout(() => {
      setToastJob(null);
    }, 6000);
  };

  const handleUnhideJob = (jobUrl: string) => {
    const updated = { ...hiddenJobsMap };
    delete updated[jobUrl];
    saveHiddenMap(updated);
  };

  const handleUnhideAll = () => {
    saveHiddenMap({});
    setShowHiddenOnly(false);
    setIsManageHiddenOpen(false);
  };

  const handleUndoHide = () => {
    if (toastJob) {
      handleUnhideJob(toastJob.url);
      setToastJob(null);
    }
  };

  const fetchJobs = async (
    searchQuery: string = query,
    source: string = selectedSource,
    isUsOnly: boolean = usOnly,
    loc: string = searchLocation,
    rad: number = searchRadius,
    incRemote: boolean = includeRemote,
    minSal: number = minSalary,
    incUnlisted: boolean = includeUnlistedSalary,
    forceRefresh: boolean = false
  ) => {
    const currentFetchId = ++fetchSequenceRef.current;
    lastFetchedQueryRef.current = searchQuery.trim();
    setLoading(true);
    try {
      const adzunaId = localStorage.getItem('job_pulse_adzuna_app_id') || undefined;
      const adzunaKey = localStorage.getItem('job_pulse_adzuna_app_key') || undefined;
      const effectiveQuery = searchQuery.trim() || 'developer';
      const effectiveRad = rad > 0 ? rad : undefined;
      const effectiveLoc = loc.trim() ? loc.trim() : undefined;
      const results = await api.searchDiscoveredJobs(
        effectiveQuery,
        source,
        adzunaId,
        adzunaKey,
        isUsOnly,
        effectiveLoc,
        effectiveRad,
        incRemote,
        minSal > 0 ? minSal : undefined,
        incUnlisted,
        forceRefresh
      );
      if (currentFetchId === fetchSequenceRef.current) {
        setJobs(results);
      }
    } catch (err) {
      if (currentFetchId === fetchSequenceRef.current) {
        console.error('Failed to search jobs:', err);
      }
    } finally {
      if (currentFetchId === fetchSequenceRef.current) {
        setLoading(false);
      }
    }
  };

  useEffect(() => {
    const savedLoc = localStorage.getItem('job_pulse_search_location') || '';
    const savedRad = localStorage.getItem('job_pulse_search_radius');
    const radNum = savedRad !== null ? Number(savedRad) : 25;
    const savedIncRemote = localStorage.getItem('job_pulse_include_remote');
    const incRemoteBool = savedIncRemote !== null ? savedIncRemote === 'true' : true;

    fetchJobs('developer', 'all', true, savedLoc, radNum, incRemoteBool, minSalary, includeUnlistedSalary);

    // Load profile location & compensation for quick suggestions
    api.getProfile().then((prof) => {
      if (prof && prof.location) {
        setProfileLocation(prof.location);
      }
      if (prof && prof.desired_salary) {
        setProfileSalary(prof.desired_salary);
      }
    }).catch(() => {});

    return () => {
      if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
      if (queryDebounceRef.current) clearTimeout(queryDebounceRef.current);
      if (toastTimeoutRef.current) clearTimeout(toastTimeoutRef.current);
    };
  }, []);

  const handleLocationChange = (newLoc: string) => {
    setSearchLocation(newLoc);
    localStorage.setItem('job_pulse_search_location', newLoc);
  };

  const handleRadiusChange = (newRad: number) => {
    setSearchRadius(newRad);
    localStorage.setItem('job_pulse_search_radius', String(newRad));
    if (searchLocation.trim()) {
      const effectiveQuery = getEffectiveSearchQuery(query, selectedFilters);
      fetchJobs(effectiveQuery, selectedSource, usOnly, searchLocation, newRad, includeRemote);
    }
  };

  const handleIncludeRemoteToggle = () => {
    const nextVal = !includeRemote;
    setIncludeRemote(nextVal);
    localStorage.setItem('job_pulse_include_remote', String(nextVal));
    const effectiveQuery = getEffectiveSearchQuery(query, selectedFilters);
    fetchJobs(effectiveQuery, selectedSource, usOnly, searchLocation, searchRadius, nextVal);
  };

  const handleClearLocation = () => {
    setSearchLocation('');
    localStorage.removeItem('job_pulse_search_location');
    const effectiveQuery = getEffectiveSearchQuery(query, selectedFilters);
    fetchJobs(effectiveQuery, selectedSource, usOnly, '', searchRadius, includeRemote);
  };

  const handleDetectLocation = () => {
    if (!navigator.geolocation) {
      alert('Geolocation is not supported by your browser.');
      return;
    }
    setDetectingLocation(true);
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        try {
          const { latitude, longitude } = pos.coords;
          const res = await fetch(
            `https://nominatim.openstreetmap.org/reverse?format=json&lat=${latitude}&lon=${longitude}&zoom=10`
          );
          let locStr = '';
          if (res.ok) {
            const data = await res.json();
            const addr = data.address || {};
            const city = addr.city || addr.town || addr.village || addr.county || '';
            const state = addr.state || '';
            locStr = city && state ? `${city}, ${state}` : (city || state || `${latitude.toFixed(2)}, ${longitude.toFixed(2)}`);
          } else {
            locStr = `${latitude.toFixed(2)}, ${longitude.toFixed(2)}`;
          }
          if (locStr) {
            setSearchLocation(locStr);
            localStorage.setItem('job_pulse_search_location', locStr);
            const effectiveQuery = getEffectiveSearchQuery(query, selectedFilters);
            fetchJobs(effectiveQuery, selectedSource, usOnly, locStr, searchRadius, includeRemote);
          }
        } catch (err) {
          console.error('Failed to reverse geocode:', err);
        } finally {
          setDetectingLocation(false);
        }
      },
      (err) => {
        console.warn('Geolocation error:', err);
        setDetectingLocation(false);
        alert('Could not determine your location automatically. Please type your city or ZIP code.');
      },
      { timeout: 8000 }
    );
  };

  const handleQueryChange = (val: string) => {
    setQuery(val);
    if (queryDebounceRef.current) {
      clearTimeout(queryDebounceRef.current);
    }
    const trimmed = val.trim();
    // Debounce live fetch when user pauses typing
    queryDebounceRef.current = setTimeout(() => {
      const effective = getEffectiveSearchQuery(trimmed, selectedFilters);
      fetchJobs(effective, selectedSource, usOnly, searchLocation, searchRadius, includeRemote, minSalary, includeUnlistedSalary);
    }, 550);
  };

  const handleFilterToggle = (filterId: string) => {
    const nextFilters = selectedFilters.includes(filterId)
      ? selectedFilters.filter((id) => id !== filterId)
      : [...selectedFilters, filterId];
    setSelectedFilters(nextFilters);

    const trimmedQuery = query.trim();
    // If user typed a query that hasn't been fetched from backend yet, fetch it immediately!
    if (trimmedQuery && trimmedQuery.toLowerCase() !== lastFetchedQueryRef.current.toLowerCase()) {
      if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
      if (queryDebounceRef.current) clearTimeout(queryDebounceRef.current);
      const effectiveQuery = getEffectiveSearchQuery(trimmedQuery, nextFilters);
      fetchJobs(effectiveQuery, selectedSource, usOnly, searchLocation, searchRadius, includeRemote, minSalary, includeUnlistedSalary);
      return;
    }

    // If no query is typed, debounce fetch with the new filter keyword
    if (!trimmedQuery) {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
      debounceTimerRef.current = setTimeout(() => {
        const effectiveQuery = getEffectiveSearchQuery('', nextFilters);
        fetchJobs(effectiveQuery, selectedSource, usOnly, searchLocation, searchRadius, includeRemote, minSalary, includeUnlistedSalary);
      }, 450);
    }
  };

  const handleClearGroup = (groupId: string) => {
    const group = FILTER_GROUPS.find((g) => g.id === groupId);
    if (!group) return;
    const groupOptionIds = new Set(group.options.map((o) => o.id));
    const nextFilters = selectedFilters.filter((id) => !groupOptionIds.has(id));
    setSelectedFilters(nextFilters);

    const trimmedQuery = query.trim();
    if (trimmedQuery && trimmedQuery.toLowerCase() !== lastFetchedQueryRef.current.toLowerCase()) {
      if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
      if (queryDebounceRef.current) clearTimeout(queryDebounceRef.current);
      const effectiveQuery = getEffectiveSearchQuery(trimmedQuery, nextFilters);
      fetchJobs(effectiveQuery, selectedSource, usOnly, searchLocation, searchRadius, includeRemote, minSalary, includeUnlistedSalary);
      return;
    }

    if (!trimmedQuery) {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
      debounceTimerRef.current = setTimeout(() => {
        const effectiveQuery = getEffectiveSearchQuery('', nextFilters);
        fetchJobs(effectiveQuery, selectedSource, usOnly, searchLocation, searchRadius, includeRemote, minSalary, includeUnlistedSalary);
      }, 450);
    }
  };

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }
    if (queryDebounceRef.current) {
      clearTimeout(queryDebounceRef.current);
    }
    const effectiveQuery = getEffectiveSearchQuery(query, selectedFilters);
    fetchJobs(effectiveQuery, selectedSource, usOnly, searchLocation, searchRadius, includeRemote, minSalary, includeUnlistedSalary, true);
  };

  const handleSourceSelect = (sourceId: string) => {
    const nextSource = selectedSource === sourceId && sourceId !== 'all' ? 'all' : sourceId;
    setSelectedSource(nextSource);
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }
    const effectiveQuery = getEffectiveSearchQuery(query, selectedFilters);
    fetchJobs(effectiveQuery, nextSource, usOnly, searchLocation, searchRadius, includeRemote);
  };

  const handleSelectTrack = (track: 'all' | 'software' | 'it_admin') => {
    setActiveTrack(track);
    let newFilters: string[] = [];
    let newQuery = '';

    if (track === 'software') {
      newFilters = ['backend'];
    } else if (track === 'it_admin') {
      newFilters = ['it_support'];
    } else {
      newFilters = [];
    }

    setSelectedFilters(newFilters);
    setQuery(newQuery);

    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }
    const effectiveQuery = getEffectiveSearchQuery(newQuery, newFilters, track);
    fetchJobs(effectiveQuery, selectedSource, usOnly, searchLocation, searchRadius, includeRemote);
  };

  const handleSalaryRateTypeChange = (type: 'annual' | 'hourly') => {
    setSalaryRateType(type);
    localStorage.setItem('job_pulse_salary_rate_type', type);
  };

  const handleMinSalaryChange = (val: number) => {
    const cleaned = Math.max(0, val);
    setMinSalary(cleaned);
    localStorage.setItem('job_pulse_min_salary', String(cleaned));
  };

  const handleIncludeUnlistedSalaryToggle = () => {
    const nextVal = !includeUnlistedSalary;
    setIncludeUnlistedSalary(nextVal);
    localStorage.setItem('job_pulse_include_unlisted_salary', String(nextVal));
  };

  const handleApplyProfileSalary = () => {
    if (!profileSalary) return;
    const parsed = parseSalaryStringToAnnual(profileSalary);
    if (parsed && parsed > 0) {
      handleMinSalaryChange(parsed);
    }
  };

  const handleResetFilters = () => {
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }
    setQuery('');
    setSelectedFilters([]);
    setSelectedSource('all');
    setActiveTrack('all');
    setMinSalary(0);
    localStorage.removeItem('job_pulse_min_salary');
    fetchJobs('developer', 'all', usOnly, searchLocation, searchRadius, includeRemote, 0, includeUnlistedSalary);
  };

  // Compound client-side filtering:
  // - Handles hidden listings pool (either active or hidden only)
  // - Matches source platform
  // - Matches every custom search query word
  // - Category logic: AND across categories, OR within same category
  const filteredJobs = useMemo(() => {
    const pool = showHiddenOnly
      ? Object.values(hiddenJobsMap)
      : jobs.filter((job) => !hiddenUrls.has(job.url));

    return pool.filter((job) => {
      // 0. Hide in-pipeline jobs when active
      if (!showHiddenOnly && hidePipelineJobs && pipelineMatchMap.has(job.url)) {
        return false;
      }

      // 0b. Company blacklist filter (excludes recruiter/company postings permanently when active)
      if (!showHiddenOnly && blockedCompanies.length > 0) {
        const comp = (job.company || '').toLowerCase();
        if (blockedCompanies.some((b) => b && comp.includes(b.toLowerCase()))) {
          return false;
        }
      }

      // 0c. Target Location & Range enforcement:
      // - Pure remote jobs are allowed if includeRemote is true, hidden if false.
      // - Hybrid & Onsite jobs MUST be physically located within searchRadius of searchLocation.
      //   Any hybrid job outside this range (e.g. Seattle when searching Austin) is strictly filtered out.
      if (!showHiddenOnly && searchLocation.trim()) {
        if (!checkJobLocationMatchesRange(job, searchLocation, searchRadius, includeRemote)) {
          return false;
        }
      }

      // 0d. Minimum Compensation (Salary / Hourly) filter
      if (!showHiddenOnly && minSalary > 0) {
        const salMin = job.salary_min;
        const salMax = job.salary_max;
        const hasSalary = (salMin !== undefined && salMin !== null && salMin > 0) || (salMax !== undefined && salMax !== null && salMax > 0);

        if (hasSalary) {
          const effectiveMax = (salMax && salMax > 0) ? salMax : (salMin ?? 0);
          if (effectiveMax < minSalary) {
            return false;
          }
        } else if (!includeUnlistedSalary) {
          return false;
        }
      }

      // 1. Source board filter
      if (selectedSource !== 'all' && job.source.toLowerCase() !== selectedSource.toLowerCase()) {
        return false;
      }

      const titleLower = (job.title || '').toLowerCase();
      const compLower = (job.company || '').toLowerCase();
      const locLower = (job.location || '').toLowerCase();
      const descLower = (job.description || '').toLowerCase();
      const tagsStr = (job.tags || []).join(' ').toLowerCase();
      const fullText = `${titleLower} ${compLower} ${locLower} ${tagsStr} ${descLower}`;

      // 2. Custom typed keyword filter (supports composite phrases and synonyms)
      if (query.trim()) {
        const normalizedQ = query
          .toLowerCase()
          .trim()
          .replace(/\bentry[\s-]+level\b/g, 'junior')
          .replace(/\bnew\s+grad(?:uate)?\b/g, 'junior')
          .replace(/\brecent\s+grad(?:uate)?\b/g, 'junior')
          .replace(/\bearly[\s-]+career\b/g, 'junior')
          .replace(/\bfull[\s-]+stack\b/g, 'fullstack')
          .replace(/\bfront[\s-]+end\b/g, 'frontend')
          .replace(/\bback[\s-]+end\b/g, 'backend')
          .replace(/\bwork\s+from\s+home\b/g, 'remote')
          .replace(/[/,()"+-]/g, ' ');

        const stopWords = new Set(['and', 'or', 'the', 'for', 'with', 'in', 'level', 'role', 'position', 'job', 'jobs']);
        const words = normalizedQ
          .split(/\s+/)
          .filter((w) => w.length > 1 && !stopWords.has(w));

        const matchesAll = words.every((w) => {
          if (['junior', 'jr', 'entry', 'associate', 'intern', 'internship', 'apprentice'].includes(w)) {
            return matchesOption('junior', fullText, job);
          }
          if (['developer', 'engineer', 'dev', 'programmer', 'software', 'coder', 'engineering', 'development'].includes(w)) {
            return /\b(developer|engineer|dev|programmer|software|coder|engineering|development|swe|sde|consultant|specialist|architect)\b/i.test(fullText);
          }
          if (['solutions', 'solution'].includes(w)) {
            return /\b(solution|solutions)\b/i.test(fullText);
          }
          if (['remote', 'wfh', 'telecommute'].includes(w)) {
            return matchesOption('remote', fullText, job);
          }
          if (['fullstack', 'frontend', 'backend', 'devops', 'python', 'javascript', 'typescript', 'react', 'nodejs', 'golang', 'java', 'csharp', 'cpp', 'rust', 'sql', 'aws'].includes(w)) {
            return matchesOption(w, fullText, job);
          }
          // Support plural/singular stem matching
          if (fullText.includes(w)) return true;
          if (w.endsWith('s') && fullText.includes(w.slice(0, -1))) return true;
          if (!w.endsWith('s') && fullText.includes(w + 's')) return true;
          return false;
        });
        if (!matchesAll) return false;
      }

      // 3. Category Group filtering:
      for (const group of FILTER_GROUPS) {
        const selectedInGroup = group.options.filter((opt) => selectedFilters.includes(opt.id));
        if (selectedInGroup.length > 0) {
          const matchesAnyInGroup = selectedInGroup.some((opt) => matchesOption(opt.id, fullText, job));
          if (!matchesAnyInGroup) {
            return false;
          }
        }
      }

      return true;
    });
  }, [jobs, hiddenJobsMap, hiddenUrls, showHiddenOnly, selectedSource, selectedFilters, query, blockedCompanies, hidePipelineJobs, pipelineMatchMap, searchLocation, searchRadius, includeRemote, minSalary, includeUnlistedSalary]);

  // Reset pagination to page 1 whenever search, filters, source, location, compensation, or view mode changes
  useEffect(() => {
    setCurrentPage(1);
  }, [query, selectedFilters, selectedSource, usOnly, showHiddenOnly, hidePipelineJobs, searchLocation, searchRadius, includeRemote, minSalary, includeUnlistedSalary]);

  const totalPages = Math.max(1, Math.ceil(filteredJobs.length / ITEMS_PER_PAGE));
  const safePage = Math.min(currentPage, totalPages);
  const startIndex = (safePage - 1) * ITEMS_PER_PAGE;
  const endIndex = Math.min(startIndex + ITEMS_PER_PAGE, filteredJobs.length);

  const paginatedJobs = useMemo(() => {
    return filteredJobs.slice(startIndex, endIndex);
  }, [filteredJobs, startIndex, endIndex]);

  const handlePageChange = (newPage: number) => {
    if (newPage < 1 || newPage > totalPages || newPage === safePage) return;
    setCurrentPage(newPage);
    mainScrollRef.current?.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const getPageNumbers = () => {
    const pages: (number | string)[] = [];
    if (totalPages <= 7) {
      for (let i = 1; i <= totalPages; i++) pages.push(i);
    } else {
      if (safePage <= 4) {
        pages.push(1, 2, 3, 4, 5, '...', totalPages);
      } else if (safePage >= totalPages - 3) {
        pages.push(1, '...', totalPages - 4, totalPages - 3, totalPages - 2, totalPages - 1, totalPages);
      } else {
        pages.push(1, '...', safePage - 1, safePage, safePage + 1, '...', totalPages);
      }
    }
    return pages;
  };

  const handleAddJob = async (job: DiscoveredJob) => {
    setAddingUrl(job.url);
    try {
      const created = await api.createJob({
        title: job.title,
        company: job.company,
        location: job.location || 'Remote',
        workplace_type: job.workplace_type || 'remote',
        url: job.url,
        salary_min: job.salary_min,
        salary_max: job.salary_max,
        salary_currency: job.salary_currency || 'USD',
        description: job.description,
        source: job.source,
        status: 'TO_APPLY',
      });
      setAddedUrls((prev) => new Set(prev).add(job.url));
      setInternalPipelineJobs((prev) => [created, ...prev]);
      onJobAdded(created);
    } catch (err) {
      console.error('Failed to add job:', err);
    } finally {
      setAddingUrl(null);
    }
  };

  const getSourceBadge = (source: string) => {
    switch (source.toLowerCase()) {
      case 'bigtech':
        return 'bg-amber-950/70 text-amber-300 border-amber-700/60';
      case 'company_boards':
        return 'bg-fuchsia-950/70 text-fuchsia-300 border-fuchsia-700/60';
      case 'simplify':
        return 'bg-cyan-950/70 text-cyan-300 border-cyan-700/60';
      case 'linkedin':
        return 'bg-sky-950/70 text-sky-300 border-sky-700/60';
      case 'glassdoor':
        return 'bg-lime-950/70 text-lime-300 border-lime-700/60';
      case 'themuse':
        return 'bg-violet-950/70 text-violet-300 border-violet-700/60';
      case 'indeed':
        return 'bg-blue-950/60 text-blue-300 border-blue-800/50';
      case 'ziprecruiter':
        return 'bg-green-950/60 text-green-300 border-green-800/50';
      case 'weworkremotely':
        return 'bg-red-950/60 text-red-300 border-red-800/50';
      case 'himalayas':
        return 'bg-indigo-950/60 text-indigo-300 border-indigo-800/50';
      case 'hackernews':
        return 'bg-orange-950/60 text-orange-300 border-orange-800/50';
      case 'adzuna':
        return 'bg-emerald-950/60 text-emerald-300 border-emerald-800/50';
      case 'remoteok':
        return 'bg-purple-950/60 text-purple-300 border-purple-800/50';
      case 'arbeitnow':
        return 'bg-sky-950/60 text-sky-300 border-sky-800/50';
      case 'jobicy':
        return 'bg-teal-950/60 text-teal-300 border-teal-800/50';
      default:
        return 'bg-slate-900/80 text-slate-400 border-slate-700/50';
    }
  };

  return (
    <div className="flex-1 min-h-0 flex flex-col lg:flex-row h-full max-h-full overflow-hidden w-full bg-slate-900">
      {/* Mobile Filter Toggle Bar (Small screens only) */}
      <div className="w-full lg:hidden p-3 bg-slate-950 border-b border-slate-800 shrink-0">
        <button
          type="button"
          onClick={() => setIsFiltersExpanded(!isFiltersExpanded)}
          className="w-full flex items-center justify-between p-3 rounded-xl bg-slate-900 border border-slate-800 text-slate-200 font-bold text-xs shadow-md"
        >
          <div className="flex items-center space-x-2">
            <SlidersHorizontal className="w-4 h-4 text-emerald-400" />
            <span>Filter Options & Sources</span>
            {(selectedFilters.length > 0 || selectedSource !== 'all') && (
              <span className="px-2 py-0.5 rounded-full text-[10px] bg-emerald-500/20 text-emerald-300 font-bold border border-emerald-500/40">
                {[...selectedFilters, selectedSource !== 'all' ? selectedSource : ''].filter(Boolean).length} active
              </span>
            )}
          </div>
          <div className="flex items-center space-x-1 text-slate-400 text-xs">
            <span>{isFiltersExpanded ? 'Hide Filters' : 'Show Filters'}</span>
            {isFiltersExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </div>
        </button>
      </div>

      {/* Left Sidebar: Vertically Oriented Filters (True Independent Scroll Container) */}
      <aside
        className={`${
          isFiltersExpanded ? 'flex' : 'hidden'
        } lg:flex w-full lg:w-80 xl:w-88 shrink-0 border-b lg:border-b-0 lg:border-r border-slate-800 bg-slate-950/60 backdrop-blur-md flex-col h-auto lg:h-full lg:max-h-full min-h-0 overflow-y-auto overscroll-contain p-4 sm:p-5 space-y-4 shadow-xl z-10`}
      >
        {/* Sidebar Title & Reset All */}
        <div className="flex items-center justify-between pb-3 border-b border-slate-800">
          <div className="flex items-center space-x-2 text-white font-bold text-sm">
            <SlidersHorizontal className="w-4 h-4 text-emerald-400" />
            <span>Filters</span>
            {(selectedFilters.length > 0 || selectedSource !== 'all' || query.trim()) && (
              <span className="px-2 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 animate-pulse">
                {[...selectedFilters, selectedSource !== 'all' ? selectedSource : '', query.trim()].filter(Boolean).length}
              </span>
            )}
          </div>
          {(selectedFilters.length > 0 || selectedSource !== 'all' || query.trim()) && (
            <button
              type="button"
              onClick={handleResetFilters}
              className="text-xs text-slate-400 hover:text-emerald-400 transition underline font-medium"
            >
              Reset all
            </button>
          )}
        </div>

        {/* US Jobs Only Toggle */}
        <button
          type="button"
          onClick={() => {
            const newVal = !usOnly;
            setUsOnly(newVal);
            fetchJobs(query.trim(), selectedSource, newVal);
          }}
          className={`w-full flex items-center justify-between px-3.5 py-2.5 rounded-xl text-xs font-semibold border transition ${
            usOnly
              ? 'bg-emerald-950/70 border-emerald-500/60 text-emerald-300 shadow-xs'
              : 'bg-slate-800/80 border-slate-700/80 text-slate-400 hover:text-white hover:bg-slate-800'
          }`}
          title="Toggle US-Only jobs filter"
        >
          <div className="flex items-center space-x-2">
            <span className="text-sm">🇺🇸</span>
            <span>US Jobs Only</span>
          </div>
          <span className={`w-2.5 h-2.5 rounded-full ${usOnly ? 'bg-emerald-400 animate-pulse' : 'bg-slate-500'}`} />
        </button>

        {/* Hidden Listings Toggle */}
        <div className="flex items-center space-x-2">
          <button
            type="button"
            onClick={() => setShowHiddenOnly(!showHiddenOnly)}
            className={`flex-1 flex items-center justify-between px-3.5 py-2.5 rounded-xl text-xs font-semibold border transition ${
              showHiddenOnly
                ? 'bg-amber-950/70 border-amber-500/60 text-amber-300 shadow-xs ring-1 ring-amber-500/30'
                : 'bg-slate-800/80 border-slate-700/80 text-slate-400 hover:text-white hover:bg-slate-800'
            }`}
            title="Toggle between active and hidden listings"
          >
            <div className="flex items-center space-x-2">
              {showHiddenOnly ? <Eye className="w-4 h-4 text-amber-400" /> : <EyeOff className="w-4 h-4 text-slate-400" />}
              <span>{showHiddenOnly ? 'Viewing Hidden' : 'Hidden Listings'}</span>
            </div>
            <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
              showHiddenOnly
                ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                : 'bg-slate-900 text-slate-400 border border-slate-700'
            }`}>
              {hiddenCount}
            </span>
          </button>
          <button
            type="button"
            onClick={() => onOpenSettings ? onOpenSettings('hidden') : setIsManageHiddenOpen(true)}
            className="px-2.5 py-2.5 rounded-xl text-xs font-semibold border border-slate-700/80 bg-slate-800/80 hover:bg-slate-700 text-slate-300 hover:text-white transition"
            title="Manage hidden listings and company blacklist in Settings"
          >
            Manage
          </button>
        </div>

        {/* Hide In-Pipeline Toggle */}
        <button
          type="button"
          onClick={toggleHidePipelineJobs}
          className={`w-full flex items-center justify-between px-3.5 py-2.5 rounded-xl text-xs font-semibold border transition ${
            hidePipelineJobs
              ? 'bg-purple-950/70 border-purple-500/60 text-purple-300 shadow-xs'
              : 'bg-slate-800/80 border-slate-700/80 text-slate-400 hover:text-white hover:bg-slate-800'
          }`}
          title="Toggle hiding jobs that are already tracked in your Pipeline Kanban"
        >
          <div className="flex items-center space-x-2">
            <Briefcase className="w-4 h-4 text-purple-400" />
            <span>Hide In Pipeline</span>
          </div>
          <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
            hidePipelineJobs
              ? 'bg-purple-500/20 text-purple-300 border border-purple-500/40'
              : 'bg-slate-900 text-slate-400 border border-slate-700'
          }`}>
            {inPipelineCount}
          </span>
        </button>

        {/* Location & Radius Section */}
        <div className="space-y-3 pt-3 border-t border-slate-800/80">
          <div className="flex items-center justify-between text-xs">
            <div className="flex items-center space-x-2 text-slate-200 font-semibold">
              <MapPin className="w-3.5 h-3.5 text-emerald-400" />
              <span>Location & Radius</span>
            </div>
            {searchLocation && (
              <button
                type="button"
                onClick={handleClearLocation}
                className="text-[11px] text-slate-400 hover:text-emerald-400 transition underline font-normal"
              >
                Clear
              </button>
            )}
          </div>

          {/* Quick Location Input */}
          <div className="relative">
            <MapPin className="w-3.5 h-3.5 absolute left-3 top-2.5 text-slate-400" />
            <input
              type="text"
              placeholder="City, State or ZIP..."
              value={searchLocation}
              onChange={(e) => handleLocationChange(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  const effectiveQuery = getEffectiveSearchQuery(query, selectedFilters);
                  fetchJobs(effectiveQuery, selectedSource, usOnly, searchLocation, searchRadius, includeRemote);
                }
              }}
              className="w-full pl-8 pr-10 py-1.5 bg-slate-800/80 border border-slate-700 rounded-lg text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
            />
            <div className="absolute right-1.5 top-1.5 flex items-center space-x-1">
              <button
                type="button"
                onClick={handleDetectLocation}
                disabled={detectingLocation}
                className="text-slate-400 hover:text-emerald-400 p-1 rounded hover:bg-slate-700/50 transition"
                title="Detect current location"
              >
                <Navigation className={`w-3 h-3 ${detectingLocation ? 'animate-spin text-emerald-400' : ''}`} />
              </button>
            </div>
          </div>

          {/* Use Profile Location Shortcut */}
          {profileLocation && profileLocation !== searchLocation && (
            <button
              type="button"
              onClick={() => {
                handleLocationChange(profileLocation);
                const effectiveQuery = getEffectiveSearchQuery(query, selectedFilters);
                fetchJobs(effectiveQuery, selectedSource, usOnly, profileLocation, searchRadius, includeRemote);
              }}
              className="text-[11px] text-emerald-400 hover:text-emerald-300 transition flex items-center space-x-1"
            >
              <span className="text-slate-400">Profile:</span>
              <span className="font-semibold underline truncate max-w-[180px]">{profileLocation}</span>
            </button>
          )}

          {/* Radius Selector Chips */}
          <div className="space-y-1">
            <div className="flex items-center justify-between text-[11px] text-slate-400">
              <span>Radius (miles):</span>
              <span className="text-emerald-400 font-semibold">{searchRadius > 0 ? `${searchRadius} mi` : 'Anywhere'}</span>
            </div>
            <div className="grid grid-cols-4 gap-1">
              {[10, 25, 50, 100].map((r) => (
                <button
                  key={r}
                  type="button"
                  onClick={() => handleRadiusChange(r)}
                  className={`py-1 text-center rounded-lg text-xs font-medium border transition ${
                    searchRadius === r
                      ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/60 font-semibold ring-1 ring-emerald-500/30'
                      : 'bg-slate-800/70 text-slate-400 border-slate-700/60 hover:text-slate-200 hover:bg-slate-800'
                  }`}
                >
                  {r}m
                </button>
              ))}
            </div>
          </div>

          {/* Include Remote Toggle Checkbox */}
          <label className="flex items-center space-x-2 text-xs text-slate-300 cursor-pointer pt-0.5">
            <input
              type="checkbox"
              checked={includeRemote}
              onChange={handleIncludeRemoteToggle}
              className="rounded bg-slate-800 border-slate-700 text-emerald-500 focus:ring-emerald-500/40"
            />
            <span>Include Remote Jobs</span>
          </label>
        </div>

        {/* Compensation / Desired Salary Section */}
        <div className="space-y-3 pt-3 border-t border-slate-800/80">
          <div className="flex items-center justify-between text-xs">
            <div className="flex items-center space-x-2 text-slate-200 font-semibold">
              <DollarSign className="w-3.5 h-3.5 text-emerald-400" />
              <span>Compensation</span>
              {minSalary > 0 && (
                <span className="px-1.5 py-0.2 rounded-full text-[10px] font-bold bg-emerald-950 text-emerald-300 border border-emerald-500/40">
                  {salaryRateType === 'hourly' ? `$${Math.round(minSalary / 2080)}/hr+` : `$${Math.round(minSalary / 1000)}k+`}
                </span>
              )}
            </div>
            {minSalary > 0 && (
              <button
                type="button"
                onClick={() => handleMinSalaryChange(0)}
                className="text-[11px] text-slate-400 hover:text-emerald-400 transition underline font-normal"
              >
                Reset
              </button>
            )}
          </div>

          {/* Rate Switcher: Annual vs Hourly */}
          <div className="grid grid-cols-2 gap-1 p-0.5 bg-slate-900 border border-slate-800 rounded-xl">
            <button
              type="button"
              onClick={() => handleSalaryRateTypeChange('annual')}
              className={`py-1 text-center rounded-lg text-xs font-semibold transition ${
                salaryRateType === 'annual'
                  ? 'bg-slate-800 text-emerald-300 shadow-xs'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Annual ($/yr)
            </button>
            <button
              type="button"
              onClick={() => handleSalaryRateTypeChange('hourly')}
              className={`py-1 text-center rounded-lg text-xs font-semibold transition ${
                salaryRateType === 'hourly'
                  ? 'bg-slate-800 text-emerald-300 shadow-xs'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Hourly ($/hr)
            </button>
          </div>

          {/* Quick Preset Chips */}
          <div className="space-y-1">
            <div className="flex items-center justify-between text-[11px] text-slate-400">
              <span>Minimum Pay:</span>
              <span className="text-emerald-400 font-semibold">
                {minSalary > 0
                  ? salaryRateType === 'hourly'
                    ? `$${Math.round(minSalary / 2080)}/hr (~$${Math.round(minSalary / 1000)}k/yr)`
                    : `$${Math.round(minSalary / 1000)}k/yr (~$${Math.round(minSalary / 2080)}/hr)`
                  : 'Any pay'}
              </span>
            </div>
            <div className="grid grid-cols-3 gap-1">
              {(salaryRateType === 'hourly'
                ? [
                    { label: 'Any', value: 0 },
                    { label: '$25/hr', value: 25 * 2080 },
                    { label: '$35/hr', value: 35 * 2080 },
                    { label: '$45/hr', value: 45 * 2080 },
                    { label: '$55/hr', value: 55 * 2080 },
                    { label: '$70/hr', value: 70 * 2080 },
                  ]
                : [
                    { label: 'Any', value: 0 },
                    { label: '$50k', value: 50000 },
                    { label: '$70k', value: 70000 },
                    { label: '$90k', value: 90000 },
                    { label: '$110k', value: 110000 },
                    { label: '$130k', value: 130000 },
                  ]
              ).map((preset) => (
                <button
                  key={preset.label}
                  type="button"
                  onClick={() => handleMinSalaryChange(preset.value)}
                  className={`py-1 text-center rounded-lg text-xs font-medium border transition ${
                    minSalary === preset.value
                      ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/60 font-semibold ring-1 ring-emerald-500/30'
                      : 'bg-slate-800/70 text-slate-400 border-slate-700/60 hover:text-slate-200 hover:bg-slate-800'
                  }`}
                >
                  {preset.label}
                </button>
              ))}
            </div>
          </div>

          {/* Custom Min Input */}
          <div className="relative">
            <span className="absolute left-3 top-2 text-xs text-slate-500 font-semibold">$</span>
            <input
              type="number"
              placeholder={salaryRateType === 'hourly' ? "Custom /hr (e.g. 40)" : "Custom /yr (e.g. 85000)"}
              value={
                minSalary > 0
                  ? salaryRateType === 'hourly'
                    ? Math.round(minSalary / 2080)
                    : minSalary
                  : ''
              }
              onChange={(e) => {
                const val = Number(e.target.value);
                if (salaryRateType === 'hourly') {
                  handleMinSalaryChange(val > 0 ? val * 2080 : 0);
                } else {
                  handleMinSalaryChange(val > 0 ? val : 0);
                }
              }}
              className="w-full pl-7 pr-12 py-1.5 bg-slate-800/80 border border-slate-700 rounded-lg text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
            />
            <span className="absolute right-3 top-2 text-[10px] text-slate-500 font-semibold uppercase">
              {salaryRateType === 'hourly' ? '/hr' : '/yr'}
            </span>
          </div>

          {/* Profile Salary Target Shortcut */}
          {profileSalary && (
            <button
              type="button"
              onClick={handleApplyProfileSalary}
              className="text-[11px] text-emerald-400 hover:text-emerald-300 transition flex items-center space-x-1"
            >
              <span className="text-slate-400">Profile Target:</span>
              <span className="font-semibold underline truncate max-w-[160px]">{profileSalary}</span>
            </button>
          )}

          {/* Include Unlisted Compensation Toggle */}
          <label className="flex items-start space-x-2 text-xs text-slate-300 cursor-pointer pt-0.5">
            <input
              type="checkbox"
              checked={includeUnlistedSalary}
              onChange={handleIncludeUnlistedSalaryToggle}
              className="mt-0.5 rounded bg-slate-800 border-slate-700 text-emerald-500 focus:ring-emerald-500/40"
            />
            <div className="flex flex-col">
              <span className="font-medium text-slate-200 text-xs">Include Unlisted Pay</span>
              <span className="text-[10px] text-slate-500">
                {includeUnlistedSalary
                  ? 'Showing roles with undisclosed pay'
                  : 'Only showing roles with verified pay'}
              </span>
            </div>
          </label>
        </div>

        {/* Source Platform Section */}
        <div className="space-y-2 pt-2 border-t border-slate-800/80">
          <div className="flex items-center justify-between text-xs">
            <div className="flex items-center space-x-2 text-slate-200 font-semibold">
              <Filter className="w-3.5 h-3.5 text-emerald-400" />
              <span>Source Platform</span>
              {selectedSource !== 'all' && (
                <span className="px-1.5 py-0.2 rounded-full text-[10px] font-bold bg-emerald-950 text-emerald-300 border border-emerald-500/40">
                  1
                </span>
              )}
            </div>
            {selectedSource !== 'all' && (
              <button
                type="button"
                onClick={() => handleSourceSelect('all')}
                className="text-[11px] text-slate-400 hover:text-emerald-400 transition underline font-normal"
              >
                Clear
              </button>
            )}
          </div>
          <div className="flex flex-wrap gap-1.5 pt-1">
            {SOURCE_FILTERS.map((s) => {
              const isActive = selectedSource === s.id;
              return (
                <button
                  key={s.id}
                  type="button"
                  onClick={() => handleSourceSelect(s.id)}
                  className={`inline-flex items-center space-x-1.5 px-2.5 py-1 rounded-lg text-xs transition border ${
                    isActive
                      ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/60 font-semibold shadow-xs ring-1 ring-emerald-500/30'
                      : 'bg-slate-800/70 hover:bg-slate-700/80 text-slate-300 border-slate-700/60 hover:text-white'
                  }`}
                  title={
                    isActive
                      ? (s.id === 'all' ? 'All sources active' : `Click to remove "${s.label}" filter`)
                      : `Click to filter by "${s.label}"`
                  }
                >
                  {isActive && (
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                  )}
                  <span>{s.label}</span>
                  {isActive ? (
                    s.id === 'all' ? (
                      <Check className="w-3 h-3 ml-0.5 opacity-80" />
                    ) : (
                      <X className="w-3 h-3 ml-0.5 opacity-80 hover:opacity-100" />
                    )
                  ) : (
                    <Plus className="w-3 h-3 ml-0.5 opacity-30 hover:opacity-80" />
                  )}
                </button>
              );
            })}
          </div>
        </div>

        {/* Categorized Filter Groups (Vertical Stack) */}
        {FILTER_GROUPS.map((group) => {
          const activeInGroup = group.options.filter((opt) => selectedFilters.includes(opt.id));
          return (
            <div
              key={group.id}
              className="space-y-2 pt-3 border-t border-slate-800/80"
            >
              <div className="flex items-center justify-between text-xs">
                <div className="flex items-center space-x-2 text-slate-200 font-semibold">
                  <span>{group.icon}</span>
                  <span>{group.title}</span>
                  {activeInGroup.length > 0 && (
                    <span className="px-1.5 py-0.2 rounded-full text-[10px] font-bold bg-emerald-950 text-emerald-300 border border-emerald-500/40">
                      {activeInGroup.length}
                    </span>
                  )}
                </div>
                {activeInGroup.length > 0 && (
                  <button
                    type="button"
                    onClick={() => handleClearGroup(group.id)}
                    className="text-[11px] text-slate-400 hover:text-emerald-400 transition underline font-normal"
                  >
                    Clear
                  </button>
                )}
              </div>
              <div className="flex flex-wrap gap-1.5 pt-1">
                {group.options.map((option) => {
                  const isActive = selectedFilters.includes(option.id);
                  return (
                    <button
                      key={option.id}
                      type="button"
                      onClick={() => handleFilterToggle(option.id)}
                      className={`inline-flex items-center space-x-1.5 px-2.5 py-1 rounded-lg text-xs transition border ${
                        isActive
                          ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/60 font-semibold shadow-xs ring-1 ring-emerald-500/30'
                          : 'bg-slate-800/70 hover:bg-slate-700/80 text-slate-300 border-slate-700/60 hover:text-white'
                      }`}
                      title={
                        isActive
                          ? `Click to remove "${option.label}" filter`
                          : `Click to filter by "${option.label}"`
                      }
                    >
                      {isActive && (
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                      )}
                      <span>{option.label}</span>
                      {isActive ? (
                        <X className="w-3 h-3 ml-0.5 opacity-80 hover:opacity-100" />
                      ) : (
                        <Plus className="w-3 h-3 ml-0.5 opacity-30 hover:opacity-80" />
                      )}
                    </button>
                  );
                })}
              </div>
            </div>
          );
        })}
      </aside>

      {/* Right Main Content Area: Independent Vertical Scroll Container */}
      <main ref={mainScrollRef} className="flex-1 min-w-0 min-h-0 flex flex-col h-full max-h-full overflow-y-auto overscroll-contain p-4 sm:p-6 lg:p-8 space-y-6">
        {/* Header Banner */}
        <div className="bg-gradient-to-r from-emerald-950/40 via-slate-900 to-slate-900 border border-emerald-800/30 rounded-3xl p-6 sm:p-8 shrink-0">
          <div className="max-w-3xl space-y-3">
            <div className="flex items-center space-x-2 text-emerald-400 font-semibold text-xs tracking-wide uppercase">
              <Compass className="w-4 h-4" />
              <span>Multi-Board Live Job Aggregator</span>
            </div>
            <h1 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight">
              Discover Active Tech Opportunities
            </h1>
            <p className="text-slate-400 text-sm">
              Searches directly across <span className="text-slate-200 font-medium">Big Tech Careers (Google, Microsoft, Amazon, Apple, NVIDIA, Netflix, Salesforce)</span>, <span className="text-slate-200 font-medium">25+ Top Tech ATS Boards (OpenAI, Anthropic, Stripe, Cloudflare, Databricks...)</span>, <span className="text-slate-200 font-medium">SimplifyJobs (Entry-Level &amp; New Grad)</span>, <span className="text-slate-200 font-medium">LinkedIn</span>, <span className="text-slate-200 font-medium">Glassdoor</span>, <span className="text-slate-200 font-medium">Indeed</span>, <span className="text-slate-200 font-medium">ZipRecruiter</span>, <span className="text-slate-200 font-medium">The Muse</span>, <span className="text-slate-200 font-medium">We Work Remotely</span>, <span className="text-slate-200 font-medium">Himalayas</span>, <span className="text-slate-200 font-medium">Hacker News</span>, and <span className="text-slate-200 font-medium">RemoteOK</span>.
            </p>

            {/* Quick Career Track Presets */}
            <div className="flex flex-wrap items-center gap-2 pt-2 pb-1">
              <span className="text-xs font-semibold text-slate-400 mr-1">Target Profile:</span>
              <button
                type="button"
                onClick={() => handleSelectTrack('all')}
                className={`px-3 py-1.5 rounded-xl text-xs font-semibold transition border ${
                  activeTrack === 'all'
                    ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/50 shadow-xs'
                    : 'bg-slate-800/80 text-slate-400 hover:text-white hover:bg-slate-800 border-slate-700/60'
                }`}
                title="Search across all tech roles"
              >
                🌐 All Tech Roles
              </button>
              <button
                type="button"
                onClick={() => handleSelectTrack('software')}
                className={`px-3 py-1.5 rounded-xl text-xs font-semibold transition border ${
                  activeTrack === 'software'
                    ? 'bg-blue-500/20 text-blue-300 border-blue-500/50 shadow-xs'
                    : 'bg-slate-800/80 text-slate-400 hover:text-white hover:bg-slate-800 border-slate-700/60'
                }`}
                title="Filter for Software Developer, Backend, and Data Engineering roles (Resume 1)"
              >
                💻 Software & Backend (Resume 1)
              </button>
              <button
                type="button"
                onClick={() => handleSelectTrack('it_admin')}
                className={`px-3 py-1.5 rounded-xl text-xs font-semibold transition border ${
                  activeTrack === 'it_admin'
                    ? 'bg-purple-500/20 text-purple-300 border-purple-500/50 shadow-xs'
                    : 'bg-slate-800/80 text-slate-400 hover:text-white hover:bg-slate-800 border-slate-700/60'
                }`}
                title="Filter for IT Support, Systems Administration, and Desktop roles (Resume 2)"
              >
                🛠️ IT Support & SysAdmin (Resume 2)
              </button>
            </div>

            {/* Search Box */}
            <form onSubmit={handleSearchSubmit} className="flex flex-col sm:flex-row gap-2 pt-2">
              {/* Keyword / Role input */}
              <div className="relative flex-[1.6]">
                <Search className="w-4 h-4 absolute left-3.5 top-3 text-slate-400" />
                <input
                  type="text"
                  placeholder="Role, skills, or keywords (e.g. Senior Python, Full Stack, React)..."
                  value={query}
                  onChange={(e) => handleQueryChange(e.target.value)}
                  className="w-full pl-10 pr-10 py-2.5 bg-slate-800/90 border border-slate-700 rounded-xl text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-emerald-500/50"
                />
                {query && (
                  <button
                    type="button"
                    onClick={() => {
                      setQuery('');
                      const effective = getEffectiveSearchQuery('', selectedFilters);
                      fetchJobs(effective, selectedSource, usOnly, searchLocation, searchRadius, includeRemote);
                    }}
                    className="absolute right-3.5 top-3 text-slate-400 hover:text-slate-100 transition"
                    title="Clear search query"
                  >
                    <X className="w-4 h-4" />
                  </button>
                )}
              </div>

              {/* Location Input with GPS detection */}
              <div className="relative flex-1">
                <MapPin className="w-4 h-4 absolute left-3.5 top-3 text-emerald-400" />
                <input
                  type="text"
                  placeholder="City, State or ZIP..."
                  value={searchLocation}
                  onChange={(e) => handleLocationChange(e.target.value)}
                  className="w-full pl-10 pr-14 py-2.5 bg-slate-800/90 border border-slate-700 rounded-xl text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-emerald-500/50"
                />
                <div className="absolute right-2 top-2 flex items-center space-x-1">
                  {searchLocation ? (
                    <button
                      type="button"
                      onClick={handleClearLocation}
                      className="text-slate-400 hover:text-slate-100 transition p-1"
                      title="Clear location"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  ) : null}
                  <button
                    type="button"
                    onClick={handleDetectLocation}
                    disabled={detectingLocation}
                    className="text-slate-400 hover:text-emerald-400 transition p-1 rounded-md hover:bg-slate-700/60"
                    title="Use my current location (GPS / Geolocation)"
                  >
                    <Navigation className={`w-3.5 h-3.5 ${detectingLocation ? 'animate-spin text-emerald-400' : ''}`} />
                  </button>
                </div>
              </div>

              {/* Radius Dropdown */}
              <div className="flex items-center sm:w-36">
                <select
                  value={searchRadius}
                  onChange={(e) => handleRadiusChange(Number(e.target.value))}
                  className="w-full py-2.5 px-3 bg-slate-800/90 border border-slate-700 rounded-xl text-xs sm:text-sm text-slate-200 focus:outline-none focus:ring-2 focus:ring-emerald-500/50 cursor-pointer"
                  title="Search radius in miles"
                >
                  <option value={10}>Within 10 mi</option>
                  <option value={25}>Within 25 mi</option>
                  <option value={50}>Within 50 mi</option>
                  <option value={100}>Within 100 mi</option>
                  <option value={0}>Entire US / Any</option>
                </select>
              </div>

              {/* Search Submit Button */}
              <button
                type="submit"
                disabled={loading}
                className="px-5 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-sm shadow-md transition flex items-center justify-center space-x-2 disabled:opacity-50"
              >
                <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                <span>Search</span>
              </button>
            </form>
          </div>
        </div>
          {/* Active Filter Indicators Bar */}
        {(query.trim() || selectedFilters.length > 0 || selectedSource !== 'all' || usOnly || searchLocation.trim() || minSalary > 0 || !includeUnlistedSalary) && (
          <div className="flex flex-wrap items-center gap-2 p-2.5 bg-slate-800/50 border border-slate-700/50 rounded-xl text-xs">
            <span className="text-slate-400 flex items-center gap-1.5 font-medium">
              <Filter className="w-3.5 h-3.5 text-emerald-400" />
              <span>
                Active filters (
                {[
                  query.trim(),
                  searchLocation.trim() ? `near:${searchLocation}` : '',
                  minSalary > 0 ? `min:${minSalary}` : '',
                  !includeUnlistedSalary ? 'verified-pay-only' : '',
                  ...selectedFilters,
                  selectedSource !== 'all' ? selectedSource : '',
                ].filter(Boolean).length}
                ):
              </span>
            </span>

            {/* Compensation Pill */}
            {minSalary > 0 && (
              <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-emerald-950/70 text-emerald-300 border border-emerald-500/40 font-medium shadow-xs">
                <DollarSign className="w-3 h-3 text-emerald-400" />
                <span>
                  Pay:{' '}
                  <strong>
                    {salaryRateType === 'hourly'
                      ? `$${Math.round(minSalary / 2080)}/hr+`
                      : `$${Math.round(minSalary / 1000)}k/yr+`}
                  </strong>
                  {!includeUnlistedSalary && ' (Verified)'}
                </span>
                <button
                  type="button"
                  onClick={() => handleMinSalaryChange(0)}
                  className="hover:text-white transition p-0.5 rounded-full hover:bg-emerald-800/50"
                  title="Remove salary filter"
                >
                  <X className="w-3 h-3" />
                </button>
              </span>
            )}

            {/* Location Pill */}
            {searchLocation.trim() && (
              <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-emerald-950/70 text-emerald-300 border border-emerald-500/40 font-medium shadow-xs">
                <MapPin className="w-3 h-3 text-emerald-400" />
                <span>
                  Near: <strong>{searchLocation}</strong> {searchRadius > 0 ? `(within ${searchRadius} mi)` : ''}
                </span>
                <button
                  type="button"
                  onClick={handleClearLocation}
                  className="hover:text-white transition p-0.5 rounded-full hover:bg-emerald-800/50"
                  title="Remove location filter"
                >
                  <X className="w-3 h-3" />
                </button>
              </span>
            )}

            {/* Custom Search Query Pill */}
            {query.trim() && (
              <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-emerald-950/70 text-emerald-300 border border-emerald-500/40 font-medium shadow-xs">
                <span>Search: <strong>"{query}"</strong></span>
                <button
                  type="button"
                  onClick={() => {
                    setQuery('');
                    const effective = getEffectiveSearchQuery('', selectedFilters);
                    fetchJobs(effective, selectedSource, usOnly, searchLocation, searchRadius, includeRemote);
                  }}
                  className="hover:text-white transition p-0.5 rounded-full hover:bg-emerald-800/50"
                  title="Remove search query"
                >
                  <X className="w-3 h-3" />
                </button>
              </span>
            )}

            {/* Selected Category Filter Pills */}
            {selectedFilters.map((filterId) => {
              const option = ALL_FILTER_OPTIONS.find((o) => o.id === filterId);
              if (!option) return null;
              const groupPrefix =
                option.category === 'experience'
                  ? 'Exp'
                  : option.category === 'language'
                  ? 'Tech'
                  : option.category === 'role'
                  ? 'Role'
                  : 'Work';
              return (
                <span
                  key={filterId}
                  className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-emerald-950/70 text-emerald-300 border border-emerald-500/40 font-medium shadow-xs"
                >
                  <span className="text-emerald-400/70 font-normal">{groupPrefix}:</span>
                  <strong>{option.label}</strong>
                  <button
                    type="button"
                    onClick={() => handleFilterToggle(filterId)}
                    className="hover:text-white transition p-0.5 rounded-full hover:bg-emerald-800/50"
                    title={`Remove ${option.label} filter`}
                  >
                    <X className="w-3 h-3" />
                  </button>
                </span>
              );
            })}

            {/* Source Board Pill */}
            {selectedSource !== 'all' && (
              <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-emerald-950/70 text-emerald-300 border border-emerald-500/40 font-medium shadow-xs">
                <span className="text-emerald-400/70 font-normal">Source:</span>
                <strong>{SOURCE_FILTERS.find((s) => s.id === selectedSource)?.label || selectedSource}</strong>
                <button
                  type="button"
                  onClick={() => handleSourceSelect('all')}
                  className="hover:text-white transition p-0.5 rounded-full hover:bg-emerald-800/50"
                  title="Reset to All Sources"
                >
                  <X className="w-3 h-3" />
                </button>
              </span>
            )}

            {/* US Only Pill */}
            {usOnly && (
              <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-slate-800/80 text-emerald-400 border border-emerald-900/40 font-medium">
                <span>🇺🇸 US Jobs Only</span>
              </span>
            )}

            {/* Hide In Pipeline Pill */}
            {hidePipelineJobs && inPipelineCount > 0 && (
              <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-purple-950/70 text-purple-300 border border-purple-500/40 font-medium shadow-xs">
                <Briefcase className="w-3 h-3 text-purple-400" />
                <span>Hide In Pipeline</span>
                <button
                  type="button"
                  onClick={toggleHidePipelineJobs}
                  className="hover:text-white transition p-0.5 rounded-full hover:bg-purple-800/50"
                  title="Show in-pipeline jobs in discovery"
                >
                  <X className="w-3 h-3" />
                </button>
              </span>
            )}

            {/* Clear All Filters Button */}
            {(query.trim() || selectedFilters.length > 0 || selectedSource !== 'all') && (
              <button
                type="button"
                onClick={handleResetFilters}
                className="text-slate-400 hover:text-emerald-400 text-xs ml-auto transition underline font-medium"
              >
                Clear all filters
              </button>
            )}
          </div>
        )}

        {/* Hidden Listings Active Banner */}
        {showHiddenOnly && (
          <div className="bg-amber-950/40 border border-amber-800/50 rounded-2xl p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs text-amber-200 shrink-0">
            <div className="flex items-center space-x-2.5">
              <EyeOff className="w-4 h-4 text-amber-400 shrink-0" />
              <div>
                <span className="font-bold text-amber-300">Viewing Hidden Listings</span>
                <span className="text-amber-200/80 ml-1.5">
                  ({filteredJobs.length} hidden {filteredJobs.length === 1 ? 'listing' : 'listings'} match active filters)
                </span>
              </div>
            </div>
            <div className="flex items-center space-x-3">
              {hiddenCount > 0 && (
                <button
                  type="button"
                  onClick={handleUnhideAll}
                  className="text-slate-300 hover:text-white underline font-medium transition"
                >
                  Unhide All ({hiddenCount})
                </button>
              )}
              <button
                type="button"
                onClick={() => setShowHiddenOnly(false)}
                className="px-3 py-1.5 bg-amber-500/20 hover:bg-amber-500/30 text-amber-200 border border-amber-500/40 rounded-xl font-bold transition flex items-center space-x-1.5"
              >
                <Eye className="w-3.5 h-3.5" />
                <span>Return to Active Listings</span>
              </button>
            </div>
          </div>
        )}

        {/* Results Counter */}
        <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-400 px-1">
          <div className="flex items-center flex-wrap gap-1.5">
            <span>
              Found <strong className="text-slate-200">{filteredJobs.length}</strong> {showHiddenOnly ? 'hidden' : 'matching'} listings
              {filteredJobs.length > 0 && totalPages > 1 && (
                <span className="text-slate-400">
                  {' '}• Showing <strong className="text-emerald-400">{startIndex + 1}–{endIndex}</strong> (Page {safePage} of {totalPages})
                </span>
              )}
            </span>

            {/* In-Pipeline indicator badge/button */}
            {!showHiddenOnly && inPipelineCount > 0 && (
              <button
                type="button"
                onClick={toggleHidePipelineJobs}
                className={`inline-flex items-center space-x-1 px-2.5 py-0.5 rounded-full text-[11px] font-semibold border transition ${
                  hidePipelineJobs
                    ? 'bg-purple-950/60 text-purple-300 border-purple-800/60 hover:bg-purple-900/60'
                    : 'bg-slate-800 text-slate-300 border-slate-700 hover:text-white'
                }`}
                title={hidePipelineJobs ? 'Click to show in-pipeline jobs in discovery feed' : 'Click to hide in-pipeline jobs from discovery feed'}
              >
                <Briefcase className="w-3 h-3 text-purple-400" />
                <span>
                  {hidePipelineJobs
                    ? `${inPipelineCount} in pipeline (hidden)`
                    : `Showing ${inPipelineCount} in pipeline (click to hide)`}
                </span>
              </button>
            )}

            {!showHiddenOnly && jobs.length !== filteredJobs.length && (
              <span className="text-slate-500"> (filtered from {jobs.length} total)</span>
            )}
            {(selectedFilters.length > 0 || query.trim()) && (
              <span className="text-slate-400">
                for{' '}
                <span className="text-emerald-400 font-semibold">
                  {[
                    query.trim() ? `"${query}"` : '',
                    ...selectedFilters.map((id) => ALL_FILTER_OPTIONS.find((o) => o.id === id)?.label).filter(Boolean),
                  ]
                    .filter(Boolean)
                    .join(', ')}
                </span>
              </span>
            )}
          </div>
          {loading && <span className="text-emerald-400 animate-pulse font-medium">Fetching fresh jobs across boards...</span>}
        </div>

        {/* Empty State */}
        {filteredJobs.length === 0 && !loading ? (
          <div className="text-center py-16 bg-slate-900/40 rounded-2xl border border-slate-800 space-y-3">
            {showHiddenOnly ? (
              <>
                <EyeOff className="w-10 h-10 text-slate-600 mx-auto" />
                <p className="text-slate-300 font-medium text-sm">
                  No hidden listings found
                </p>
                <p className="text-slate-500 text-xs max-w-md mx-auto">
                  {hiddenCount === 0
                    ? 'You have not hidden any job listings yet. Click the "Hide" button on any job card to hide it from your feed.'
                    : 'None of your hidden listings match the current active search and filters.'}
                </p>
                <div className="pt-2 flex justify-center">
                  <button
                    type="button"
                    onClick={() => setShowHiddenOnly(false)}
                    className="px-4 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold transition flex items-center space-x-1.5 shadow-md"
                  >
                    <span>Return to Active Listings</span>
                  </button>
                </div>
              </>
            ) : (
              <>
                <Compass className="w-10 h-10 text-slate-600 mx-auto" />
                <p className="text-slate-300 font-medium text-sm">
                  No jobs found matching your active filter combination
                </p>
                <p className="text-slate-500 text-xs max-w-md mx-auto">
                  Try toggling off one or more filters, or search the live boards directly for this combination.
                </p>
                <div className="pt-2 flex justify-center gap-3">
                  <button
                    type="button"
                    onClick={() => {
                      const effective = getEffectiveSearchQuery(query, selectedFilters);
                      fetchJobs(effective, selectedSource, usOnly, searchLocation, searchRadius, includeRemote, minSalary, includeUnlistedSalary, true);
                    }}
                    className="px-4 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold transition flex items-center space-x-1.5 shadow-md"
                  >
                    <RefreshCw className="w-3.5 h-3.5" />
                    <span>Fetch Live Across Boards</span>
                  </button>
                  <button
                    type="button"
                    onClick={handleResetFilters}
                    className="px-4 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium border border-slate-700 transition"
                  >
                    Reset All Filters
                  </button>
                </div>
              </>
            )}
          </div>
        ) : (
          <div className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {paginatedJobs.map((job, idx) => {
              const matchingPipelineJob = pipelineMatchMap.get(job.url) || (addedUrls.has(job.url) ? { status: 'TO_APPLY' } as Job : undefined);
              const isAdded = Boolean(matchingPipelineJob || addedUrls.has(job.url));
              const isAddingThis = addingUrl === job.url;

              return (
                <div
                  key={`${job.company}-${job.title}-${idx}`}
                  className={`bg-slate-800/80 hover:bg-slate-800 border rounded-2xl p-5 flex flex-col justify-between shadow-md hover:shadow-xl transition ${
                    matchingPipelineJob
                      ? 'border-purple-500/60 ring-1 ring-purple-500/30'
                      : 'border-slate-700/60'
                  }`}
                >
                  <div className="space-y-2.5">
                    {/* Header */}
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center space-x-2 text-xs font-semibold text-slate-300 min-w-0">
                        <Building2 className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                        <span className="truncate max-w-[150px] sm:max-w-[180px]">{job.company}</span>
                      </div>
                      <div className="flex items-center space-x-1.5 shrink-0">
                        {matchingPipelineJob && (
                          <span
                            className="text-[10px] px-2 py-0.5 rounded-full border font-semibold flex items-center space-x-1 bg-purple-950/80 text-purple-300 border-purple-700/60 shrink-0"
                            title={`Already in your pipeline under "${PIPELINE_STATUS_LABELS[matchingPipelineJob.status] || matchingPipelineJob.status}"`}
                          >
                            <Briefcase className="w-3 h-3 text-purple-400 shrink-0" />
                            <span>In Pipeline: {PIPELINE_STATUS_LABELS[matchingPipelineJob.status] || matchingPipelineJob.status}</span>
                          </span>
                        )}
                        <span className={`text-[10px] px-2 py-0.5 rounded-full border font-mono font-semibold uppercase shrink-0 ${getSourceBadge(job.source)}`}>
                          {job.source}
                        </span>
                      </div>
                    </div>

                    {/* Role Title */}
                    <h3 className="font-bold text-slate-100 text-base leading-snug line-clamp-2">
                      {job.title}
                    </h3>

                    {/* Meta info */}
                    <div className="flex flex-wrap items-center gap-1.5 text-xs">
                      <span className="inline-flex items-center space-x-1 text-slate-400 bg-slate-900/60 px-2 py-0.5 rounded border border-slate-700/40">
                        <MapPin className="w-3 h-3 text-slate-400 shrink-0" />
                        <span className="truncate max-w-[120px]">{job.location || 'Remote'}</span>
                      </span>

                      {formatSalaryBadge(job.salary_min, job.salary_max, job.salary_currency, salaryRateType) && (
                        <span
                          className="inline-flex items-center space-x-1 text-emerald-400 bg-emerald-950/40 px-2 py-0.5 rounded border border-emerald-800/40 font-medium cursor-help"
                          title={
                            salaryRateType === 'hourly'
                              ? `Approx. annual: $${Math.round((job.salary_min || 0) / 1000)}k${job.salary_max ? ` - $${Math.round(job.salary_max / 1000)}k` : ''}/yr`
                              : `Approx. hourly: $${Math.round((job.salary_min || 0) / 2080)}${job.salary_max ? ` - $${Math.round(job.salary_max / 2080)}` : ''}/hr`
                          }
                        >
                          <DollarSign className="w-3 h-3 shrink-0" />
                          <span>{formatSalaryBadge(job.salary_min, job.salary_max, job.salary_currency, salaryRateType)}</span>
                        </span>
                      )}
                    </div>

                    {/* Tags */}
                    {job.tags && job.tags.length > 0 && (
                      <div className="flex flex-wrap gap-1 pt-1">
                        {job.tags.slice(0, 4).map((tag, tIdx) => (
                          <span
                            key={tIdx}
                            className="text-[10px] px-2 py-0.5 rounded bg-slate-900/60 text-slate-400 border border-slate-800"
                          >
                            {tag}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Actions */}
                  <div className="pt-4 mt-4 border-t border-slate-700/60 flex items-center justify-between gap-2">
                    <div className="flex items-center space-x-3 shrink-0">
                      <a
                        href={job.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-xs text-slate-400 hover:text-emerald-400 flex items-center space-x-1 transition shrink-0"
                      >
                        <span>Posting</span>
                        <ExternalLink className="w-3 h-3" />
                      </a>
                      {showHiddenOnly ? (
                        <button
                          type="button"
                          onClick={() => handleUnhideJob(job.url)}
                          className="text-xs text-emerald-400 hover:text-emerald-300 flex items-center space-x-1 transition shrink-0 font-medium"
                          title="Restore listing to active feed"
                        >
                          <Eye className="w-3 h-3" />
                          <span>Unhide</span>
                        </button>
                      ) : (
                        <button
                          type="button"
                          onClick={() => handleHideJob(job)}
                          className="text-xs text-slate-500 hover:text-rose-400 flex items-center space-x-1 transition shrink-0"
                          title="Hide this listing"
                        >
                          <EyeOff className="w-3 h-3" />
                          <span>Hide</span>
                        </button>
                      )}
                    </div>

                    {matchingPipelineJob ? (
                      <button
                        type="button"
                        disabled
                        className="flex items-center space-x-1.5 px-3 py-1.5 rounded-xl text-xs font-bold bg-purple-950/70 text-purple-300 border border-purple-800/60 cursor-default shadow-xs shrink-0"
                        title={`This job is already tracked in your pipeline under "${PIPELINE_STATUS_LABELS[matchingPipelineJob.status] || matchingPipelineJob.status}"`}
                      >
                        <Check className="w-3.5 h-3.5 text-purple-400" />
                        <span>In Pipeline ({PIPELINE_STATUS_LABELS[matchingPipelineJob.status] || matchingPipelineJob.status})</span>
                      </button>
                    ) : (
                      <button
                        onClick={() => handleAddJob(job)}
                        disabled={isAdded || isAddingThis}
                        className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-xl text-xs font-bold transition shadow-xs shrink-0 ${
                          isAdded
                            ? 'bg-slate-700 text-emerald-400 cursor-default'
                            : 'bg-emerald-600 hover:bg-emerald-500 text-white'
                        } disabled:opacity-70`}
                      >
                        {isAdded ? (
                          <>
                            <Check className="w-3.5 h-3.5" />
                            <span>Added to Pipeline</span>
                          </>
                        ) : (
                          <>
                            <Plus className="w-3.5 h-3.5" />
                            <span>{isAddingThis ? 'Adding...' : 'Add to Pipeline'}</span>
                          </>
                        )}
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

            {/* Pagination Controls Bar */}
            {totalPages > 1 && (
              <div className="pt-3 pb-8 border-t border-slate-800 flex flex-col sm:flex-row items-center justify-between gap-4 text-xs">
                <div className="text-slate-400">
                  Showing <strong className="text-slate-200">{startIndex + 1}</strong> to{' '}
                  <strong className="text-slate-200">{endIndex}</strong> of{' '}
                  <strong className="text-slate-200">{filteredJobs.length}</strong> listings
                </div>

                <div className="flex items-center space-x-1.5">
                  <button
                    type="button"
                    onClick={() => handlePageChange(safePage - 1)}
                    disabled={safePage <= 1}
                    className="flex items-center space-x-1 px-3 py-1.5 rounded-xl border border-slate-700 bg-slate-800/80 hover:bg-slate-700 disabled:opacity-30 disabled:pointer-events-none text-slate-300 hover:text-white transition font-medium"
                    title="Previous page"
                  >
                    <ChevronLeft className="w-4 h-4" />
                    <span>Prev</span>
                  </button>

                  <div className="flex items-center space-x-1 px-1">
                    {getPageNumbers().map((p, idx) => {
                      if (typeof p === 'string') {
                        return (
                          <span key={`ellipsis-${idx}`} className="px-2 text-slate-500 font-bold select-none">
                            ...
                          </span>
                        );
                      }
                      const isCurrent = p === safePage;
                      return (
                        <button
                          key={p}
                          type="button"
                          onClick={() => handlePageChange(p)}
                          className={`min-w-[32px] h-8 px-2 rounded-xl text-xs font-semibold border transition flex items-center justify-center ${
                            isCurrent
                              ? 'bg-emerald-600 border-emerald-500 text-white shadow-sm ring-1 ring-emerald-500/40'
                              : 'bg-slate-800/70 border-slate-700/70 text-slate-300 hover:text-white hover:bg-slate-700'
                          }`}
                        >
                          {p}
                        </button>
                      );
                    })}
                  </div>

                  <button
                    type="button"
                    onClick={() => handlePageChange(safePage + 1)}
                    disabled={safePage >= totalPages}
                    className="flex items-center space-x-1 px-3 py-1.5 rounded-xl border border-slate-700 bg-slate-800/80 hover:bg-slate-700 disabled:opacity-30 disabled:pointer-events-none text-slate-300 hover:text-white transition font-medium"
                    title="Next page"
                  >
                    <span>Next</span>
                    <ChevronRight className="w-4 h-4" />
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </main>

      {/* Manage Hidden Listings Modal */}
      {isManageHiddenOpen && (
        <div className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-3xl w-full max-w-2xl max-h-[85vh] flex flex-col shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-150">
            {/* Modal Header */}
            <div className="p-5 border-b border-slate-800 flex items-center justify-between">
              <div className="flex items-center space-x-2.5">
                <div className="p-2 bg-amber-500/10 text-amber-400 rounded-xl">
                  <EyeOff className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-white">Hidden Listings</h3>
                  <p className="text-xs text-slate-400">{hiddenCount} total hidden {hiddenCount === 1 ? 'listing' : 'listings'}</p>
                </div>
              </div>
              <div className="flex items-center space-x-2">
                {hiddenCount > 0 && (
                  <button
                    type="button"
                    onClick={handleUnhideAll}
                    className="px-3 py-1.5 rounded-xl text-xs font-medium text-rose-400 hover:text-rose-300 hover:bg-rose-950/30 border border-rose-900/40 transition"
                  >
                    Unhide All
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => setIsManageHiddenOpen(false)}
                  className="p-1.5 text-slate-400 hover:text-white rounded-xl hover:bg-slate-800 transition"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
            </div>

            {/* Modal Body */}
            <div className="flex-1 overflow-y-auto p-5 space-y-3">
              {hiddenCount === 0 ? (
                <div className="py-12 text-center text-slate-400 text-xs space-y-2">
                  <EyeOff className="w-8 h-8 text-slate-600 mx-auto" />
                  <p className="text-slate-300 font-medium">No hidden listings</p>
                  <p className="text-slate-500 max-w-xs mx-auto">When you click "Hide" on any job card, it will be saved here so you can easily restore it anytime.</p>
                </div>
              ) : (
                Object.values(hiddenJobsMap).map((job) => (
                  <div
                    key={job.url}
                    className="bg-slate-800/60 border border-slate-700/60 rounded-xl p-3.5 flex items-center justify-between gap-3 hover:bg-slate-800 transition"
                  >
                    <div className="min-w-0 flex-1 space-y-1">
                      <div className="flex items-center space-x-2">
                        <span className="font-semibold text-slate-200 text-sm truncate">{job.title}</span>
                        <span className={`text-[10px] px-1.5 py-0.2 rounded-full border uppercase font-mono ${getSourceBadge(job.source)}`}>
                          {job.source}
                        </span>
                      </div>
                      <div className="flex items-center space-x-3 text-xs text-slate-400">
                        <span>{job.company}</span>
                        <span>•</span>
                        <span>{job.location || 'Remote'}</span>
                      </div>
                    </div>

                    <div className="flex items-center space-x-2 shrink-0">
                      <a
                        href={job.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="p-1.5 text-slate-400 hover:text-emerald-400 rounded-lg hover:bg-slate-700 transition"
                        title="Open posting"
                      >
                        <ExternalLink className="w-4 h-4" />
                      </a>
                      <button
                        type="button"
                        onClick={() => handleUnhideJob(job.url)}
                        className="px-3 py-1.5 rounded-lg text-xs font-bold bg-emerald-600/20 text-emerald-300 hover:bg-emerald-600/30 border border-emerald-500/40 transition flex items-center space-x-1"
                      >
                        <Eye className="w-3.5 h-3.5" />
                        <span>Unhide</span>
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>

            {/* Modal Footer */}
            <div className="p-4 border-t border-slate-800 bg-slate-900/50 flex justify-end">
              <button
                type="button"
                onClick={() => setIsManageHiddenOpen(false)}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-white rounded-xl text-xs font-bold transition"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Floating Undo Toast */}
      {toastJob && (
        <div className="fixed bottom-6 right-6 z-50 flex items-center space-x-3 bg-slate-800 text-white border border-slate-700 px-4 py-3 rounded-2xl shadow-2xl animate-in fade-in slide-in-from-bottom-5 duration-200">
          <EyeOff className="w-4 h-4 text-rose-400 shrink-0" />
          <div className="text-xs max-w-xs truncate">
            Hidden <span className="font-semibold text-slate-200">{toastJob.title}</span> at <span className="text-slate-300">{toastJob.company}</span>
          </div>
          <button
            type="button"
            onClick={handleUndoHide}
            className="text-xs font-bold text-emerald-400 hover:text-emerald-300 underline pl-1 shrink-0 flex items-center space-x-1"
          >
            <Undo2 className="w-3 h-3" />
            <span>Undo</span>
          </button>
          <button
            type="button"
            onClick={() => setToastJob(null)}
            className="text-slate-400 hover:text-white p-0.5 ml-1"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}
    </div>
  );
};
