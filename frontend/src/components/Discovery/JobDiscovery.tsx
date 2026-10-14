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
  Undo2
} from 'lucide-react';
import { DiscoveredJob, Job } from '../../types';
import { api } from '../../api/client';

interface JobDiscoveryProps {
  onJobAdded: (job: Job) => void;
  onOpenSettings?: (tab?: 'ai' | 'hidden') => void;
}

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
      { id: 'javascript', label: 'JavaScript', category: 'language' },
      { id: 'typescript', label: 'TypeScript', category: 'language' },
      { id: 'react', label: 'React', category: 'language' },
      { id: 'nodejs', label: 'Node.js', category: 'language' },
      { id: 'golang', label: 'Go / Golang', category: 'language' },
      { id: 'java', label: 'Java', category: 'language' },
      { id: 'csharp', label: 'C# / .NET', category: 'language' },
      { id: 'cpp', label: 'C / C++', category: 'language' },
      { id: 'rust', label: 'Rust', category: 'language' },
      { id: 'sql', label: 'SQL', category: 'language' },
      { id: 'aws', label: 'AWS / Cloud', category: 'language' },
    ],
  },
  {
    id: 'role',
    title: 'Role & Discipline',
    icon: <Compass className="w-4 h-4 text-cyan-400" />,
    options: [
      { id: 'fullstack', label: 'Full Stack', category: 'role' },
      { id: 'frontend', label: 'Frontend', category: 'role' },
      { id: 'backend', label: 'Backend', category: 'role' },
      { id: 'devops', label: 'DevOps / SRE', category: 'role' },
      { id: 'data_ai', label: 'Data / AI / ML', category: 'role' },
      { id: 'mobile', label: 'Mobile', category: 'role' },
      { id: 'security', label: 'Security', category: 'role' },
      { id: 'qa', label: 'QA / Testing', category: 'role' },
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
  { id: 'indeed', label: 'Indeed' },
  { id: 'ziprecruiter', label: 'ZipRecruiter' },
  { id: 'arbeitnow', label: 'Arbeitnow' },
  { id: 'jobicy', label: 'Jobicy' },
  { id: 'weworkremotely', label: 'We Work Remotely' },
  { id: 'himalayas', label: 'Himalayas' },
  { id: 'hackernews', label: 'HN "Who is Hiring?"' },
  { id: 'remoteok', label: 'RemoteOK' },
  { id: 'adzuna', label: 'Adzuna API' },
];

const matchesOption = (optionId: string, fullText: string, job: DiscoveredJob): boolean => {
  const loc = (job.location || '').toLowerCase();
  const title = (job.title || '').toLowerCase();
  const workplace = (job.workplace_type || '').toLowerCase();

  switch (optionId) {
    // Experience Level
    case 'junior':
      return (
        fullText.includes('junior') ||
        fullText.includes('entry level') ||
        fullText.includes('entry-level') ||
        fullText.includes('associate') ||
        fullText.includes('new grad') ||
        fullText.includes('graduate') ||
        fullText.includes('early career') ||
        fullText.includes('apprentice') ||
        fullText.includes('0-2 years') ||
        fullText.includes('1-2 years') ||
        fullText.includes('0-1 year') ||
        /\bjr\.?\b/i.test(title) ||
        /\b(software engineer|developer|engineer|analyst|programmer)\s+(i|1)\b/i.test(title) ||
        /\b(level|tier)\s+(i|1)\b/i.test(title)
      );
    case 'mid':
      return (
        fullText.includes('mid-level') ||
        fullText.includes('mid level') ||
        fullText.includes('intermediate') ||
        fullText.includes('2-5 years') ||
        fullText.includes('3-5 years') ||
        /\b(ii|2)\b/i.test(title) ||
        (!title.includes('senior') &&
          !title.includes('lead') &&
          !title.includes('principal') &&
          !title.includes('director') &&
          !title.includes('manager') &&
          !title.includes('junior') &&
          !title.includes('intern'))
      );
    case 'senior':
      return (
        title.includes('senior') ||
        /\bsr\.?\b/i.test(title) ||
        fullText.includes('senior engineer') ||
        fullText.includes('senior developer') ||
        fullText.includes('5+ years') ||
        fullText.includes('6+ years') ||
        fullText.includes('7+ years')
      );
    case 'lead':
      return (
        title.includes('lead') ||
        title.includes('staff') ||
        title.includes('principal') ||
        fullText.includes('tech lead') ||
        fullText.includes('team lead')
      );
    case 'manager':
      return (
        title.includes('manager') ||
        title.includes('director') ||
        title.includes('vp') ||
        title.includes('head of') ||
        fullText.includes('engineering manager')
      );

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

    // Role & Discipline
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
  fullstack: 'full stack',
  frontend: 'frontend',
  backend: 'backend',
  devops: 'devops',
  data_ai: 'data',
  mobile: 'mobile',
  security: 'security',
  qa: 'qa',

  // Tech / Language
  python: 'python',
  javascript: 'javascript',
  typescript: 'typescript',
  react: 'react',
  nodejs: 'nodejs',
  golang: 'golang',
  java: 'java',
  csharp: 'c#',
  cpp: 'c++',
  rust: 'rust',
  sql: 'sql',
  aws: 'aws',
};

const getEffectiveSearchQuery = (customQuery: string, activeFilterIds: string[]): string => {
  const parts: string[] = [];

  if (customQuery.trim()) {
    parts.push(customQuery.trim());
  }

  // 1. Experience keywords
  const expFilters = activeFilterIds.filter((id) =>
    ['junior', 'mid', 'senior', 'lead', 'manager'].includes(id)
  );
  if (expFilters.length > 0) {
    parts.push(FILTER_SEARCH_TERMS[expFilters[0]] || expFilters[0]);
  }

  // 2. Tech / Language keywords
  const langFilters = activeFilterIds.filter((id) =>
    ['python', 'javascript', 'typescript', 'react', 'nodejs', 'golang', 'java', 'csharp', 'cpp', 'rust', 'sql', 'aws'].includes(id)
  );
  if (langFilters.length > 0) {
    parts.push(FILTER_SEARCH_TERMS[langFilters[0]] || langFilters[0]);
  }

  // 3. Role keywords
  const roleFilters = activeFilterIds.filter((id) =>
    ['fullstack', 'frontend', 'backend', 'devops', 'data_ai', 'mobile', 'security', 'qa'].includes(id)
  );
  if (roleFilters.length > 0) {
    parts.push(FILTER_SEARCH_TERMS[roleFilters[0]] || roleFilters[0]);
  } else if (!customQuery.trim() && langFilters.length === 0) {
    // Default core discipline so the query is recognized on job boards
    parts.push('developer');
  }

  // 4. Workplace keywords (e.g. remote)
  const wpFilters = activeFilterIds.filter((id) =>
    ['remote', 'hybrid', 'contract', 'internship'].includes(id)
  );
  if (wpFilters.length > 0) {
    parts.push(FILTER_SEARCH_TERMS[wpFilters[0]] || wpFilters[0]);
  }

  return parts.join(' ').trim() || 'developer';
};

export const JobDiscovery: React.FC<JobDiscoveryProps> = ({ onJobAdded, onOpenSettings }) => {
  const [query, setQuery] = useState('');
  const [selectedFilters, setSelectedFilters] = useState<string[]>([]);
  const [selectedSource, setSelectedSource] = useState('all');
  const [usOnly, setUsOnly] = useState(true);
  const [isFiltersExpanded, setIsFiltersExpanded] = useState(true);
  const [loading, setLoading] = useState(false);
  const [jobs, setJobs] = useState<DiscoveredJob[]>([]);
  const [addedUrls, setAddedUrls] = useState<Set<string>>(new Set());
  const [addingUrl, setAddingUrl] = useState<string | null>(null);

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
  const toastTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

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
    searchQuery: string = '',
    source: string = selectedSource,
    isUsOnly: boolean = usOnly
  ) => {
    setLoading(true);
    try {
      const adzunaId = localStorage.getItem('job_pulse_adzuna_app_id') || undefined;
      const adzunaKey = localStorage.getItem('job_pulse_adzuna_app_key') || undefined;
      const effectiveQuery = searchQuery.trim() || 'developer';
      const results = await api.searchDiscoveredJobs(effectiveQuery, source, adzunaId, adzunaKey, isUsOnly);
      setJobs(results);
    } catch (err) {
      console.error('Failed to search jobs:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchJobs('developer', 'all', true);
    return () => {
      if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
      if (toastTimeoutRef.current) clearTimeout(toastTimeoutRef.current);
    };
  }, []);

  const handleFilterToggle = (filterId: string) => {
    const nextFilters = selectedFilters.includes(filterId)
      ? selectedFilters.filter((id) => id !== filterId)
      : [...selectedFilters, filterId];
    setSelectedFilters(nextFilters);

    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }
    debounceTimerRef.current = setTimeout(() => {
      const effectiveQuery = getEffectiveSearchQuery(query, nextFilters);
      fetchJobs(effectiveQuery, selectedSource, usOnly);
    }, 450);
  };

  const handleClearGroup = (groupId: string) => {
    const group = FILTER_GROUPS.find((g) => g.id === groupId);
    if (!group) return;
    const groupOptionIds = new Set(group.options.map((o) => o.id));
    const nextFilters = selectedFilters.filter((id) => !groupOptionIds.has(id));
    setSelectedFilters(nextFilters);

    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }
    debounceTimerRef.current = setTimeout(() => {
      const effectiveQuery = getEffectiveSearchQuery(query, nextFilters);
      fetchJobs(effectiveQuery, selectedSource, usOnly);
    }, 450);
  };

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }
    const effectiveQuery = getEffectiveSearchQuery(query, selectedFilters);
    fetchJobs(effectiveQuery, selectedSource, usOnly);
  };

  const handleSourceSelect = (sourceId: string) => {
    const nextSource = selectedSource === sourceId && sourceId !== 'all' ? 'all' : sourceId;
    setSelectedSource(nextSource);
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }
    const effectiveQuery = getEffectiveSearchQuery(query, selectedFilters);
    fetchJobs(effectiveQuery, nextSource, usOnly);
  };

  const handleResetFilters = () => {
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }
    setQuery('');
    setSelectedFilters([]);
    setSelectedSource('all');
    fetchJobs('developer', 'all', usOnly);
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
      // 0. Company blacklist filter (excludes recruiter/company postings permanently when active)
      if (!showHiddenOnly && blockedCompanies.length > 0) {
        const comp = (job.company || '').toLowerCase();
        if (blockedCompanies.some((b) => b && comp.includes(b.toLowerCase()))) {
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

      // 2. Custom typed keyword filter (all words must match)
      if (query.trim()) {
        const words = query.toLowerCase().trim().split(/\s+/).filter(Boolean);
        const matchesAll = words.every((w) => fullText.includes(w));
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
  }, [jobs, hiddenJobsMap, hiddenUrls, showHiddenOnly, selectedSource, selectedFilters, query, blockedCompanies]);

  // Reset pagination to page 1 whenever search, filters, source, or view mode changes
  useEffect(() => {
    setCurrentPage(1);
  }, [query, selectedFilters, selectedSource, usOnly, showHiddenOnly]);

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
        status: 'WISHLIST',
      });
      setAddedUrls((prev) => new Set(prev).add(job.url));
      onJobAdded(created);
    } catch (err) {
      console.error('Failed to add job:', err);
    } finally {
      setAddingUrl(null);
    }
  };

  const getSourceBadge = (source: string) => {
    switch (source.toLowerCase()) {
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
              Searches directly across <span className="text-slate-200 font-medium">Indeed</span>, <span className="text-slate-200 font-medium">ZipRecruiter</span>, <span className="text-slate-200 font-medium">Arbeitnow</span>, <span className="text-slate-200 font-medium">Jobicy</span>, <span className="text-slate-200 font-medium">We Work Remotely</span>, <span className="text-slate-200 font-medium">Himalayas</span>, <span className="text-slate-200 font-medium">Hacker News</span>, and <span className="text-slate-200 font-medium">RemoteOK</span>.
            </p>

            {/* Search Box */}
            <form onSubmit={handleSearchSubmit} className="flex gap-2 pt-2">
              <div className="relative flex-1">
                <Search className="w-4 h-4 absolute left-3.5 top-3 text-slate-400" />
                <input
                  type="text"
                  placeholder="Search job title, skills, or keywords (e.g. Senior Python, Full Stack, React)..."
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  className="w-full pl-10 pr-10 py-2.5 bg-slate-800/90 border border-slate-700 rounded-xl text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-emerald-500/50"
                />
                {query && (
                  <button
                    type="button"
                    onClick={() => {
                      setQuery('');
                      fetchJobs('', selectedSource);
                    }}
                    className="absolute right-3.5 top-3 text-slate-400 hover:text-slate-100 transition"
                    title="Clear search query"
                  >
                    <X className="w-4 h-4" />
                  </button>
                )}
              </div>
              <button
                type="submit"
                disabled={loading}
                className="px-5 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-sm shadow-md transition flex items-center space-x-2 disabled:opacity-50"
              >
                <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                <span>Search</span>
              </button>
            </form>
          </div>
        </div>
          {/* Active Filter Indicators Bar */}
        {(query.trim() || selectedFilters.length > 0 || selectedSource !== 'all' || usOnly) && (
          <div className="flex flex-wrap items-center gap-2 p-2.5 bg-slate-800/50 border border-slate-700/50 rounded-xl text-xs">
            <span className="text-slate-400 flex items-center gap-1.5 font-medium">
              <Filter className="w-3.5 h-3.5 text-emerald-400" />
              <span>
                Active filters (
                {[
                  query.trim(),
                  ...selectedFilters,
                  selectedSource !== 'all' ? selectedSource : '',
                ].filter(Boolean).length}
                ):
              </span>
            </span>

            {/* Custom Search Query Pill */}
            {query.trim() && (
              <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-emerald-950/70 text-emerald-300 border border-emerald-500/40 font-medium shadow-xs">
                <span>Search: <strong>"{query}"</strong></span>
                <button
                  type="button"
                  onClick={() => {
                    setQuery('');
                    const effective = getEffectiveSearchQuery('', selectedFilters);
                    fetchJobs(effective, selectedSource, usOnly);
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
        <div className="flex items-center justify-between text-xs text-slate-400 px-1">
          <span>
            Found <strong className="text-slate-200">{filteredJobs.length}</strong> {showHiddenOnly ? 'hidden' : 'matching'} listings
            {filteredJobs.length > 0 && totalPages > 1 && (
              <span className="text-slate-400">
                {' '}• Showing <strong className="text-emerald-400">{startIndex + 1}–{endIndex}</strong> (Page {safePage} of {totalPages})
              </span>
            )}
            {!showHiddenOnly && jobs.length !== filteredJobs.length && (
              <span className="text-slate-500"> (filtered from {jobs.length} total)</span>
            )}
            {(selectedFilters.length > 0 || query.trim()) && (
              <span className="ml-1 text-slate-400">
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
          </span>
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
                      fetchJobs(effective, selectedSource, usOnly);
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
              const isAdded = addedUrls.has(job.url);
              const isAddingThis = addingUrl === job.url;

              return (
                <div
                  key={`${job.company}-${job.title}-${idx}`}
                  className="bg-slate-800/80 hover:bg-slate-800 border border-slate-700/60 rounded-2xl p-5 flex flex-col justify-between shadow-md hover:shadow-xl transition"
                >
                  <div className="space-y-2.5">
                    {/* Header */}
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center space-x-2 text-xs font-semibold text-slate-300 min-w-0">
                        <Building2 className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                        <span className="truncate max-w-[150px] sm:max-w-[180px]">{job.company}</span>
                      </div>
                      <span className={`text-[10px] px-2 py-0.5 rounded-full border font-mono font-semibold uppercase shrink-0 ${getSourceBadge(job.source)}`}>
                        {job.source}
                      </span>
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

                      {job.salary_min && (
                        <span className="inline-flex items-center space-x-1 text-emerald-400 bg-emerald-950/40 px-2 py-0.5 rounded border border-emerald-800/40 font-medium">
                          <DollarSign className="w-3 h-3 shrink-0" />
                          <span>${Math.round(job.salary_min / 1000)}k+</span>
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
