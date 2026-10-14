import React, { useState, useEffect, useMemo } from 'react';
import { 
  X, 
  Settings, 
  Sparkles, 
  Check, 
  Key, 
  Shield, 
  EyeOff, 
  Eye, 
  RotateCcw, 
  Clock, 
  Ban, 
  Search, 
  Building2, 
  ExternalLink 
} from 'lucide-react';
import { DiscoveredJob } from '../../types';

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  initialTab?: 'ai' | 'hidden';
}

export const SettingsModal: React.FC<SettingsModalProps> = ({
  isOpen,
  onClose,
  initialTab = 'ai',
}) => {
  if (!isOpen) return null;

  const [activeTab, setActiveTab] = useState<'ai' | 'hidden'>(initialTab);

  // Tab 1: AI & Search API settings
  const [aiProvider, setAiProvider] = useState<string>('template');
  const [apiKey, setApiKey] = useState<string>('');
  const [adzunaAppId, setAdzunaAppId] = useState<string>('');
  const [adzunaAppKey, setAdzunaAppKey] = useState<string>('');
  const [savedBanner, setSavedBanner] = useState(false);

  // Tab 2: Hidden Listings & Blacklists
  const [hiddenJobsMap, setHiddenJobsMap] = useState<Record<string, DiscoveredJob & { hiddenAt?: string }>>({});
  const [hiddenSearch, setHiddenSearch] = useState('');
  const [blockedCompanies, setBlockedCompanies] = useState<string[]>([]);
  const [newBlockedCompany, setNewBlockedCompany] = useState('');
  const [cleanupNotification, setCleanupNotification] = useState<string | null>(null);

  // Load saved settings & hidden data on open / mount
  useEffect(() => {
    setActiveTab(initialTab);

    // AI & API settings
    const savedProvider = localStorage.getItem('job_pulse_ai_provider') || 'template';
    const savedKey = localStorage.getItem('job_pulse_api_key') || '';
    const savedAdzunaId = localStorage.getItem('job_pulse_adzuna_app_id') || '';
    const savedAdzunaKey = localStorage.getItem('job_pulse_adzuna_app_key') || '';
    setAiProvider(savedProvider);
    setApiKey(savedKey);
    setAdzunaAppId(savedAdzunaId);
    setAdzunaAppKey(savedAdzunaKey);

    // Hidden jobs & blocked companies
    loadHiddenData();
  }, [isOpen, initialTab]);

  const loadHiddenData = () => {
    try {
      const rawHidden = localStorage.getItem('job_pulse_hidden_jobs');
      setHiddenJobsMap(rawHidden ? JSON.parse(rawHidden) : {});
      const rawBlocked = localStorage.getItem('job_pulse_blocked_companies');
      setBlockedCompanies(rawBlocked ? JSON.parse(rawBlocked) : []);
    } catch (err) {
      console.error('Failed to parse hidden or blacklist data from storage:', err);
    }
  };

  const notifyStorageUpdate = () => {
    window.dispatchEvent(new Event('job_pulse_storage_updated'));
  };

  // AI & Search Settings Save
  const handleSaveAISettings = (e: React.FormEvent) => {
    e.preventDefault();
    localStorage.setItem('job_pulse_ai_provider', aiProvider);
    localStorage.setItem('job_pulse_api_key', apiKey);
    localStorage.setItem('job_pulse_adzuna_app_id', adzunaAppId);
    localStorage.setItem('job_pulse_adzuna_app_key', adzunaAppKey);
    notifyStorageUpdate();
    setSavedBanner(true);
    setTimeout(() => {
      setSavedBanner(false);
      onClose();
    }, 1000);
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
  const handleAddBlockedCompany = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = newBlockedCompany.trim();
    if (!trimmed) return;

    if (!blockedCompanies.some((b) => b.toLowerCase() === trimmed.toLowerCase())) {
      const updated = [...blockedCompanies, trimmed];
      setBlockedCompanies(updated);
      localStorage.setItem('job_pulse_blocked_companies', JSON.stringify(updated));
      notifyStorageUpdate();
    }
    setNewBlockedCompany('');
  };

  const handleRemoveBlockedCompany = (company: string) => {
    const updated = blockedCompanies.filter((b) => b.toLowerCase() !== company.toLowerCase());
    setBlockedCompanies(updated);
    localStorage.setItem('job_pulse_blocked_companies', JSON.stringify(updated));
    notifyStorageUpdate();
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
              <p className="text-xs text-slate-400">Configure AI tailoring, discovery APIs, and hidden job blacklists</p>
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
            <span>AI & Search APIs</span>
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
          <form onSubmit={handleSaveAISettings} className="flex-1 overflow-y-auto p-6 space-y-5">
            {/* AI Engine Selection */}
            <div className="space-y-2">
              <label className="text-xs font-bold uppercase tracking-wider text-slate-300">
                Document Tailoring & AI Engine
              </label>
              <p className="text-xs text-slate-400">
                Choose how cover letters and targeted resume bullets are generated:
              </p>

              <div className="grid grid-cols-2 gap-2 pt-1">
                {[
                  { id: 'template', label: 'Offline Templates', desc: '100% Local, instant, no key required' },
                  { id: 'ollama', label: 'Local Ollama', desc: 'Runs via localhost:11434 (Llama 3)' },
                  { id: 'gemini', label: 'Google Gemini', desc: 'Gemini 1.5 Flash via API key' },
                  { id: 'openai', label: 'OpenAI GPT-4o', desc: 'OpenAI API key' },
                ].map((p) => (
                  <button
                    type="button"
                    key={p.id}
                    onClick={() => setAiProvider(p.id)}
                    className={`p-3 rounded-xl border text-left transition ${
                      aiProvider === p.id
                        ? 'bg-emerald-950/40 border-emerald-500/60 text-emerald-300'
                        : 'bg-slate-800/80 border-slate-700 text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    <span className="font-bold text-xs block text-slate-200">{p.label}</span>
                    <span className="text-[10px] text-slate-400 block mt-0.5">{p.desc}</span>
                  </button>
                ))}
              </div>
            </div>

            {/* API Key */}
            {(aiProvider === 'gemini' || aiProvider === 'openai') && (
              <div className="space-y-1.5 pt-2 border-t border-slate-800">
                <label className="text-xs font-semibold text-slate-300 flex items-center space-x-1">
                  <Key className="w-3.5 h-3.5 text-emerald-400" />
                  <span>API Key ({aiProvider === 'gemini' ? 'Google Gemini' : 'OpenAI'}):</span>
                </label>
                <input
                  type="password"
                  placeholder="sk-..."
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-xl text-xs text-slate-100 focus:outline-none focus:ring-1 focus:ring-emerald-500 font-mono"
                />
                <p className="text-[11px] text-slate-500">
                  Stored securely in your local browser storage and never transmitted to third parties.
                </p>
              </div>
            )}

            {/* Adzuna API */}
            <div className="space-y-2 pt-2 border-t border-slate-800">
              <div className="flex items-center justify-between">
                <label className="text-xs font-bold uppercase tracking-wider text-slate-300">
                  Adzuna API (Live Search Aggregator)
                </label>
                <a
                  href="https://developer.adzuna.com"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[11px] text-emerald-400 hover:underline"
                >
                  Get Free API Key →
                </a>
              </div>
              <p className="text-[11px] text-slate-400">
                Enables additional live searches across millions of indexed jobs.
              </p>

              <div className="grid grid-cols-2 gap-2 pt-1">
                <div>
                  <label className="text-[11px] text-slate-400 block mb-0.5">App ID:</label>
                  <input
                    type="text"
                    placeholder="e.g. 52c9..."
                    value={adzunaAppId}
                    onChange={(e) => setAdzunaAppId(e.target.value)}
                    className="w-full px-3 py-1.5 bg-slate-800 border border-slate-700 rounded-xl text-xs text-slate-100 focus:outline-none focus:ring-1 focus:ring-emerald-500 font-mono"
                  />
                </div>

                <div>
                  <label className="text-[11px] text-slate-400 block mb-0.5">App Key:</label>
                  <input
                    type="password"
                    placeholder="e.g. 841b..."
                    value={adzunaAppKey}
                    onChange={(e) => setAdzunaAppKey(e.target.value)}
                    className="w-full px-3 py-1.5 bg-slate-800 border border-slate-700 rounded-xl text-xs text-slate-100 focus:outline-none focus:ring-1 focus:ring-emerald-500 font-mono"
                  />
                </div>
              </div>
            </div>

            {/* Local Security Badge */}
            <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800 text-xs text-slate-400 flex items-center space-x-2.5">
              <Shield className="w-5 h-5 text-emerald-400 shrink-0" />
              <span>
                All applications, contacts, and personal information are stored exclusively in your local SQLite database (<code className="text-slate-300">jobs.db</code>).
              </span>
            </div>

            {/* Action Buttons */}
            <div className="pt-2 flex justify-between items-center">
              {savedBanner ? (
                <span className="text-xs text-emerald-400 font-semibold flex items-center space-x-1">
                  <Check className="w-4 h-4" />
                  <span>Settings saved!</span>
                </span>
              ) : <div />}

              <div className="flex space-x-2">
                <button
                  type="button"
                  onClick={onClose}
                  className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold transition shadow-md"
                >
                  Save Settings
                </button>
              </div>
            </div>
          </form>
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
