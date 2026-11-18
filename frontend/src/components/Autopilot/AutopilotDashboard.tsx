import React, { useState, useEffect } from 'react';
import {
  Bot,
  Play,
  Sparkles,
  CheckCircle2,
  Clock,
  FileText,
  HelpCircle,
  Send,
  Sliders,
  RefreshCw,
  AlertTriangle,
  ShieldCheck,
  Layers,
  ExternalLink,
  Zap,
  Mail,
  KeyRound,
} from 'lucide-react';
import { AutopilotConfig, AutopilotRunSummary, Job, SearchProfile } from '../../types';
import { api } from '../../api/client';

interface AutopilotDashboardProps {
  jobs: Job[];
  onJobsRefreshed: (jobs: Job[]) => void;
  onSelectJob: (job: Job) => void;
}

export const AutopilotDashboard: React.FC<AutopilotDashboardProps> = ({
  jobs,
  onJobsRefreshed,
  onSelectJob,
}) => {
  const [config, setConfig] = useState<AutopilotConfig | null>(null);
  const [searchProfiles, setSearchProfiles] = useState<SearchProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [runningCycle, setRunningCycle] = useState(false);
  const [runningQueueOnly, setRunningQueueOnly] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [lastSummary, setLastSummary] = useState<AutopilotRunSummary | null>(null);

  const [imapEmail, setImapEmail] = useState('jkilpatrick50@gmail.com');
  const [imapPassword, setImapPassword] = useState('');
  const [testingEmail, setTestingEmail] = useState(false);
  const [emailStatusMsg, setEmailStatusMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [manualCode, setManualCode] = useState('');
  const [manualCodeMsg, setManualCodeMsg] = useState<string | null>(null);

  useEffect(() => {
    loadInitialData();
  }, []);

  // Poll live incremental progress while an Autopilot cycle is running
  useEffect(() => {
    if (!runningCycle && !runningQueueOnly) return;
    let active = true;
    const timer = setInterval(async () => {
      if (!active) return;
      try {
        const [cfg, updatedJobs] = await Promise.all([
          api.getAutopilotConfig(),
          api.getJobs(),
        ]);
        if (!active) return;
        if (cfg.last_run_summary) {
          setLastSummary(cfg.last_run_summary);
        }
        onJobsRefreshed(updatedJobs);
      } catch {
        // ignore transient poll errors
      }
    }, 2500);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [runningCycle, runningQueueOnly]);

  const loadInitialData = async () => {
    setLoading(true);
    try {
      const [cfg, profiles] = await Promise.all([
        api.getAutopilotConfig(),
        api.getSearchProfiles(),
      ]);
      setConfig(cfg);
      setSearchProfiles(profiles);
      if (cfg.imap_email) {
        setImapEmail(cfg.imap_email);
      }
      if (cfg.last_run_summary) {
        setLastSummary(cfg.last_run_summary);
      }
    } catch (err) {
      console.error('Failed to load autopilot data:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleSaveAndTestEmail = async (e: React.FormEvent) => {
    e.preventDefault();
    setTestingEmail(true);
    setEmailStatusMsg(null);
    try {
      const res = await api.testAutopilotEmail({
        imap_server: 'imap.gmail.com',
        imap_email: imapEmail,
        imap_password: imapPassword || undefined,
        save: true,
      });
      setEmailStatusMsg({ ok: res.success, text: res.message });
      if (res.success && config) {
        setConfig({ ...config, imap_email: imapEmail, imap_password_configured: true });
      }
    } catch (err: any) {
      setEmailStatusMsg({ ok: false, text: err.message || 'Failed to test IMAP connection.' });
    } finally {
      setTestingEmail(false);
    }
  };

  const handleSendManualCode = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!manualCode.trim()) return;
    try {
      const res = await api.submitSecurityCode(manualCode.trim());
      setManualCode('');
      setManualCodeMsg(res.message);
      setTimeout(() => setManualCodeMsg(null), 5000);
    } catch (err: any) {
      setManualCodeMsg(err.message || 'Failed to queue security code');
    }
  };

  const handleSaveConfig = async (updates: Partial<AutopilotConfig>) => {
    if (!config) return;
    const optimistic = { ...config, ...updates };
    setConfig(optimistic);
    setSaving(true);
    try {
      const saved = await api.updateAutopilotConfig(updates);
      setConfig(saved);
      setStatusMessage('Autopilot settings updated.');
      setTimeout(() => setStatusMessage(null), 3000);
    } catch (err) {
      console.error('Failed to update autopilot config:', err);
    } finally {
      setSaving(false);
    }
  };

  const handleRunCycle = async (scrapeNew: boolean) => {
    if (scrapeNew) {
      setRunningCycle(true);
    } else {
      setRunningQueueOnly(true);
    }
    setStatusMessage(
      scrapeNew
        ? 'Autonomous cycle running: scraping suitable listings, tailoring resumes & cover letters, answering questions, and submitting...'
        : 'Processing Need to Apply queue: tailoring documents, answering questions, and attempting submission...'
    );

    try {
      const savedProvider = localStorage.getItem('job_pulse_ai_provider') || config?.ai_provider || 'hadoku';
      const savedApiKey = localStorage.getItem('job_pulse_api_key') || undefined;
      const rawBlocked = localStorage.getItem('job_pulse_blocked_companies');
      if (rawBlocked) {
        try {
          const parsedBlocked = JSON.parse(rawBlocked);
          if (Array.isArray(parsedBlocked) && parsedBlocked.length > 0) {
            await api.updateAutopilotConfig({ blocked_companies: parsedBlocked });
          }
        } catch {
          // ignore
        }
      }

      const res = await api.runAutopilotCycle({
        scrape_new: scrapeNew,
        process_existing_queue: true,
        search_profile_id: config?.search_profile_id,
        min_discover_score: config?.min_discover_score,
        min_auto_apply_score: config?.min_auto_apply_score,
        max_jobs: config?.max_jobs_per_run,
        auto_submit: config?.auto_submit,
        headless: config?.headless,
        require_full_qa_confidence: config?.require_full_qa_confidence,
        ai_provider: savedProvider,
        api_key: savedApiKey,
      });

      if (res.summary) {
        setLastSummary(res.summary);
      }
      if (res.jobs) {
        onJobsRefreshed(res.jobs);
      }
      setStatusMessage(
        `Cycle complete: ${res.summary.auto_applied_count} auto-submitted to Applied, ${res.summary.routed_to_need_to_apply_count} routed to Need to Apply with tailored kit.`
      );
      setTimeout(() => setStatusMessage(null), 7000);
    } catch (err) {
      console.error('Autopilot cycle failed:', err);
      setStatusMessage('Autopilot run encountered an error. Check logs or retry.');
    } finally {
      setRunningCycle(false);
      setRunningQueueOnly(false);
    }
  };

  const needToApplyCount = jobs.filter((j) => j.status === 'TO_APPLY' || j.status === 'WISHLIST').length;
  const autoAppliedTotal = jobs.filter((j) => j.autopilot_status === 'auto_applied').length;
  const preparedNeedToApplyTotal = jobs.filter(
    (j) => j.status === 'TO_APPLY' && j.autopilot_status === 'needs_manual_apply'
  ).length;

  if (loading || !config) {
    return (
      <div className="p-8 text-center text-slate-400 text-sm">
        Loading Autonomous Autopilot Engine...
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto p-6 space-y-6">
      {/* Top Autonomous Hero Banner */}
      <div className="bg-gradient-to-br from-slate-900 via-slate-900 to-emerald-950/30 border border-emerald-500/30 rounded-2xl p-6 shadow-xl">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6">
          <div className="space-y-2 max-w-2xl">
            <div className="flex items-center space-x-2.5">
              <div className="w-10 h-10 rounded-xl bg-emerald-500/15 border border-emerald-500/30 flex items-center justify-center text-emerald-400">
                <Bot className="w-5 h-5" />
              </div>
              <div>
                <div className="flex items-center space-x-2">
                  <h2 className="text-lg font-bold text-white">Autonomous JobPulse Autopilot</h2>
                  <span
                    className={`text-xs px-2.5 py-0.5 rounded-full font-semibold border ${
                      config.enabled
                        ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
                        : 'bg-slate-800 text-slate-400 border-slate-700'
                    }`}
                  >
                    {config.enabled ? `Autonomous Daemon Active (Every ${config.interval_minutes}m)` : 'Manual / On-Demand Mode'}
                  </span>
                </div>
                <p className="text-xs text-slate-400 mt-0.5">
                  Scrapes suitable job listings, generates tailored resumes & cover letters, answers all screening questions, and submits applications automatically whenever possible. Jobs requiring human review or login walls land in <strong className="text-slate-200">Need to Apply</strong> with their tailored packet pre-built.
                </p>
              </div>
            </div>
          </div>

          {/* Primary Actions */}
          <div className="flex flex-wrap items-center gap-3">
            {/* Autonomous Daemon Toggle */}
            <button
              onClick={() => handleSaveConfig({ enabled: !config.enabled })}
              disabled={saving}
              className={`px-3.5 py-2 rounded-xl text-xs font-bold border transition flex items-center space-x-2 ${
                config.enabled
                  ? 'bg-emerald-950/80 border-emerald-500/60 text-emerald-300 hover:bg-emerald-900/60'
                  : 'bg-slate-800 border-slate-700 text-slate-300 hover:text-white hover:bg-slate-700'
              }`}
              title="Enable or disable continuous background scraping and auto-application loop"
            >
              <span
                className={`w-2 h-2 rounded-full ${
                  config.enabled ? 'bg-emerald-400 animate-pulse' : 'bg-slate-500'
                }`}
              />
              <span>{config.enabled ? 'Daemon: ON' : 'Daemon: OFF'}</span>
            </button>

            {/* Process Need to Apply Queue */}
            <button
              onClick={() => handleRunCycle(false)}
              disabled={runningCycle || runningQueueOnly}
              className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 text-xs font-bold flex items-center space-x-1.5 transition disabled:opacity-50"
              title="Generate resumes, cover letters, answer questions, and attempt submission for existing Need to Apply jobs"
            >
              <RefreshCw className={`w-3.5 h-3.5 text-emerald-400 ${runningQueueOnly ? 'animate-spin' : ''}`} />
              <span>
                {runningQueueOnly ? 'Processing Queue...' : `Process Need to Apply (${needToApplyCount})`}
              </span>
            </button>

            {/* Run Full Autonomous Cycle Now */}
            <button
              onClick={() => handleRunCycle(true)}
              disabled={runningCycle || runningQueueOnly}
              className="px-4 py-2 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-500 hover:from-emerald-500 hover:to-teal-400 text-white text-xs font-bold shadow-lg shadow-emerald-500/20 flex items-center space-x-1.5 transition disabled:opacity-50"
            >
              <Play className={`w-3.5 h-3.5 ${runningCycle ? 'animate-spin' : ''}`} />
              <span>{runningCycle ? 'Running Autonomous Cycle...' : 'Run Autonomous Cycle Now'}</span>
            </button>
          </div>
        </div>

        {statusMessage && (
          <div className="mt-4 px-3.5 py-2.5 rounded-xl bg-slate-950/70 border border-emerald-500/30 text-xs text-emerald-300 flex items-center space-x-2">
            <Sparkles className="w-4 h-4 text-emerald-400 shrink-0" />
            <span>{statusMessage}</span>
          </div>
        )}
      </div>

      {/* Pipeline Autonomy Summary Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
        <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-4 space-y-1">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>Scraped Last Run</span>
            <Zap className="w-4 h-4 text-amber-400" />
          </div>
          <div className="text-2xl font-extrabold text-white">
            {lastSummary?.scraped_count ?? 0}
          </div>
          <p className="text-[11px] text-slate-500">
            {lastSummary?.imported_count ?? 0} met fit threshold ({config.min_discover_score}%+)
          </p>
        </div>

        <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-4 space-y-1">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>Tailored Resumes & CLs</span>
            <FileText className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="text-2xl font-extrabold text-white">
            {(lastSummary?.resumes_generated ?? 0) + (lastSummary?.cover_letters_generated ?? 0)}
          </div>
          <p className="text-[11px] text-slate-500">
            {lastSummary?.resumes_generated ?? 0} resumes · {lastSummary?.cover_letters_generated ?? 0} cover letters
          </p>
        </div>

        <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-4 space-y-1">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>Questions Answered</span>
            <HelpCircle className="w-4 h-4 text-cyan-400" />
          </div>
          <div className="text-2xl font-extrabold text-white">
            {lastSummary?.questions_answered ?? 0}
          </div>
          <p className="text-[11px] text-slate-500">
            Standard & role-specific Q&A
          </p>
        </div>

        <div className="bg-slate-900/90 border border-emerald-500/30 rounded-2xl p-4 space-y-1">
          <div className="flex items-center justify-between text-xs text-emerald-400 font-medium">
            <span>Auto-Submitted (Applied)</span>
            <Send className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="text-2xl font-extrabold text-emerald-300">
            {lastSummary?.auto_applied_count ?? autoAppliedTotal}
          </div>
          <p className="text-[11px] text-slate-400">
            {autoAppliedTotal} total auto-applied in pipeline
          </p>
        </div>

        <div className="bg-slate-900/90 border border-blue-500/30 rounded-2xl p-4 space-y-1">
          <div className="flex items-center justify-between text-xs text-blue-300 font-medium">
            <span>Routed to Need to Apply</span>
            <Clock className="w-4 h-4 text-blue-400" />
          </div>
          <div className="text-2xl font-extrabold text-blue-300">
            {lastSummary?.routed_to_need_to_apply_count ?? preparedNeedToApplyTotal}
          </div>
          <p className="text-[11px] text-slate-400">
            {needToApplyCount} currently in Need to Apply stage
          </p>
        </div>
      </div>

      {/* Main Grid: Configuration Controls + Last Run Per-Job Outcome Log */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Autopilot Rules & Thresholds */}
        <div className="lg:col-span-5 bg-slate-900/80 border border-slate-800 rounded-2xl p-5 space-y-5">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <div className="flex items-center space-x-2">
              <Sliders className="w-4 h-4 text-emerald-400" />
              <h3 className="font-bold text-sm text-white">Autonomous Rules & Thresholds</h3>
            </div>
            <span className="text-[11px] text-slate-500">Auto-saves on change</span>
          </div>

          {/* Active Search Profile */}
          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-slate-300 flex items-center space-x-1.5">
              <Layers className="w-3.5 h-3.5 text-emerald-400" />
              <span>Target Search Profile</span>
            </label>
            <select
              value={config.search_profile_id ?? ''}
              onChange={(e) =>
                handleSaveConfig({
                  search_profile_id: e.target.value ? Number(e.target.value) : null,
                })
              }
              className="w-full bg-slate-800 border border-slate-700 rounded-xl px-3 py-2 text-xs text-slate-200 focus:outline-none focus:ring-1 focus:ring-emerald-500"
            >
              <option value="">Default Active Search Profile</option>
              {searchProfiles.map((sp) => (
                <option key={sp.id} value={sp.id}>
                  {sp.name} ({sp.track.toUpperCase()} · {sp.remote_pref})
                </option>
              ))}
            </select>
            <p className="text-[11px] text-slate-500">
              Controls target keywords, companies, role track (IC vs Manager), ladder levels, and location filters.
            </p>
          </div>

          {/* Fit Score Thresholds */}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-xs font-semibold text-slate-300 block">
                Min Score to Discover (%)
              </label>
              <input
                type="number"
                min={0}
                max={100}
                value={config.min_discover_score}
                onChange={(e) =>
                  handleSaveConfig({ min_discover_score: Number(e.target.value) })
                }
                className="w-full bg-slate-800 border border-slate-700 rounded-xl px-3 py-1.5 text-xs text-slate-100 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              />
              <span className="text-[10px] text-slate-500 block">
                Imports matching jobs into pipeline
              </span>
            </div>

            <div className="space-y-1">
              <label className="text-xs font-semibold text-emerald-300 block">
                Min Score to Auto-Submit (%)
              </label>
              <input
                type="number"
                min={0}
                max={100}
                value={config.min_auto_apply_score}
                onChange={(e) =>
                  handleSaveConfig({ min_auto_apply_score: Number(e.target.value) })
                }
                className="w-full bg-slate-800 border border-slate-700 rounded-xl px-3 py-1.5 text-xs text-slate-100 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              />
              <span className="text-[10px] text-slate-500 block">
                Lower scores go to Need to Apply
              </span>
            </div>
          </div>

          {/* Max Jobs & Schedule Interval */}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-xs font-semibold text-slate-300 block">
                Max Jobs per Cycle
              </label>
              <input
                type="number"
                min={1}
                max={50}
                value={config.max_jobs_per_run}
                onChange={(e) =>
                  handleSaveConfig({ max_jobs_per_run: Number(e.target.value) })
                }
                className="w-full bg-slate-800 border border-slate-700 rounded-xl px-3 py-1.5 text-xs text-slate-100 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              />
            </div>

            <div className="space-y-1">
              <label className="text-xs font-semibold text-slate-300 block">
                Daemon Interval (Minutes)
              </label>
              <input
                type="number"
                min={5}
                max={1440}
                value={config.interval_minutes}
                onChange={(e) =>
                  handleSaveConfig({ interval_minutes: Number(e.target.value) })
                }
                className="w-full bg-slate-800 border border-slate-700 rounded-xl px-3 py-1.5 text-xs text-slate-100 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              />
            </div>
          </div>

          {/* Checkboxes / Guardrails */}
          <div className="space-y-2.5 pt-2 border-t border-slate-800">
            <label className="flex items-start space-x-2.5 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={config.auto_submit}
                onChange={(e) => handleSaveConfig({ auto_submit: e.target.checked })}
                className="mt-0.5 rounded bg-slate-800 border-slate-700 text-emerald-600 focus:ring-0"
              />
              <div>
                <span className="text-xs font-semibold text-slate-200 block">
                  Auto-Submit Applications Whenever Possible
                </span>
                <span className="text-[11px] text-slate-400 block">
                  Submits direct ATS forms automatically and marks them Applied. Unsubmittable forms fall back to Need to Apply.
                </span>
              </div>
            </label>

            <label className="flex items-start space-x-2.5 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={config.require_full_qa_confidence}
                onChange={(e) =>
                  handleSaveConfig({ require_full_qa_confidence: e.target.checked })
                }
                className="mt-0.5 rounded bg-slate-800 border-slate-700 text-emerald-600 focus:ring-0"
              />
              <div>
                <span className="text-xs font-semibold text-slate-200 block">
                  Require High Confidence on All Required Questions
                </span>
                <span className="text-[11px] text-slate-400 block">
                  Routes jobs with ambiguous or unrecognized required questions to Need to Apply instead of guessing.
                </span>
              </div>
            </label>

            <label className="flex items-start space-x-2.5 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={config.headless}
                onChange={(e) => handleSaveConfig({ headless: e.target.checked })}
                className="mt-0.5 rounded bg-slate-800 border-slate-700 text-emerald-600 focus:ring-0"
              />
              <div>
                <span className="text-xs font-semibold text-slate-200 block">
                  Run Browser Automation in Headless Background Mode
                </span>
                <span className="text-[11px] text-slate-400 block">
                  Uncheck to watch Playwright fill forms in a visible browser window during autonomous cycles.
                </span>
              </div>
            </label>
          </div>

          <div className="p-3 rounded-xl bg-slate-950/60 border border-slate-800 text-[11px] text-slate-400 flex items-start space-x-2">
            <ShieldCheck className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
            <span>
              <strong className="text-slate-200">Safety & Routing Guarantee:</strong> Portals with login walls (Workday, LinkedIn, iCIMS), CAPTCHA challenges, or custom required questions that cannot be verified are never forced — they are automatically placed in <strong className="text-blue-300">Need to Apply</strong> with tailored resumes, cover letters, and draft answers attached.
            </span>
          </div>

          {/* Automatic Email Verification Code Reader (Greenhouse 8-Char Security Code) */}
          <div className="pt-4 border-t border-slate-800 space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <Mail className="w-4 h-4 text-emerald-400" />
                <h4 className="font-bold text-xs uppercase tracking-wider text-slate-200">
                  Automatic Email Code Retrieval (Greenhouse 2FA)
                </h4>
              </div>
              {config.imap_password_configured && (
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 font-bold">
                  Active
                </span>
              )}
            </div>

            <p className="text-[11px] text-slate-400 leading-relaxed">
              Greenhouse emails an 8-character security code when submitting an application. Connect a Gmail App Password so Autopilot can read the code from your inbox, fill the 8 boxes, and finish submitting automatically.{' '}
              <a
                href="https://myaccount.google.com/apppasswords"
                target="_blank"
                rel="noopener noreferrer"
                className="text-emerald-400 hover:underline font-medium"
              >
                Create Gmail App Password →
              </a>
            </p>

            <form onSubmit={handleSaveAndTestEmail} className="space-y-2">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                <input
                  type="email"
                  placeholder="jkilpatrick50@gmail.com"
                  value={imapEmail}
                  onChange={(e) => setImapEmail(e.target.value)}
                  className="bg-slate-800 border border-slate-700 rounded-xl px-3 py-1.5 text-xs text-slate-100 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                />
                <input
                  type="password"
                  placeholder={config.imap_password_configured ? '•••••••••••••••• (Saved)' : '16-char Gmail App Password'}
                  value={imapPassword}
                  onChange={(e) => setImapPassword(e.target.value)}
                  className="bg-slate-800 border border-slate-700 rounded-xl px-3 py-1.5 text-xs text-slate-100 focus:outline-none focus:ring-1 focus:ring-emerald-500 font-mono"
                />
              </div>
              <button
                type="submit"
                disabled={testingEmail}
                className="w-full py-2 px-3 rounded-xl bg-slate-800 hover:bg-slate-700 border border-emerald-500/40 text-emerald-300 text-xs font-bold transition disabled:opacity-50"
              >
                {testingEmail ? 'Testing IMAP Inbox...' : 'Save & Test Automatic Email Code Reader'}
              </button>
            </form>

            {emailStatusMsg && (
              <div
                className={`p-2.5 rounded-xl border text-xs ${
                  emailStatusMsg.ok
                    ? 'bg-emerald-950/40 border-emerald-700/50 text-emerald-300'
                    : 'bg-rose-950/40 border-rose-700/50 text-rose-300'
                }`}
              >
                {emailStatusMsg.text}
              </div>
            )}

            {/* Quick Manual 8-Character Security Code Drop-Box */}
            <form onSubmit={handleSendManualCode} className="pt-2 space-y-1.5">
              <label className="text-[11px] font-semibold text-slate-300 flex items-center space-x-1">
                <KeyRound className="w-3 h-3 text-amber-400" />
                <span>Or Paste 8-Char Greenhouse Code From Email:</span>
              </label>
              <div className="flex gap-2">
                <input
                  type="text"
                  maxLength={12}
                  placeholder="e.g. X7k9P2mQ"
                  value={manualCode}
                  onChange={(e) => setManualCode(e.target.value)}
                  className="flex-1 bg-slate-800 border border-slate-700 rounded-xl px-3 py-1.5 text-xs text-slate-100 font-mono focus:outline-none focus:ring-1 focus:ring-emerald-500"
                />
                <button
                  type="submit"
                  disabled={!manualCode.trim()}
                  className="px-3 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold disabled:opacity-50"
                >
                  Send Code
                </button>
              </div>
              {manualCodeMsg && (
                <p className="text-[11px] text-emerald-400 font-medium">{manualCodeMsg}</p>
              )}
            </form>
          </div>
        </div>

        {/* Right Column: Execution Log & Routing Breakdown */}
        <div className="lg:col-span-7 bg-slate-900/80 border border-slate-800 rounded-2xl p-5 flex flex-col">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3 mb-4">
            <div>
              <h3 className="font-bold text-sm text-white">Autonomous Processing & Routing Log</h3>
              <p className="text-xs text-slate-400">
                {lastSummary
                  ? `Last cycle (${lastSummary.search_profile_used}) completed in ${lastSummary.duration_seconds}s`
                  : 'Click "Run Autonomous Cycle Now" to scrape, tailor, answer questions, and apply'}
              </p>
            </div>
            {config.last_run_at && (
              <span className="text-[11px] text-slate-500">
                {new Date(config.last_run_at).toLocaleTimeString()}
              </span>
            )}
          </div>

          {(!lastSummary || lastSummary.job_results.length === 0) ? (
            <div className="flex-1 flex flex-col items-center justify-center py-12 text-center space-y-3">
              <Bot className="w-10 h-10 text-slate-600" />
              <div className="space-y-1">
                <p className="text-sm font-semibold text-slate-300">No Autopilot Run Recorded Yet</p>
                <p className="text-xs text-slate-500 max-w-md">
                  Trigger an autonomous cycle above to scrape suitable job listings, generate tailored resumes and cover letters, answer all screening questions, and submit or route to Need to Apply.
                </p>
              </div>
            </div>
          ) : (
            <div className="space-y-2.5 max-h-[460px] overflow-y-auto pr-1">
              {lastSummary.job_results.map((item) => {
                const matchingJob = jobs.find((j) => j.id === item.job_id);
                const isApplied = item.outcome === 'auto_applied';
                const isExpired = item.outcome === 'skipped_expired';

                return (
                  <div
                    key={item.job_id}
                    onClick={() => matchingJob && onSelectJob(matchingJob)}
                    className="p-3.5 rounded-xl bg-slate-950/60 hover:bg-slate-800/70 border border-slate-800 hover:border-emerald-500/40 transition cursor-pointer flex flex-col sm:flex-row sm:items-center justify-between gap-3"
                  >
                    <div className="space-y-1 min-w-0">
                      <div className="flex items-center space-x-2 flex-wrap gap-y-1">
                        <span className="font-bold text-xs text-white truncate">
                          {item.title}
                        </span>
                        <span className="text-xs text-slate-400">at</span>
                        <span className="font-semibold text-xs text-emerald-400">
                          {item.company}
                        </span>
                        {item.fit_score !== undefined && (
                          <span className="text-[10px] px-2 py-0.5 rounded-full bg-slate-800 border border-slate-700 text-slate-300 font-semibold">
                            {item.fit_score}% Fit
                          </span>
                        )}
                      </div>

                      <p className="text-xs text-slate-400 leading-relaxed">
                        {item.reason}
                      </p>

                      {item.documents_generated && (
                        <div className="flex items-center space-x-3 pt-0.5 text-[11px] text-slate-400">
                          <span className="text-emerald-400/90 flex items-center space-x-1">
                            <CheckCircle2 className="w-3 h-3" />
                            <span>Tailored Resume & Cover Letter</span>
                          </span>
                          <span>•</span>
                          <span className="text-cyan-400/90">
                            {item.questions_answered} Questions Answered
                          </span>
                        </div>
                      )}
                    </div>

                    <div className="flex items-center space-x-2 shrink-0">
                      {isApplied ? (
                        <span className="px-2.5 py-1 rounded-lg text-xs font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 flex items-center space-x-1">
                          <Send className="w-3 h-3" />
                          <span>Applied</span>
                        </span>
                      ) : isExpired ? (
                        <span className="px-2.5 py-1 rounded-lg text-xs font-bold bg-rose-500/20 text-rose-300 border border-rose-500/40 flex items-center space-x-1">
                          <AlertTriangle className="w-3 h-3" />
                          <span>Expired</span>
                        </span>
                      ) : (
                        <span className="px-2.5 py-1 rounded-lg text-xs font-bold bg-blue-500/20 text-blue-300 border border-blue-500/40 flex items-center space-x-1">
                          <Clock className="w-3 h-3" />
                          <span>Need to Apply</span>
                        </span>
                      )}
                      <ExternalLink className="w-3.5 h-3.5 text-slate-500" />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
