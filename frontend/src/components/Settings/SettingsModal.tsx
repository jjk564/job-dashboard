import React, { useState, useEffect, useMemo } from 'react';
import { 
  X, 
  Settings, 
  Sparkles, 
  EyeOff, 
  Eye, 
  RotateCcw, 
  Clock, 
  Ban, 
  Search, 
  Building2, 
  ExternalLink 
} from 'lucide-react';
import { api } from '../../api/client';
import { DiscoveredJob } from '../../types';

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  initialTab?: 'ai' | 'hidden';
}

/** Closed renders nothing; the check sits outside the body because hooks may not follow a return. */
export const SettingsModal: React.FC<SettingsModalProps> = (props) =>
  props.isOpen ? <SettingsBody {...props} /> : null;

const SettingsBody: React.FC<SettingsModalProps> = ({
  isOpen,
  onClose,
  initialTab = 'ai',
}) => {

  const [activeTab, setActiveTab] = useState<'ai' | 'hidden'>(initialTab);


  // Tab 2: Hidden Listings & Blacklists
  const [hiddenJobsMap, setHiddenJobsMap] = useState<Record<string, DiscoveredJob & { hiddenAt?: string }>>({});
  const [hiddenSearch, setHiddenSearch] = useState('');
  const [blockedCompanies, setBlockedCompanies] = useState<string[]>([]);
  const [newBlockedCompany, setNewBlockedCompany] = useState('');
  const [cleanupNotification, setCleanupNotification] = useState<string | null>(null);

  // Load saved settings & hidden data on open / mount
  useEffect(() => {
    setActiveTab(initialTab);

    // Hidden jobs & blocked companies
    loadHiddenData();
  }, [isOpen, initialTab]);

  const loadHiddenData = () => {
    try {
      const rawHidden = localStorage.getItem('job_pulse_hidden_jobs');
      setHiddenJobsMap(rawHidden ? JSON.parse(rawHidden) : {});
    } catch (err) {
      console.error('Failed to parse hidden listings from storage:', err);
    }
    // Hidden companies are hadoku's, per person: the feed drops them on the server.
    api
      .getBlockedCompanies()
      .then(setBlockedCompanies)
      .catch((err) => console.error('Failed to load hidden companies:', err));
  };

  const notifyStorageUpdate = () => {
    window.dispatchEvent(new Event('job_pulse_storage_updated'));
  };

  // Hidden Listings Actions
  const hiddenJobsList = useMemo(() => Object.values(hiddenJobsMap), [hiddenJobsMap]);

  const filteredHiddenJobs = useMemo(() => {
    if (!hiddenSearch.trim()) return hiddenJobsList;
    const term = hiddenSearch.toLowerCase().trim();
    return hiddenJobsList.filter((job) =>
      job.title.toLowerCase().includes(term) ||
      job.company.toLowerCase().includes(term) ||
      (job.location || '').toLowerCase().includes(term) ||
      job.source.toLowerCase().includes(term)
    );
  }, [hiddenJobsList, hiddenSearch]);

  const handleUnhideJob = (url: string) => {
    const updated = { ...hiddenJobsMap };
    delete updated[url];
    setHiddenJobsMap(updated);
    localStorage.setItem('job_pulse_hidden_jobs', JSON.stringify(updated));
    notifyStorageUpdate();
  };

  const handleUnhideAll = () => {
    setHiddenJobsMap({});
    localStorage.setItem('job_pulse_hidden_jobs', JSON.stringify({}));
    notifyStorageUpdate();
  };

  const handleCleanOlderThan30Days = () => {
    const now = Date.now();
    const cutoffMs = 30 * 24 * 60 * 60 * 1000;
    const updated: Record<string, DiscoveredJob & { hiddenAt?: string }> = {};
    let purgedCount = 0;

    for (const [url, job] of Object.entries(hiddenJobsMap)) {
      const hiddenTime = job.hiddenAt ? new Date(job.hiddenAt).getTime() : now;
      if (now - hiddenTime > cutoffMs) {
        purgedCount += 1;
      } else {
        updated[url] = job;
      }
    }

    setHiddenJobsMap(updated);
    localStorage.setItem('job_pulse_hidden_jobs', JSON.stringify(updated));
    notifyStorageUpdate();
    setCleanupNotification(
      purgedCount > 0
        ? `Cleaned up ${purgedCount} listing(s) hidden over 30 days ago.`
        : 'No listings older than 30 days were found.'
    );
    setTimeout(() => setCleanupNotification(null), 4000);
  };

  // Blocked Companies Actions
  const handleAddBlockedCompany = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = newBlockedCompany.trim();
    if (!trimmed) return;
    try {
      await api.blockCompany(trimmed);
      setBlockedCompanies(await api.getBlockedCompanies());
      notifyStorageUpdate();
      setNewBlockedCompany('');
    } catch (err) {
      console.error('Failed to hide company:', err);
    }
  };

  const handleRemoveBlockedCompany = async (company: string) => {
    try {
      await api.unblockCompany(company);
      setBlockedCompanies(await api.getBlockedCompanies());
      notifyStorageUpdate();
    } catch (err) {
      console.error('Failed to unhide company:', err);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-fadeIn">
      <div className="bg-slate-900 border border-slate-800 rounded-3xl w-full max-w-2xl max-h-[88vh] flex flex-col shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="p-6 pb-4 border-b border-slate-800 flex items-center justify-between shrink-0">
          <div className="flex items-center space-x-2.5">
            <div className="w-9 h-9 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400">
              <Settings className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-bold text-slate-100 text-base">Dashboard Settings</h3>
              <p className="text-xs text-slate-400">Documents, hidden listings and hidden companies</p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-1.5 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Tab Navigation */}
        <div className="flex border-b border-slate-800 px-6 bg-slate-950/40 shrink-0">
          <button
            type="button"
            onClick={() => setActiveTab('ai')}
            className={`flex items-center space-x-2 py-3 px-4 border-b-2 font-medium text-xs transition ${
              activeTab === 'ai'
                ? 'border-emerald-500 text-emerald-400 font-bold bg-slate-900/60'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <Sparkles className="w-4 h-4" />
            <span>Documents</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('hidden')}
            className={`flex items-center space-x-2 py-3 px-4 border-b-2 font-medium text-xs transition ${
              activeTab === 'hidden'
                ? 'border-emerald-500 text-emerald-400 font-bold bg-slate-900/60'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <EyeOff className="w-4 h-4" />
            <span>Hidden Listings & Blacklists</span>
            {(hiddenJobsList.length > 0 || blockedCompanies.length > 0) && (
              <span className="ml-1.5 px-2 py-0.2 rounded-full text-[10px] font-bold bg-slate-800 text-slate-300 border border-slate-700">
                {hiddenJobsList.length + blockedCompanies.length}
              </span>
            )}
          </button>
        </div>

        {/* Content Body */}
        {activeTab === 'ai' ? (
          <div className="flex-1 overflow-y-auto p-6 space-y-3 text-sm text-slate-300">
            <p className="font-bold text-slate-100">Documents come from hadoku</p>
            <p className="text-xs text-slate-400">
              Tailored résumés, cover letters, screening answers and packets are written by hadoku's résumé service,
              signed in as you on hadoku.me. There is no provider or API key to set here, and Discover searches hadoku's
              corpus, so no job-board keys either.
            </p>
          </div>
        ) : (
          <div className="flex-1 overflow-y-auto p-6 space-y-6">
            {/* Section 1: Hidden Job Listings */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-2">
                  <EyeOff className="w-4 h-4 text-amber-400" />
                  <h4 className="text-xs font-bold uppercase tracking-wider text-slate-200">
                    Hidden Job Listings ({hiddenJobsList.length})
                  </h4>
                </div>
                <div className="flex items-center space-x-2">
                  {hiddenJobsList.length > 0 && (
                    <>
                      <button
                        type="button"
                        onClick={handleCleanOlderThan30Days}
                        className="text-[11px] text-slate-300 hover:text-amber-300 px-2.5 py-1 rounded-lg border border-slate-700 bg-slate-800 hover:bg-slate-700 transition flex items-center space-x-1"
                        title="Remove hidden jobs older than 30 days"
                      >
                        <Clock className="w-3 h-3" />
                        <span>Clean (&gt;30d)</span>
                      </button>
                      <button
                        type="button"
                        onClick={handleUnhideAll}
                        className="text-[11px] text-rose-400 hover:text-rose-300 px-2.5 py-1 rounded-lg border border-rose-900/40 bg-rose-950/20 hover:bg-rose-950/40 transition flex items-center space-x-1"
                      >
                        <RotateCcw className="w-3 h-3" />
                        <span>Unhide All</span>
                      </button>
                    </>
                  )}
                </div>
              </div>
              <p className="text-xs text-slate-400">
                Listings you've hidden from the Discovery feed. You can review, search, or unhide them at any time.
              </p>

              {cleanupNotification && (
                <div className="p-2.5 bg-amber-950/40 border border-amber-800/40 rounded-xl text-xs text-amber-300 flex items-center space-x-2 animate-fadeIn">
                  <Clock className="w-3.5 h-3.5 shrink-0" />
                  <span>{cleanupNotification}</span>
                </div>
              )}

              {hiddenJobsList.length > 0 && (
                <div className="relative">
                  <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-2.5" />
                  <input
                    type="text"
                    placeholder="Filter hidden jobs by title, company, or source..."
                    value={hiddenSearch}
                    onChange={(e) => setHiddenSearch(e.target.value)}
                    className="w-full pl-9 pr-3 py-1.5 bg-slate-800/80 border border-slate-700 rounded-xl text-xs text-slate-200 focus:outline-none focus:ring-1 focus:ring-emerald-500 placeholder-slate-500"
                  />
                </div>
              )}

              {/* Scrollable Hidden Jobs List */}
              <div className="max-h-56 overflow-y-auto space-y-2 pr-1 rounded-xl">
                {filteredHiddenJobs.length === 0 ? (
                  <div className="py-8 text-center bg-slate-950/40 border border-slate-800/80 rounded-2xl text-xs text-slate-400 space-y-1">
                    <EyeOff className="w-6 h-6 text-slate-600 mx-auto" />
                    <p className="text-slate-300 font-medium">
                      {hiddenJobsList.length === 0 ? 'No hidden listings' : 'No hidden jobs match your search'}
                    </p>
                    <p className="text-slate-500 max-w-xs mx-auto text-[11px]">
                      {hiddenJobsList.length === 0
                        ? 'When you click "Hide" on any job card in the Discovery feed, it is preserved here.'
                        : 'Try clearing your search term.'}
                    </p>
                  </div>
                ) : (
                  filteredHiddenJobs.map((job) => (
                    <div
                      key={job.url}
                      className="p-3 bg-slate-800/60 hover:bg-slate-800/90 border border-slate-700/60 rounded-xl flex items-center justify-between gap-3 transition"
                    >
                      <div className="min-w-0 flex-1 space-y-0.5">
                        <div className="flex items-center space-x-2">
                          <span className="font-semibold text-slate-200 text-xs truncate max-w-[260px] sm:max-w-[340px]">
                            {job.title}
                          </span>
                          <span className="text-[9px] px-1.5 py-0.2 rounded-full border uppercase font-mono bg-slate-900/80 text-slate-400 border-slate-700 shrink-0">
                            {job.source}
                          </span>
                        </div>
                        <div className="flex items-center space-x-2 text-[11px] text-slate-400">
                          <span className="truncate max-w-[140px] text-slate-300 font-medium">{job.company}</span>
                          <span>•</span>
                          <span className="truncate max-w-[120px]">{job.location || 'Remote'}</span>
                          {job.hiddenAt && (
                            <>
                              <span>•</span>
                              <span className="text-slate-500 text-[10px]">
                                Hidden {new Date(job.hiddenAt).toLocaleDateString()}
                              </span>
                            </>
                          )}
                        </div>
                      </div>

                      <div className="flex items-center space-x-1.5 shrink-0">
                        <a
                          href={job.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="p-1.5 text-slate-400 hover:text-emerald-400 rounded-lg hover:bg-slate-700/60 transition"
                          title="View original job posting"
                        >
                          <ExternalLink className="w-3.5 h-3.5" />
                        </a>
                        <button
                          type="button"
                          onClick={() => handleUnhideJob(job.url)}
                          className="px-2.5 py-1 rounded-lg text-xs font-bold bg-emerald-500/20 text-emerald-300 hover:bg-emerald-500/30 border border-emerald-500/40 transition flex items-center space-x-1"
                          title="Restore listing to active feed"
                        >
                          <Eye className="w-3 h-3" />
                          <span>Unhide</span>
                        </button>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>

            {/* Section 2: Company & Recruiter Blacklist */}
            <div className="space-y-3 pt-4 border-t border-slate-800">
              <div className="flex items-center space-x-2">
                <Ban className="w-4 h-4 text-rose-400" />
                <h4 className="text-xs font-bold uppercase tracking-wider text-slate-200">
                  Company & Recruiter Blacklist ({blockedCompanies.length})
                </h4>
              </div>
              <p className="text-xs text-slate-400">
                Permanently block all job listings from specific employers, agencies, or recruiters across all live discovery boards.
              </p>

              <form onSubmit={handleAddBlockedCompany} className="flex gap-2">
                <div className="relative flex-1">
                  <Building2 className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-2.5" />
                  <input
                    type="text"
                    placeholder="e.g. Revature, CyberCoders, Dice..."
                    value={newBlockedCompany}
                    onChange={(e) => setNewBlockedCompany(e.target.value)}
                    className="w-full pl-9 pr-3 py-1.5 bg-slate-800/80 border border-slate-700 rounded-xl text-xs text-slate-200 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                  />
                </div>
                <button
                  type="submit"
                  disabled={!newBlockedCompany.trim()}
                  className="px-3.5 py-1.5 bg-rose-600/80 hover:bg-rose-600 disabled:opacity-40 text-white text-xs font-bold rounded-xl transition flex items-center space-x-1 shadow-sm shrink-0"
                >
                  <Ban className="w-3 h-3" />
                  <span>Block Company</span>
                </button>
              </form>

              {/* Blocked Company Badges */}
              <div className="flex flex-wrap gap-1.5 pt-1">
                {blockedCompanies.length === 0 ? (
                  <span className="text-slate-500 text-xs italic">
                    No companies blacklisted yet.
                  </span>
                ) : (
                  blockedCompanies.map((comp) => (
                    <span
                      key={comp}
                      className="inline-flex items-center space-x-1.5 px-2.5 py-1 rounded-xl text-xs bg-slate-800 border border-rose-900/40 text-rose-300 shadow-xs"
                    >
                      <Building2 className="w-3 h-3 text-rose-400 shrink-0" />
                      <span className="font-semibold">{comp}</span>
                      <button
                        type="button"
                        onClick={() => handleRemoveBlockedCompany(comp)}
                        className="text-slate-400 hover:text-white p-0.5 rounded-full hover:bg-slate-700 transition"
                        title={`Unblock ${comp}`}
                      >
                        <X className="w-3 h-3" />
                      </button>
                    </span>
                  ))
                )}
              </div>
            </div>

            {/* Footer */}
            <div className="pt-3 border-t border-slate-800 flex justify-end">
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-white rounded-xl text-xs font-bold transition"
              >
                Done
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default SettingsModal;
