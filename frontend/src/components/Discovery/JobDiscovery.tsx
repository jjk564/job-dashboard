import React, { useState, useEffect } from 'react';
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
  X
} from 'lucide-react';
import { DiscoveredJob, Job } from '../../types';
import { api } from '../../api/client';

interface JobDiscoveryProps {
  onJobAdded: (job: Job) => void;
}

const QUICK_TAGS = ['Python', 'React', 'Full Stack', 'Backend', 'DevOps', 'TypeScript', 'Remote'];

const SOURCE_FILTERS = [
  { id: 'all', label: 'All Sources' },
  { id: 'indeed', label: 'Indeed' },
  { id: 'arbeitnow', label: 'Arbeitnow' },
  { id: 'jobicy', label: 'Jobicy' },
  { id: 'weworkremotely', label: 'We Work Remotely' },
  { id: 'himalayas', label: 'Himalayas' },
  { id: 'hackernews', label: 'HN "Who is Hiring?"' },
  { id: 'remoteok', label: 'RemoteOK' },
  { id: 'adzuna', label: 'Adzuna API' },
];

export const JobDiscovery: React.FC<JobDiscoveryProps> = ({ onJobAdded }) => {
  const [query, setQuery] = useState('developer');
  const [selectedSource, setSelectedSource] = useState('all');
  const [usOnly, setUsOnly] = useState(true);
  const [loading, setLoading] = useState(false);
  const [jobs, setJobs] = useState<DiscoveredJob[]>([]);
  const [addedUrls, setAddedUrls] = useState<Set<string>>(new Set());
  const [addingUrl, setAddingUrl] = useState<string | null>(null);

  const fetchJobs = async (
    searchQuery: string,
    source: string = selectedSource,
    isUsOnly: boolean = usOnly
  ) => {
    setLoading(true);
    try {
      const adzunaId = localStorage.getItem('job_pulse_adzuna_app_id') || undefined;
      const adzunaKey = localStorage.getItem('job_pulse_adzuna_app_key') || undefined;
      const results = await api.searchDiscoveredJobs(searchQuery, source, adzunaId, adzunaKey, isUsOnly);
      setJobs(results);
    } catch (err) {
      console.error('Failed to search jobs:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchJobs('developer', 'all', true);
  }, []);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (query.trim()) fetchJobs(query.trim(), selectedSource);
  };

  const handleSourceSelect = (sourceId: string) => {
    setSelectedSource(sourceId);
    fetchJobs(query.trim(), sourceId);
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
            Searches directly across <span className="text-slate-200 font-medium">Indeed</span>, <span className="text-slate-200 font-medium">Arbeitnow</span>, <span className="text-slate-200 font-medium">Jobicy</span>, <span className="text-slate-200 font-medium">We Work Remotely</span>, <span className="text-slate-200 font-medium">Himalayas</span>, <span className="text-slate-200 font-medium">Hacker News</span>, and <span className="text-slate-200 font-medium">RemoteOK</span>.
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

          {/* Source Selectors & US Filter */}
          <div className="pt-2">
            <div className="flex items-center justify-between text-xs text-slate-400 mb-2">
              <div className="flex items-center space-x-2">
                <Filter className="w-3.5 h-3.5 text-emerald-400" />
                <span className="font-semibold text-slate-300">Source Platform:</span>
              </div>
              <button
                type="button"
                onClick={() => {
                  const newVal = !usOnly;
                  setUsOnly(newVal);
                  fetchJobs(query.trim(), selectedSource, newVal);
                }}
                className={`flex items-center space-x-1.5 px-3 py-1 rounded-full text-xs font-semibold border transition ${
                  usOnly
                    ? 'bg-emerald-950/60 border-emerald-500/60 text-emerald-300 shadow-xs'
                    : 'bg-slate-800 border-slate-700 text-slate-400 hover:text-white'
                }`}
                title="Toggle US-Only jobs filter"
              >
                <span>🇺🇸</span>
                <span>US Jobs Only</span>
                <span className={`w-2 h-2 rounded-full ${usOnly ? 'bg-emerald-400 animate-pulse' : 'bg-slate-500'}`} />
              </button>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {SOURCE_FILTERS.map((s) => (
                <button
                  key={s.id}
                  onClick={() => handleSourceSelect(s.id)}
                  className={`px-3 py-1 rounded-lg text-xs font-medium border transition ${
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

          {/* Quick Filter Chips */}
          <div className="flex flex-wrap items-center gap-1.5 pt-1">
            <span className="text-xs text-slate-400 mr-1 font-medium">Trending:</span>
            {QUICK_TAGS.map((tag) => {
              const isTagActive = query.trim().toLowerCase() === tag.toLowerCase();
              return (
                <button
                  key={tag}
                  onClick={() => {
                    if (isTagActive) {
                      setQuery('');
                      fetchJobs('', selectedSource);
                    } else {
                      setQuery(tag);
                      fetchJobs(tag, selectedSource);
                    }
                  }}
                  className={`inline-flex items-center space-x-1.5 px-2.5 py-1 rounded-lg text-xs transition border ${
                    isTagActive
                      ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/60 font-semibold shadow-xs ring-1 ring-emerald-500/30'
                      : 'bg-slate-800/70 hover:bg-slate-700 text-slate-300 border-slate-700/60'
                  }`}
                  title={isTagActive ? `Click to clear "${tag}" filter` : `Filter by "${tag}"`}
                >
                  {isTagActive && <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />}
                  <span>{tag}</span>
                  {isTagActive && <X className="w-3 h-3 ml-0.5 opacity-80 hover:opacity-100" />}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* Results Count, Active Filters Bar & Grid */}
      <div className="space-y-4">
        {/* Active Filter Indicators Bar */}
        {(query.trim() || selectedSource !== 'all' || usOnly) && (
          <div className="flex flex-wrap items-center gap-2 p-2.5 bg-slate-800/50 border border-slate-700/50 rounded-xl text-xs">
            <span className="text-slate-400 flex items-center gap-1.5 font-medium">
              <Filter className="w-3.5 h-3.5 text-emerald-400" />
              <span>Active filters:</span>
            </span>
            {query.trim() && (
              <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-emerald-950/70 text-emerald-300 border border-emerald-500/40 font-medium shadow-xs">
                <span>Keyword: <strong>"{query}"</strong></span>
                <button
                  type="button"
                  onClick={() => {
                    setQuery('');
                    fetchJobs('', selectedSource);
                  }}
                  className="hover:text-white transition p-0.5 rounded-full hover:bg-emerald-800/50"
                  title="Remove keyword filter"
                >
                  <X className="w-3 h-3" />
                </button>
              </span>
            )}
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
            {usOnly && (
              <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-slate-800/80 text-emerald-400 border border-emerald-900/40 font-medium">
                <span>🇺🇸 US Jobs Only</span>
              </span>
            )}
            {(query.trim() || selectedSource !== 'all') && (
              <button
                type="button"
                onClick={() => {
                  setQuery('');
                  setSelectedSource('all');
                  fetchJobs('', 'all');
                }}
                className="text-slate-400 hover:text-emerald-400 text-xs ml-auto transition underline"
              >
                Clear all filters
              </button>
            )}
          </div>
        )}

        <div className="flex items-center justify-between text-xs text-slate-400 px-1">
          <span>
            Found <strong className="text-slate-200">{jobs.length}</strong> listings
            {query.trim() && (
              <span> matching <span className="text-emerald-400 font-semibold">"{query}"</span></span>
            )}
          </span>
          {loading && <span className="text-emerald-400 animate-pulse font-medium">Fetching fresh jobs across boards...</span>}
        </div>

        {jobs.length === 0 && !loading ? (
          <div className="text-center py-16 bg-slate-900/40 rounded-2xl border border-slate-800">
            <Compass className="w-10 h-10 text-slate-600 mx-auto mb-3" />
            <p className="text-slate-300 font-medium text-sm">No jobs found matching "{query}"</p>
            <p className="text-slate-500 text-xs mt-1">
              Try another keyword like "Python", "Full Stack", or switch the Source filter to "All Sources".
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {jobs.map((job, idx) => {
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
      </div>
    </div>
  );
};
