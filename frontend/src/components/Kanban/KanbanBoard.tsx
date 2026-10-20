import React, { useState, useMemo } from 'react';
import { 
  Bookmark, 
  Send, 
  Clock, 
  MessageSquare, 
  Award, 
  XCircle, 
  Search, 
  Filter, 
  SlidersHorizontal,
  RefreshCw,
  AlertTriangle
} from 'lucide-react';
import { Job, JobStatus } from '../../types';
import { JobCard } from './JobCard';
import { api } from '../../api/client';

interface KanbanBoardProps {
  jobs: Job[];
  onSelectJob: (job: Job) => void;
  onUpdateJobStatus: (id: number, newStatus: JobStatus) => void;
  onDeleteJob: (id: number) => void;
  onJobsRefreshed?: (jobs: Job[]) => void;
  updatingJobIds?: Set<number>;
}

interface ColumnConfig {
  id: JobStatus;
  title: string;
  icon: React.ReactNode;
  colorClass: string;
  headerBg: string;
}

const COLUMNS: ColumnConfig[] = [
  {
    id: 'WISHLIST',
    title: 'Wishlist',
    icon: <Bookmark className="w-4 h-4 text-purple-400" />,
    colorClass: 'border-purple-500/30 text-purple-300',
    headerBg: 'bg-purple-950/20',
  },
  {
    id: 'TO_APPLY',
    title: 'To Apply',
    icon: <Clock className="w-4 h-4 text-blue-400" />,
    colorClass: 'border-blue-500/30 text-blue-300',
    headerBg: 'bg-blue-950/20',
  },
  {
    id: 'APPLIED',
    title: 'Applied',
    icon: <Send className="w-4 h-4 text-amber-400" />,
    colorClass: 'border-amber-500/30 text-amber-300',
    headerBg: 'bg-amber-950/20',
  },
  {
    id: 'INTERVIEWING',
    title: 'Interviewing',
    icon: <MessageSquare className="w-4 h-4 text-cyan-400" />,
    colorClass: 'border-cyan-500/30 text-cyan-300',
    headerBg: 'bg-cyan-950/20',
  },
  {
    id: 'OFFER',
    title: 'Offers',
    icon: <Award className="w-4 h-4 text-emerald-400" />,
    colorClass: 'border-emerald-500/30 text-emerald-300',
    headerBg: 'bg-emerald-950/20',
  },
  {
    id: 'REJECTED',
    title: 'Archive',
    icon: <XCircle className="w-4 h-4 text-slate-400" />,
    colorClass: 'border-slate-500/30 text-slate-300',
    headerBg: 'bg-slate-950/20',
  },
];

const STATUS_ORDER: JobStatus[] = ['WISHLIST', 'TO_APPLY', 'APPLIED', 'INTERVIEWING', 'OFFER', 'REJECTED'];

