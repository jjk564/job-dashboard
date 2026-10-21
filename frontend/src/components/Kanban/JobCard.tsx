import React from 'react';
import { 
  Building2, 
  MapPin, 
  DollarSign, 
  ExternalLink, 
  ChevronRight, 
  ChevronLeft, 
  Sparkles,
  Trash2,
  Calendar,
  AlertTriangle,
  Archive
} from 'lucide-react';
import { Job, JobStatus } from '../../types';

interface JobCardProps {
  job: Job;
  onSelect: (job: Job) => void;
  onMoveStatus: (job: Job, direction: 'prev' | 'next') => void;
  onDelete: (id: number) => void;
  onArchive?: (job: Job) => void;
  isUpdating?: boolean;
  onDragStart?: (e: React.DragEvent, job: Job) => void;
  onDragEnd?: (e: React.DragEvent) => void;
  isDragging?: boolean;
}

const STATUS_ORDER: JobStatus[] = ['TO_APPLY', 'APPLIED', 'INTERVIEWING', 'OFFER', 'REJECTED'];

export const JobCard: React.FC<JobCardProps> = ({
  job,
  onSelect,
  onMoveStatus,
  onDelete,
  onArchive,
  isUpdating = false,
  onDragStart,
  onDragEnd,
  isDragging = false,
}) => {
  const currentIndex = job.status === 'WISHLIST' ? 0 : STATUS_ORDER.indexOf(job.status);
  const canMovePrev = currentIndex > 0;
  const canMoveNext = currentIndex >= 0 && currentIndex < STATUS_ORDER.length - 1;

  // Format salary
  const formatSalary = () => {
    if (job.salary_min && job.salary_max) {
      return `$${Math.round(job.salary_min / 1000)}k - $${Math.round(job.salary_max / 1000)}k`;
    } else if (job.salary_min) {
      return `$${Math.round(job.salary_min / 1000)}k+`;
    }
    return null;
  };

  // Color for match score
  const getScoreColor = (score?: number) => {
    if (!score) return 'bg-slate-700/60 text-slate-300 border-slate-600';
    if (score >= 80) return 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30';
    if (score >= 50) return 'bg-amber-500/10 text-amber-400 border-amber-500/30';
    return 'bg-rose-500/10 text-rose-400 border-rose-500/30';
  };

  const salaryStr = formatSalary();

  return (
    <div 
      draggable={!isUpdating}
      onDragStart={(e) => {
        if (isUpdating) {
          e.preventDefault();
          return;
        }
        onDragStart?.(e, job);
      }}
      onDragEnd={onDragEnd}
      className={`group relative rounded-xl p-4 transition-all duration-200 shadow-md hover:shadow-xl select-none cursor-grab active:cursor-grabbing ${
        isDragging
          ? 'opacity-35 scale-[0.98] border-2 border-dashed border-emerald-400 ring-2 ring-emerald-500/40 bg-slate-800/50'
          : job.is_expired
            ? 'bg-slate-900/90 hover:bg-slate-900 border border-rose-500/40 hover:border-rose-500/70 opacity-90 hover:opacity-100 ring-1 ring-rose-500/20'
            : 'bg-slate-800/90 hover:bg-slate-800 border border-slate-700/70 hover:border-emerald-500/50'
      }`}
      onClick={() => onSelect(job)}
    >
      {/* Header: Company & Badges */}
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="flex items-center space-x-1.5 text-slate-400 text-xs font-medium min-w-0">
          <Building2 className="w-3.5 h-3.5 text-slate-400 shrink-0" />
          <span className="truncate max-w-[140px] text-slate-300 font-semibold">{job.company}</span>
        </div>

        <div className="flex items-center space-x-1.5 shrink-0">
          {job.is_expired && (
            <span
              className="inline-flex items-center space-x-1 text-[11px] px-2 py-0.5 rounded-full font-bold bg-rose-500/20 text-rose-300 border border-rose-500/50 shadow-xs"
              title={job.expired_reason || 'Job posting has expired or closed'}
            >
              <AlertTriangle className="w-3 h-3 text-rose-400" />
              <span>Expired</span>
            </span>
          )}

          {/* ATS Fit Match Pill */}
          {job.fit_score !== undefined && job.fit_score !== null ? (
            <span className={`inline-flex items-center space-x-1 text-xs px-2 py-0.5 rounded-full font-semibold border ${getScoreColor(job.fit_score)}`}>
              <Sparkles className="w-3 h-3" />
              <span>{job.fit_score}% Fit</span>
            </span>
          ) : (
            <span className="text-xs px-2 py-0.5 rounded-full bg-slate-700/50 text-slate-400">
              Unranked
            </span>
          )}
        </div>
      </div>

      {/* Job Title */}
      <h3 className="font-semibold text-slate-100 text-sm leading-snug group-hover:text-emerald-400 transition-colors line-clamp-2 mb-2">
        {job.title}
      </h3>

      {/* Expired Reason Banner */}
      {job.is_expired && job.expired_reason && (
        <div className="mb-2.5 px-2 py-1 rounded-md bg-rose-950/40 border border-rose-900/50 text-[11px] text-rose-300/90 flex items-center space-x-1.5">
          <AlertTriangle className="w-3 h-3 text-rose-400 shrink-0" />
          <span className="truncate" title={job.expired_reason}>{job.expired_reason}</span>
        </div>
      )}

      {/* Meta Pills: Location, Salary, Source */}
      <div className="flex flex-wrap items-center gap-1.5 mb-3 text-xs">
        {job.location && (
          <span className="inline-flex items-center space-x-1 text-slate-400 bg-slate-900/60 px-2 py-0.5 rounded border border-slate-700/50">
            <MapPin className="w-3 h-3 text-slate-400" />
            <span className="truncate max-w-[100px]">{job.location}</span>
          </span>
        )}

        {salaryStr && (
          <span className="inline-flex items-center space-x-1 text-emerald-400 bg-emerald-950/40 px-2 py-0.5 rounded border border-emerald-800/40 font-medium">
            <DollarSign className="w-3 h-3" />
            <span>{salaryStr}</span>
          </span>
        )}

        {job.workplace_type && (
          <span className="text-slate-400 bg-slate-900/40 px-1.5 py-0.5 rounded uppercase text-[10px] tracking-wider border border-slate-700/40 font-mono">
            {job.workplace_type}
          </span>
        )}
      </div>

      {/* Card Footer: Quick Stage Movers, Archive and External Link */}
      <div 
        className="flex items-center justify-between pt-2.5 border-t border-slate-700/60 text-xs text-slate-400"
        onMouseDown={(e) => e.stopPropagation()}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center space-x-1.5">
          {canMovePrev && (
            <button
              onClick={() => onMoveStatus(job, 'prev')}
              disabled={isUpdating}
              className="p-1 hover:bg-slate-700 rounded text-slate-400 hover:text-white transition disabled:opacity-40"
              title="Move to previous stage"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
          )}

          {canMoveNext && (
            <button
              onClick={() => onMoveStatus(job, 'next')}
              disabled={isUpdating}
              className="p-1 hover:bg-slate-700 rounded text-emerald-400 hover:text-emerald-300 font-medium flex items-center space-x-0.5 transition disabled:opacity-50"
              title="Advance to next stage"
            >
              {isUpdating ? (
                <span className="text-[11px] text-emerald-400/90 animate-pulse font-normal">Updating...</span>
              ) : (
                <>
                  <span className="text-[11px]">Advance</span>
                  <ChevronRight className="w-4 h-4" />
                </>
              )}
            </button>
          )}

          {job.is_expired && job.status !== 'REJECTED' && onArchive && (
            <button
              onClick={() => onArchive(job)}
              disabled={isUpdating}
              className="px-2 py-0.5 rounded text-[11px] font-medium bg-rose-950/60 hover:bg-rose-900/80 text-rose-300 border border-rose-800/60 flex items-center space-x-1 transition disabled:opacity-40 ml-1"
              title="Move expired job directly to Archive"
            >
              <Archive className="w-3 h-3 text-rose-400" />
              <span>Archive</span>
            </button>
          )}
        </div>

        <div className="flex items-center space-x-1.5">
          {job.url && (
            <a
              href={job.url}
              target="_blank"
              rel="noopener noreferrer"
              className="p-1 text-slate-400 hover:text-emerald-400 transition"
              title="Open Job Posting"
            >
              <ExternalLink className="w-3.5 h-3.5" />
            </a>
          )}

          <button
            onClick={() => onDelete(job.id)}
            className="p-1 text-slate-500 hover:text-rose-400 transition"
            title="Delete Job"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
};
