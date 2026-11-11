import React, { useState } from 'react';
import { 
  X, 
  Building2, 
  MapPin, 
  DollarSign, 
  ExternalLink, 
  Calendar, 
  MessageSquare, 
  Trash2,
  AlertTriangle,
  RefreshCw,
  Archive,
  Send,
  ThumbsUp,
  ThumbsDown,
  EyeOff,
} from 'lucide-react';
import { Job, JobStatus } from '../../types';
import { AICopilot } from './AICopilot';
import { api } from '../../api/client';

interface JobDetailDrawerProps {
  job: Job | null;
  onClose: () => void;
  onJobUpdated: (updated: Job) => void;
  onDeleteJob: (id: string) => void;
}

const STATUS_OPTIONS: { id: JobStatus; label: string }[] = [
  { id: 'TO_APPLY', label: 'To Apply' },
  { id: 'APPLIED', label: 'Applied' },
  { id: 'INTERVIEWING', label: 'Interviewing' },
  { id: 'OFFER', label: 'Offer Received' },
  { id: 'REJECTED', label: 'Rejected / Archived' },
];

/**
 * The drawer renders nothing without a job. That check lives here, outside
 * DrawerBody, because a component may not return before its hooks: closing the
 * drawer used to change the hook count between renders. Keyed by the job, so
 * per-posting state (notes, the action buttons) starts fresh for each one.
 */
export const JobDetailDrawer: React.FC<JobDetailDrawerProps> = ({ job, ...rest }) =>
  job ? <DrawerBody key={job.id} job={job} {...rest} /> : null;