export const KanbanBoard: React.FC<KanbanBoardProps> = ({
  jobs,
  onSelectJob,
  onUpdateJobStatus,
  onDeleteJob,
  onJobsRefreshed,
  updatingJobIds,
}) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [workplaceFilter, setWorkplaceFilter] = useState<string>('all');
  const [minFitScore, setMinFitScore] = useState<number>(0);
  const [hideExpired, setHideExpired] = useState(false);
  const [isVerifying, setIsVerifying] = useState(false);
  const [verifyMessage, setVerifyMessage] = useState<string | null>(null);

  const handleVerifyPostings = async () => {
    setIsVerifying(true);
    setVerifyMessage(null);
    try {
      const res = await api.checkAllJobStatuses();
      if (onJobsRefreshed && res.jobs) {
        onJobsRefreshed(res.jobs);
      }
      setVerifyMessage(`Scanned ${res.checked} listings: ${res.expired_found} expired.`);
      setTimeout(() => setVerifyMessage(null), 5000);
    } catch (err) {
      console.error('Failed to verify postings:', err);
      setVerifyMessage('Failed to check postings.');
      setTimeout(() => setVerifyMessage(null), 4000);
    } finally {
      setIsVerifying(false);
    }
  };

  // Filter jobs based on search term, workplace, fit score, and expired status
  const filteredJobs = useMemo(() => {
    return jobs.filter((job) => {
      const matchesSearch =
        job.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
        job.company.toLowerCase().includes(searchTerm.toLowerCase()) ||
        (job.location && job.location.toLowerCase().includes(searchTerm.toLowerCase()));

      const matchesWorkplace =
        workplaceFilter === 'all' ||
        (job.workplace_type && job.workplace_type.toLowerCase() === workplaceFilter.toLowerCase());

      const matchesScore =
        minFitScore === 0 || (job.fit_score && job.fit_score >= minFitScore);

      const matchesExpired = !hideExpired || !job.is_expired;

      return matchesSearch && matchesWorkplace && matchesScore && matchesExpired;
    });
  }, [jobs, searchTerm, workplaceFilter, minFitScore, hideExpired]);

  const handleMoveStatus = (job: Job, direction: 'prev' | 'next') => {
    const idx = STATUS_ORDER.indexOf(job.status);
    if (idx === -1) return;

    if (direction === 'prev' && idx > 0) {
      onUpdateJobStatus(job.id, STATUS_ORDER[idx - 1]);
    } else if (direction === 'next' && idx < STATUS_ORDER.length - 1) {
      onUpdateJobStatus(job.id, STATUS_ORDER[idx + 1]);
    }
  };

  return (
    <div className="flex flex-col h-[calc(100vh-4rem)] overflow-hidden">
      {/* Top Filter & Search Bar */}
      <div className="bg-slate-900/90 border-b border-slate-800 px-6 py-3 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center space-x-3 flex-1 max-w-md">
          <div className="relative w-full">
            <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-400" />
            <input
              type="text"
              placeholder="Search by role, company, or keyword..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full pl-9 pr-4 py-1.5 bg-slate-800/80 border border-slate-700 rounded-lg text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-emerald-500/50"
            />
          </div>
        </div>

        <div className="flex items-center space-x-3 text-xs flex-wrap gap-y-2">
          {/* Verify Postings Button */}
          <button
            onClick={handleVerifyPostings}
            disabled={isVerifying}
            className="flex items-center space-x-1.5 bg-slate-800/80 hover:bg-slate-700/80 px-3 py-1.5 rounded-lg border border-slate-700 text-slate-300 hover:text-white font-medium transition text-xs shadow-xs disabled:opacity-50"
            title="Scan active pipeline postings to detect expired or closed roles"
          >
            <RefreshCw className={`w-3.5 h-3.5 text-emerald-400 ${isVerifying ? 'animate-spin' : ''}`} />
            <span>{isVerifying ? 'Verifying...' : 'Verify Postings'}</span>
          </button>

          {/* Hide Expired Toggle */}
          <label className="flex items-center space-x-1.5 text-xs text-slate-400 hover:text-slate-200 cursor-pointer select-none bg-slate-800/80 px-2.5 py-1.5 rounded-lg border border-slate-700">
            <input
              type="checkbox"
              checked={hideExpired}
              onChange={(e) => setHideExpired(e.target.checked)}
              className="rounded bg-slate-900 border-slate-700 text-emerald-600 focus:ring-0 focus:ring-offset-0 w-3.5 h-3.5 cursor-pointer"
            />
            <span>Hide Expired</span>
          </label>

          {verifyMessage && (
            <span className="text-xs text-emerald-400 font-medium animate-fadeIn">
              {verifyMessage}
            </span>
          )}

          {/* Workplace Filter */}
          <div className="flex items-center space-x-1.5 bg-slate-800/80 p-1 rounded-lg border border-slate-700">
            <Filter className="w-3.5 h-3.5 text-slate-400 ml-1" />
            {(['all', 'remote', 'hybrid', 'onsite'] as const).map((type) => (
              <button
                key={type}
                onClick={() => setWorkplaceFilter(type)}
                className={`px-2 py-1 rounded capitalize font-medium transition ${
                  workplaceFilter === type
                    ? 'bg-emerald-600 text-white shadow-xs'
                    : 'text-slate-400 hover:text-white'
                }`}
              >
                {type}
              </button>
            ))}
          </div>

          {/* Min Fit Score */}
          <div className="flex items-center space-x-2 bg-slate-800/80 px-3 py-1.5 rounded-lg border border-slate-700">
            <SlidersHorizontal className="w-3.5 h-3.5 text-emerald-400" />
            <span className="text-slate-300 font-medium">Min Match:</span>
            <select
              value={minFitScore}
              onChange={(e) => setMinFitScore(Number(e.target.value))}
              className="bg-slate-900 border border-slate-700 rounded px-2 py-0.5 text-slate-200 text-xs focus:outline-none"
            >
              <option value={0}>Any Match</option>
              <option value={50}>50% +</option>
              <option value={70}>70% +</option>
              <option value={85}>85% +</option>
            </select>
          </div>
        </div>
      </div>

      {/* Kanban Columns */}
      <div className="flex-1 overflow-x-auto p-6 bg-slate-950/40">
        <div className="flex gap-4 h-full min-w-[1280px]">
          {COLUMNS.map((col) => {
            const columnJobs = filteredJobs
              .filter((j) => j.status === col.id)
              .sort((a, b) => {
                const timeA = a.updated_at ? new Date(a.updated_at).getTime() : 0;
                const timeB = b.updated_at ? new Date(b.updated_at).getTime() : 0;
                if (timeB !== timeA) return timeB - timeA;
                return b.id - a.id;
              });

            const columnExpiredCount = columnJobs.filter((j) => j.is_expired).length;

            return (
              <div
                key={col.id}
                className="flex-1 flex flex-col bg-slate-900/60 rounded-2xl border border-slate-800/80 overflow-hidden shadow-sm"
              >
                {/* Column Header */}
                <div className={`px-4 py-3 border-b border-slate-800 flex items-center justify-between ${col.headerBg}`}>
                  <div className="flex items-center space-x-2 font-semibold text-sm">
                    {col.icon}
                    <span className="text-slate-200">{col.title}</span>
                  </div>
                  <div className="flex items-center space-x-1.5">
                    {columnExpiredCount > 0 && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded-full font-bold bg-rose-500/20 text-rose-300 border border-rose-500/40" title={`${columnExpiredCount} expired postings in this column`}>
                        {columnExpiredCount} Expired
                      </span>
                    )}
                    <span className={`text-xs px-2 py-0.5 rounded-full font-bold border ${col.colorClass}`}>
                      {columnJobs.length}
                    </span>
                  </div>
                </div>

                {/* Cards Container */}
                <div className="flex-1 overflow-y-auto p-3 space-y-3">
                  {columnJobs.length === 0 ? (
                    <div className="h-32 border-2 border-dashed border-slate-800/60 rounded-xl flex items-center justify-center text-xs text-slate-500">
                      No jobs in this stage
                    </div>
                  ) : (
                    columnJobs.map((job) => (
                      <JobCard
                        key={job.id}
                        job={job}
                        onSelect={onSelectJob}
                        onMoveStatus={handleMoveStatus}
                        onDelete={onDeleteJob}
                        onArchive={(j) => onUpdateJobStatus(j.id, 'REJECTED')}
                        isUpdating={updatingJobIds?.has(job.id)}
                      />
                    ))
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};
