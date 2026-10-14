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
  ChevronUp
} from 'lucide-react';
import { DiscoveredJob, Job } from '../../types';
import { api } from '../../api/client';

interface JobDiscoveryProps {
  onJobAdded: (job: Job) => void;
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
        fullText.includes('0-2 years') ||
        fullText.includes('1-2 years') ||
        /\bjr\.?\b/i.test(title)
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
        fullText.includes('anywhere')
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

const getEffectiveSearchQuery = (customQuery: string, activeFilterIds: string[]): string => {
  if (customQuery.trim()) {
    return customQuery.trim();
  }
  // Find active language or role options to use as search keywords
  const activeRoles = FILTER_GROUPS.find((g) => g.id === 'role')
    ?.options.filter((o) => activeFilterIds.includes(o.id))
    .map((o) => o.label) || [];
  const activeLangs = FILTER_GROUPS.find((g) => g.id === 'language')
    ?.options.filter((o) => activeFilterIds.includes(o.id))
    .map((o) => o.label) || [];

  const keywords = [...activeRoles, ...activeLangs].slice(0, 2);
  if (keywords.length > 0) {
    return keywords.join(' ');
  }

  const activeExp = FILTER_GROUPS.find((g) => g.id === 'experience')
    ?.options.filter((o) => activeFilterIds.includes(o.id))
    .map((o) => o.label) || [];
  if (activeExp.length > 0) {
    return `${activeExp[0]} developer`;
  }

  return 'developer';
};

export const JobDiscovery: React.FC<JobDiscoveryProps> = ({ onJobAdded }) => {
  const [query, setQuery] = useState('');
  const [selectedFilters, setSelectedFilters] = useState<string[]>([]);
  const [selectedSource, setSelectedSource] = useState('all');
  const [usOnly, setUsOnly] = useState(true);
  const [isFiltersExpanded, setIsFiltersExpanded] = useState(true);
  const [loading, setLoading] = useState(false);
  const [jobs, setJobs] = useState<DiscoveredJob[]>([]);
  const [addedUrls, setAddedUrls] = useState<Set<string>>(new Set());
  const [addingUrl, setAddingUrl] = useState<string | null>(null);

  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

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
    setSelectedSource(sourceId);
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }
    const effectiveQuery = getEffectiveSearchQuery(query, selectedFilters);
    fetchJobs(effectiveQuery, sourceId, usOnly);
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
  // - Matches source platform
  // - Matches every custom search query word
  // - Category logic: AND across categories, OR within same category
  const filteredJobs = useMemo(() => {
    return jobs.filter((job) => {
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
      // Across different categories: AND (job must satisfy EVERY active category)
      // Within the same category: OR (job matches ANY selected option in that category)
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
  }, [jobs, selectedSource, selectedFilters, query]);

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
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
      {/* Header Banner */}
      <div className="bg-gradient-to-r from-emerald-950/40 via-slate-900 to-slate-900 border border-emerald-800/30 rounded-3xl p-6 sm:p-8">
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

      {/* Main Layout: Left Vertical Filters Sidebar + Right Job Feed */}
      <div className="flex flex-col lg:flex-row gap-6 items-start">
        {/* Mobile Toggle Button for Filters (visible on small screens only) */}
        <div className="w-full lg:hidden">
          <button
            type="button"
            onClick={() => setIsFiltersExpanded(!isFiltersExpanded)}
            className="w-full flex items-center justify-between p-3.5 rounded-2xl bg-slate-900 border border-slate-800 text-slate-200 font-bold text-xs shadow-md"
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
              <span>{isFiltersExpanded ? 'Hide' : 'Show'}</span>
              {isFiltersExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            </div>
          </button>
        </div>

        {/* Left Sidebar: Vertically Oriented Filters */}
        <aside
          className={`${
            isFiltersExpanded ? 'block' : 'hidden'
          } lg:block w-full lg:w-72 xl:w-80 shrink-0 space-y-4 lg:sticky lg:top-6 lg:max-h-[calc(100vh-3rem)] lg:overflow-y-auto pr-1`}
        >
          <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-4 sm:p-5 space-y-4 shadow-xl backdrop-blur-sm">
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

            {/* Source Platform Section */}
            <div className="space-y-2 pt-2 border-t border-slate-800/80">
              <div className="flex items-center justify-between text-xs font-semibold text-slate-200">
                <div className="flex items-center space-x-2">
                  <Filter className="w-3.5 h-3.5 text-emerald-400" />
                  <span>Source Platform</span>
                </div>
                {selectedSource !== 'all' && (
                  <button
                    type="button"
                    onClick={() => handleSourceSelect('all')}
                    className="text-[11px] text-slate-400 hover:text-emerald-400 transition underline font-normal"
                  >
                    All
                  </button>
                )}
              </div>
              <div className="flex flex-wrap gap-1.5 pt-0.5">
                {SOURCE_FILTERS.map((s) => (
                  <button
                    key={s.id}
                    type="button"
                    onClick={() => handleSourceSelect(s.id)}
                    className={`px-2.5 py-1 rounded-lg text-xs font-medium border transition ${
                      selectedSource === s.id
                        ? 'bg-emerald-600 border-emerald-500 text-white shadow-xs font-semibold'
                        : 'bg-slate-800/80 border-slate-700/80 text-slate-400 hover:text-white hover:bg-slate-700'
                    }`}
                  >
                    {s.label}
                  </button>
                ))}
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
          </div>
        </aside>

        {/* Right Main Content: Active Filter Bar, Count, & Job Listings */}
        <main className="flex-1 min-w-0 space-y-4 w-full">
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
              <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-slate-800 text-slate-200 border border-slate-700 font-medium">
                <span>Source: <strong>{SOURCE_FILTERS.find((s) => s.id === selectedSource)?.label || selectedSource}</strong></span>
                <button
                  type="button"
                  onClick={() => handleSourceSelect('all')}
                  className="hover:text-white transition p-0.5 rounded-full hover:bg-slate-700"
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

        {/* Results Counter */}
        <div className="flex items-center justify-between text-xs text-slate-400 px-1">
          <span>
            Found <strong className="text-slate-200">{filteredJobs.length}</strong> matching listings
            {jobs.length !== filteredJobs.length && (
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
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {filteredJobs.map((job, idx) => {
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
                      <div className="flex items-center space-x-2 text-xs font-semibold text-slate-300">
                        <Building2 className="w-3.5 h-3.5 text-slate-400" />
                        <span className="truncate max-w-[160px]">{job.company}</span>
                      </div>
                      <span className={`text-[10px] px-2 py-0.5 rounded-full border font-mono font-semibold uppercase ${getSourceBadge(job.source)}`}>
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
                        <MapPin className="w-3 h-3 text-slate-400" />
                        <span className="truncate max-w-[120px]">{job.location || 'Remote'}</span>
                      </span>

                      {job.salary_min && (
                        <span className="inline-flex items-center space-x-1 text-emerald-400 bg-emerald-950/40 px-2 py-0.5 rounded border border-emerald-800/40 font-medium">
                          <DollarSign className="w-3 h-3" />
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
                  <div className="pt-4 mt-4 border-t border-slate-700/60 flex items-center justify-between">
                    <a
                      href={job.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-slate-400 hover:text-emerald-400 flex items-center space-x-1 transition"
                    >
                      <span>Posting</span>
                      <ExternalLink className="w-3 h-3" />
                    </a>

                    <button
                      onClick={() => handleAddJob(job)}
                      disabled={isAdded || isAddingThis}
                      className={`flex items-center space-x-1.5 px-3.5 py-1.5 rounded-xl text-xs font-bold transition shadow-xs ${
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
        )}
      </main>
    </div>
  </div>
);
};
