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
  Compass
} from 'lucide-react';
import { DiscoveredJob, Job } from '../../types';
import { api } from '../../api/client';

interface JobDiscoveryProps {
  onJobAdded: (job: Job) => void;
}

const QUICK_TAGS = ['Python', 'React', 'Full Stack', 'Backend', 'DevOps', 'TypeScript', 'Remote'];

export const JobDiscovery: React.FC<JobDiscoveryProps> = ({ onJobAdded }) => {
  const [query, setQuery] = useState('developer');
  const [loading, setLoading] = useState(false);
  const [jobs, setJobs] = useState<DiscoveredJob[]>([]);
  const [addedUrls, setAddedUrls] = useState<Set<string>>(new Set());
  const [addingUrl, setAddingUrl] = useState<string | null>(null);

  const fetchJobs = async (searchQuery: string) => {
    setLoading(true);
    try {
      const results = await api.searchDiscoveredJobs(searchQuery);
      setJobs(results);
    } catch (err) {
      console.error('Failed to search jobs:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchJobs('developer');
  }, []);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (query.trim()) fetchJobs(query.trim());
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

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
      {/* Header Banner */}
      <div className="bg-gradient-to-r from-emerald-950/40 via-slate-900 to-slate-900 border border-emerald-800/30 rounded-3xl p-6 sm:p-8">
        <div className="max-w-3xl space-y-3">
          <div className="flex items-center space-x-2 text-emerald-400 font-semibold text-xs tracking-wide uppercase">
            <Compass className="w-4 h-4" />
            <span>Live Remote Job Aggregator</span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight">
            Discover Active Tech Opportunities
          </h1>
          <p className="text-slate-400 text-sm">
            Searches directly across public remote and software engineering boards (RemoteOK, Arbeitnow, Jobicy). Add any listing to your Kanban pipeline in one click.
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
                className="w-full pl-10 pr-4 py-2.5 bg-slate-800/90 border border-slate-700 rounded-xl text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-emerald-500/50"
              />
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

          {/* Quick Filter Chips */}
          <div className="flex flex-wrap items-center gap-1.5 pt-1">
            <span className="text-xs text-slate-500 mr-1">Trending:</span>
            {QUICK_TAGS.map((tag) => (
              <button
                key={tag}
                onClick={() => {
                  setQuery(tag);
                  fetchJobs(tag);
                }}
                className="px-2.5 py-1 rounded-lg text-xs bg-slate-800/80 hover:bg-slate-700 text-slate-300 border border-slate-700 transition"
              >
                {tag}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Results Count & Grid */}
      <div className="space-y-4">
        <div className="flex items-center justify-between text-xs text-slate-400 px-1">
          <span>Found {jobs.length} listings</span>
          {loading && <span className="text-emerald-400 animate-pulse">Fetching fresh jobs...</span>}
        </div>

        {jobs.length === 0 && !loading ? (
          <div className="text-center py-16 bg-slate-900/40 rounded-2xl border border-slate-800">
            <Compass className="w-10 h-10 text-slate-600 mx-auto mb-3" />
            <p className="text-slate-300 font-medium text-sm">No jobs found matching "{query}"</p>
            <p className="text-slate-500 text-xs mt-1">Try another keyword like "Python", "Frontend", or "Engineer".</p>
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
                      <span className="text-[10px] px-2 py-0.5 rounded-full bg-slate-900/80 text-slate-400 border border-slate-700/50 uppercase font-mono">
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