const DrawerBody: React.FC<JobDetailDrawerProps & { job: Job }> = ({
  job,
  onClose,
  onJobUpdated,
  onDeleteJob,
}) => {

  const [notes, setNotes] = useState(job.notes || '');
  const [savingNotes, setSavingNotes] = useState(false);
  const [newActivityTitle, setNewActivityTitle] = useState('');
  const [newActivityDetails, setNewActivityDetails] = useState('');
  const [addingActivity, setAddingActivity] = useState(false);
  const [checkingExpiration, setCheckingExpiration] = useState(false);

  // Check Expiration
  const handleCheckExpiration = async () => {
    setCheckingExpiration(true);
    try {
      const updated = await api.checkJobStatus(job.id);
      onJobUpdated(updated);
    } catch (err) {
      console.error('Failed to verify expiration:', err);
    } finally {
      setCheckingExpiration(false);
    }
  };

  // hadoku: queue for the form runner, vote, hide the employer
  const [queueing, setQueueing] = useState(false);
  const [queued, setQueued] = useState(false);
  const [vote, setVote] = useState<1 | -1 | null>(null);
  const [hidCompany, setHidCompany] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const handleQueueApply = async () => {
    setQueueing(true);
    setActionError(null);
    try {
      await api.queueApplication(job.id);
      setQueued(true);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Could not queue it');
    } finally {
      setQueueing(false);
    }
  };

  const handleVote = async (v: 1 | -1) => {
    const next = vote === v ? null : v;
    setActionError(null);
    try {
      await api.voteJob(job.id, next);
      setVote(next);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Could not save the vote');
    }
  };

  const handleHideCompany = async () => {
    setActionError(null);
    try {
      await api.blockCompany(job.company);
      setHidCompany(true);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Could not hide it');
    }
  };

  // Status Change
  const handleStatusChange = async (newStatus: JobStatus) => {
    try {
      const updated = await api.updateJob(job.id, { status: newStatus });
      onJobUpdated(updated);
    } catch (err) {
      console.error('Failed to change status:', err);
    }
  };

  // Save Notes
  const handleSaveNotes = async () => {
    setSavingNotes(true);
    try {
      const updated = await api.updateJob(job.id, { notes });
      onJobUpdated(updated);
    } catch (err) {
      console.error('Failed to save notes:', err);
    } finally {
      setSavingNotes(false);
    }
  };

  // Add Activity / Interview Note
  const handleAddActivity = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newActivityTitle.trim()) return;

    setAddingActivity(true);
    try {
      await api.addActivity(job.id, {
        activity_type: 'interview',
        title: newActivityTitle.trim(),
        details: newActivityDetails.trim() || undefined,
      });
      setNewActivityTitle('');
      setNewActivityDetails('');
      const updated = await api.getJob(job.id);
      onJobUpdated(updated);
    } catch (err) {
      console.error('Failed to add activity:', err);
    } finally {
      setAddingActivity(false);
    }
  };

  const formatSalary = () => {
    if (job.salary_min && job.salary_max) {
      return `$${Math.round(job.salary_min).toLocaleString()} - $${Math.round(job.salary_max).toLocaleString()}`;
    } else if (job.salary_min) {
      return `$${Math.round(job.salary_min).toLocaleString()}+`;
    }
    return 'Competitive / Unspecified';
  };

  return (
    <div className="fixed inset-0 z-50 overflow-hidden bg-slate-950/80 backdrop-blur-sm flex justify-end animate-fadeIn">
      <div className="w-full max-w-5xl bg-slate-900 border-l border-slate-800 h-full flex flex-col shadow-2xl">
        {/* Top Header */}
        <div className="px-6 py-4 bg-slate-900/90 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 rounded-xl bg-slate-800 border border-slate-700 flex items-center justify-center text-emerald-400">
              <Building2 className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <span className="font-bold text-slate-100 text-lg leading-tight">{job.company}</span>
                {job.url && (
                  <a
                    href={job.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs text-emerald-400 hover:text-emerald-300 flex items-center space-x-1"
                  >
                    <span>Posting</span>
                    <ExternalLink className="w-3 h-3" />
                  </a>
                )}
              </div>
              <h2 className="text-sm font-medium text-slate-400">{job.title}</h2>
            </div>
          </div>

          <div className="flex items-center space-x-3">
            {/* Status Select */}
            <select
              value={job.status}
              onChange={(e) => handleStatusChange(e.target.value as JobStatus)}
              className="bg-slate-800 border border-slate-700 text-slate-200 text-xs font-semibold rounded-lg px-3 py-1.5 focus:outline-none focus:ring-1 focus:ring-emerald-500"
            >
              {STATUS_OPTIONS.map((opt) => (
                <option key={opt.id} value={opt.id}>
                  Stage: {opt.label}
                </option>
              ))}
            </select>

            <button
              onClick={() => {
                onDeleteJob(job.id);
                onClose();
              }}
              className="p-1.5 text-slate-500 hover:text-rose-400 transition"
              title="Delete Job"
            >
              <Trash2 className="w-4 h-4" />
            </button>

            <button
              onClick={onClose}
              className="p-1.5 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Content Split Body */}
        <div className="flex-1 grid grid-cols-1 md:grid-cols-12 overflow-hidden">
          {/* Left Column: Job Details & Description */}
          <div className="md:col-span-7 overflow-y-auto p-6 space-y-6 border-r border-slate-800">
            {/* Expiration Banner if Expired */}
            {job.is_expired ? (
              <div className="bg-rose-950/40 border border-rose-800/60 rounded-xl p-3.5 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs animate-fadeIn">
                <div className="flex items-start space-x-2.5">
                  <AlertTriangle className="w-5 h-5 text-rose-400 shrink-0 mt-0.5" />
                  <div>
                    <div className="font-semibold text-rose-300 text-sm">Posting Detected as Expired</div>
                    <p className="text-rose-200/80 mt-0.5">
                      {job.expired_reason || 'This job is no longer active or accepting applications.'}
                    </p>
                    {job.expired_at && (
                      <span className="text-[10px] text-rose-300/60 block mt-1">
                        Last seen on its board {new Date(job.expired_at).toLocaleDateString()}
                      </span>
                    )}
                  </div>
                </div>
                <div className="flex items-center space-x-2 shrink-0">
                  <button
                    onClick={handleCheckExpiration}
                    disabled={checkingExpiration}
                    className="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 font-medium transition disabled:opacity-50 flex items-center space-x-1"
                    title="Re-check this link"
                  >
                    <RefreshCw className={`w-3 h-3 text-slate-400 ${checkingExpiration ? 'animate-spin' : ''}`} />
                    <span>{checkingExpiration ? 'Checking...' : 'Re-verify'}</span>
                  </button>
                  {job.status !== 'REJECTED' && (
                    <button
                      onClick={() => handleStatusChange('REJECTED')}
                      className="px-2.5 py-1 rounded-lg bg-rose-900/80 hover:bg-rose-800 text-white font-medium transition shadow-xs flex items-center space-x-1"
                    >
                      <Archive className="w-3 h-3" />
                      <span>Archive</span>
                    </button>
                  )}
                </div>
              </div>
            ) : job.url ? (
              <div className="flex items-center justify-between bg-slate-800/40 border border-slate-800 rounded-xl px-3 py-2 text-xs">
                <span className="text-slate-400">
                  Job Posting Status: <span className="text-emerald-400 font-medium">Active</span>
                  {job.last_seen_at && (
                    <span className="text-slate-500"> · last seen on its board {new Date(job.last_seen_at).toLocaleDateString()}</span>
                  )}
                </span>
                <div className="flex items-center space-x-2">
                  <button
                    onClick={handleCheckExpiration}
                    disabled={checkingExpiration}
                    className="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 font-medium transition flex items-center space-x-1 disabled:opacity-50"
                  >
                    <RefreshCw className={`w-3 h-3 text-emerald-400 ${checkingExpiration ? 'animate-spin' : ''}`} />
                    <span>{checkingExpiration ? 'Checking...' : 'Refresh'}</span>
                  </button>
                </div>
              </div>
            ) : null}

            {/* hadoku actions: the form runner, the feed's taste signal, hiding an employer */}
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <button
                onClick={handleQueueApply}
                disabled={queueing || queued || job.is_expired}
                className="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-bold flex items-center space-x-1.5 transition disabled:opacity-50"
                title={
                  job.is_expired
                    ? 'Its board no longer lists this posting'
                    : "hadoku's runner fills the form from your packet; you approve it on the Applications tab before it is sent"
                }
              >
                <Send className="w-3.5 h-3.5" />
                <span>{queued ? 'Queued' : queueing ? 'Queueing…' : 'Queue for Auto-Apply'}</span>
              </button>
              <button
                onClick={() => handleVote(1)}
                className={`p-1.5 rounded-lg border transition ${vote === 1 ? 'bg-emerald-600/20 border-emerald-500/60 text-emerald-300' : 'bg-slate-800 border-slate-700 text-slate-400 hover:text-white'}`}
                title="More like this"
              >
                <ThumbsUp className="w-3.5 h-3.5" />
              </button>
              <button
                onClick={() => handleVote(-1)}
                className={`p-1.5 rounded-lg border transition ${vote === -1 ? 'bg-rose-900/40 border-rose-700/60 text-rose-300' : 'bg-slate-800 border-slate-700 text-slate-400 hover:text-white'}`}
                title="Less like this"
              >
                <ThumbsDown className="w-3.5 h-3.5" />
              </button>
              <button
                onClick={handleHideCompany}
                disabled={hidCompany}
                className="px-2.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 font-medium transition disabled:opacity-50 flex items-center space-x-1"
                title="Hide every posting from this employer in Discover"
              >
                <EyeOff className="w-3.5 h-3.5" />
                <span>{hidCompany ? `${job.company} hidden` : `Hide ${job.company}`}</span>
              </button>
              {actionError && <span className="text-rose-300">{actionError}</span>}
            </div>

            {/* Meta badges */}
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <span className="inline-flex items-center space-x-1 text-slate-300 bg-slate-800 px-3 py-1 rounded-lg border border-slate-700">
                <MapPin className="w-3.5 h-3.5 text-slate-400" />
                <span>{job.location || 'Remote'}</span>
              </span>

              <span className="inline-flex items-center space-x-1 text-emerald-400 bg-emerald-950/40 px-3 py-1 rounded-lg border border-emerald-800/40 font-semibold">
                <DollarSign className="w-3.5 h-3.5" />
                <span>{formatSalary()}</span>
              </span>

              <span className="text-slate-400 bg-slate-800 px-2.5 py-1 rounded-lg uppercase tracking-wider text-[11px] font-mono border border-slate-700">
                {job.workplace_type || 'remote'}
              </span>

              {job.source && (
                <span className="text-slate-500 bg-slate-900 px-2.5 py-1 rounded-lg text-[11px] border border-slate-800">
                  via {job.source}
                </span>
              )}
            </div>

            {/* Description Block */}
            <div className="space-y-2">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400">
                Job Description & Requirements
              </h3>
              <div className="bg-slate-950/60 rounded-xl p-4 border border-slate-800/80 text-xs text-slate-300 leading-relaxed max-h-80 overflow-y-auto whitespace-pre-wrap">
                {job.description || 'No description provided.'}
              </div>
            </div>

            {/* Application Notes */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400">
                  Notes & Strategy
                </h3>
                <button
                  onClick={handleSaveNotes}
                  disabled={savingNotes}
                  className="text-xs text-emerald-400 hover:text-emerald-300 font-medium"
                >
                  {savingNotes ? 'Saving...' : 'Save Notes'}
                </button>
              </div>
              <textarea
                rows={3}
                placeholder="Log internal referrals, salary discussions, recruiter contacts, or follow-up dates..."
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                className="w-full bg-slate-950/60 border border-slate-800 rounded-xl p-3 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              />
            </div>

            {/* Interview & Activity Timeline */}
            <div className="space-y-3">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center space-x-1.5">
                <Calendar className="w-3.5 h-3.5" />
                <span>Activity & Interview Timeline</span>
              </h3>

              {/* Add Activity Form */}
              <form onSubmit={handleAddActivity} className="space-y-2 bg-slate-800/50 p-3 rounded-xl border border-slate-800">
                <input
                  type="text"
                  placeholder="e.g. Technical Round 1 scheduled with Lead Architect"
                  value={newActivityTitle}
                  onChange={(e) => setNewActivityTitle(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-slate-200 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                />
                <div className="flex space-x-2">
                  <input
                    type="text"
                    placeholder="Details or questions asked (optional)..."
                    value={newActivityDetails}
                    onChange={(e) => setNewActivityDetails(e.target.value)}
                    className="flex-1 bg-slate-900 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-slate-200 focus:outline-none"
                  />
                  <button
                    type="submit"
                    disabled={addingActivity || !newActivityTitle.trim()}
                    className="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold disabled:opacity-50"
                  >
                    Add Log
                  </button>
                </div>
              </form>

              {/* Timeline List */}
              <div className="space-y-2">
                {(job.activities && job.activities.length > 0) ? (
                  job.activities.map((act) => (
                    <div
                      key={act.id}
                      className="p-3 bg-slate-950/40 rounded-xl border border-slate-800/70 text-xs flex items-start space-x-2.5"
                    >
                      <MessageSquare className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                      <div>
                        <span className="font-semibold text-slate-200 block">{act.title}</span>
                        {act.details && <p className="text-slate-400 mt-0.5">{act.details}</p>}
                        {act.created_at && (
                          <span className="text-[10px] text-slate-500 mt-1 block">
                            {new Date(act.created_at).toLocaleDateString()}
                          </span>
                        )}
                      </div>
                    </div>
                  ))
                ) : (
                  <p className="text-xs text-slate-500">No activity logged yet.</p>
                )}
              </div>
            </div>
          </div>

          {/* Right Column: AI Copilot */}
          <div className="md:col-span-5 h-full overflow-hidden">
            <AICopilot job={job} onJobUpdated={onJobUpdated} />
          </div>
        </div>
      </div>
    </div>
  );
};
