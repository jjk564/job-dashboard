import React, { useState, useEffect, useRef, lazy, Suspense } from 'react';
import { Navbar } from './components/Navbar';
import { KanbanBoard } from './components/Kanban/KanbanBoard';

// Everything but the board loads on first use: hadoku.me budgets an app's
// first-load JS (60 kB gzip), and Discovery alone is most of this bundle.
const JobDiscovery = lazy(() => import('./components/Discovery/JobDiscovery').then(m => ({ default: m.JobDiscovery })));
const ProfileManager = lazy(() => import('./components/Profile/ProfileManager').then(m => ({ default: m.ProfileManager })));
const AnalyticsDashboard = lazy(() => import('./components/Analytics/AnalyticsDashboard').then(m => ({ default: m.AnalyticsDashboard })));
const JobDetailDrawer = lazy(() => import('./components/JobDetails/JobDetailDrawer').then(m => ({ default: m.JobDetailDrawer })));
const ImportJobModal = lazy(() => import('./components/Common/ImportJobModal').then(m => ({ default: m.ImportJobModal })));
const AddJobModal = lazy(() => import('./components/Common/AddJobModal').then(m => ({ default: m.AddJobModal })));
const SettingsModal = lazy(() => import('./components/Settings/SettingsModal').then(m => ({ default: m.SettingsModal })));
import { Job, JobStatus } from './types';
import { api } from './api/client';
import type { JobPlatformProps } from './entry';

type AppTab = 'pipeline' | 'discovery' | 'profile' | 'analytics';
const VALID_TABS: AppTab[] = ['pipeline', 'discovery', 'profile', 'analytics'];

function getInitialTab(): AppTab {
  if (typeof window !== 'undefined') {
    const hash = window.location.hash.replace(/^#\/?/, '').trim().toLowerCase() as AppTab;
    if (VALID_TABS.includes(hash)) {
      return hash;
    }
    const saved = localStorage.getItem('job_pulse_active_tab') as AppTab | null;
    if (saved && VALID_TABS.includes(saved)) {
      return saved;
    }
  }
  return 'pipeline';
}

/** True from the first time `open` is true: lazily loaded views stay mounted after. */
function useOpenedOnce(open: boolean): boolean {
  const [opened, setOpened] = useState(open);
  useEffect(() => {
    if (open) setOpened(true);
  }, [open]);
  return opened || open;
}

export const App: React.FC<JobPlatformProps> = ({ appName, theme, embedded }) => {
  const [activeTab, setActiveTabState] = useState<AppTab>(getInitialTab);

  const setActiveTab = (tab: AppTab) => {
    setActiveTabState(tab);
    try {
      localStorage.setItem('job_pulse_active_tab', tab);
      if (typeof window !== 'undefined' && window.location.hash !== `#${tab}`) {
        window.history.replaceState(null, '', `#${tab}`);
      }
    } catch {
      // Ignore storage errors
    }
  };

  useEffect(() => {
    try {
      localStorage.setItem('job_pulse_active_tab', activeTab);
      if (typeof window !== 'undefined' && window.location.hash !== `#${activeTab}`) {
        window.history.replaceState(null, '', `#${activeTab}`);
      }
    } catch {
      // Ignore storage errors
    }
  }, [activeTab]);

  useEffect(() => {
    const onHashChange = () => {
      const hash = window.location.hash.replace(/^#\/?/, '').trim().toLowerCase() as AppTab;
      if (VALID_TABS.includes(hash)) {
        setActiveTabState(hash);
        localStorage.setItem('job_pulse_active_tab', hash);
      }
    };
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [updatingJobIds, setUpdatingJobIds] = useState<Set<string>>(new Set());
  const updateSeqRef = useRef<Map<string, number>>(new Map());

  // Modals & Drawers
  const [selectedJob, setSelectedJob] = useState<Job | null>(null);
  const [isAddJobOpen, setIsAddJobOpen] = useState(false);
  const [isImportUrlOpen, setIsImportUrlOpen] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const discoveryOpened = useOpenedOnce(activeTab === 'discovery');
  const drawerOpened = useOpenedOnce(selectedJob !== null);
  const importOpened = useOpenedOnce(isImportUrlOpen);
  const addOpened = useOpenedOnce(isAddJobOpen);
  const settingsOpened = useOpenedOnce(isSettingsOpen);
  const [settingsTab, setSettingsTab] = useState<'ai' | 'hidden'>('ai');
  const [liveUpdateToast, setLiveUpdateToast] = useState(false);
  const bootIdRef = useRef<string | null>(null);

  // Load jobs on mount
  useEffect(() => {
    loadJobs();
  }, []);

  // Poll backend health boot_id to automatically sync live backend updates without reopening
  useEffect(() => {
    let active = true;
    let toastTimer: ReturnType<typeof setTimeout> | null = null;

    const checkBackendReload = async () => {
      if (document.visibilityState === 'hidden') return;
      try {
        const health = await api.getHealth();
        if (!active || !health.boot_id) return;
        if (bootIdRef.current === null) {
          bootIdRef.current = health.boot_id;
        } else if (bootIdRef.current !== health.boot_id) {
          bootIdRef.current = health.boot_id;
          await loadJobs(true);
          window.dispatchEvent(new CustomEvent('jobpulse:backend-reloaded'));
          setLiveUpdateToast(true);
          if (toastTimer) clearTimeout(toastTimer);
          toastTimer = setTimeout(() => {
            if (active) setLiveUpdateToast(false);
          }, 2500);
        }
      } catch {
        // Backend is mid-reload; next tick will catch the new boot_id
      }
    };

    checkBackendReload();
    const interval = setInterval(checkBackendReload, 3000);
    return () => {
      active = false;
      clearInterval(interval);
      if (toastTimer) clearTimeout(toastTimer);
    };
  }, []);

  const loadJobs = async (silent: boolean = false) => {
    try {
      const data = await api.getJobs();
      setJobs(data);
    } catch (err) {
      console.error('Failed to load jobs:', err);
    } finally {
      if (!silent) {
        setLoading(false);
      }
    }
  };

  // Status Change handler with race-condition and stale-response protection
  const handleUpdateJobStatus = async (id: string, newStatus: JobStatus) => {
    const nowIso = new Date().toISOString();
    const seq = (updateSeqRef.current.get(id) || 0) + 1;
    updateSeqRef.current.set(id, seq);

    // Track active updating state
    setUpdatingJobIds((prev) => new Set(prev).add(id));

    // Optimistic update: advance status, update timestamp, and move to top of list
    setJobs((prev) => {
      const existing = prev.find((j) => j.id === id);
      if (!existing) return prev;
      const updatedJob = { ...existing, status: newStatus, updated_at: nowIso };
      return [updatedJob, ...prev.filter((j) => j.id !== id)];
    });

    try {
      const updated = await api.updateJob(id, { status: newStatus });
      // Only apply server response if this is still the newest request for this job
      if (updateSeqRef.current.get(id) === seq) {
        setJobs((prev) => [updated, ...prev.filter((j) => j.id !== id)]);
        if (selectedJob && selectedJob.id === id) {
          setSelectedJob(updated);
        }
      }
    } catch (err) {
      console.error('Status update failed, reloading:', err);
      if (updateSeqRef.current.get(id) === seq) {
        loadJobs();
      }
    } finally {
      if (updateSeqRef.current.get(id) === seq) {
        setUpdatingJobIds((prev) => {
          const next = new Set(prev);
          next.delete(id);
          return next;
        });
      }
    }
  };

  // Delete handler
  const handleDeleteJob = async (id: string) => {
    try {
      await api.deleteJob(id);
      setJobs((prev) => prev.filter((j) => j.id !== id));
      if (selectedJob?.id === id) {
        setSelectedJob(null);
      }
    } catch (err) {
      console.error('Failed to delete job:', err);
    }
  };

  // Job created or updated
  const handleJobAdded = (newJob: Job) => {
    setJobs((prev) => [newJob, ...prev]);
  };

  const handleJobUpdated = (updated: Job) => {
    setJobs((prev) => [updated, ...prev.filter((j) => j.id !== updated.id)]);
    if (selectedJob?.id === updated.id) {
      setSelectedJob(updated);
    }
  };

  const handleJobsRefreshed = (refreshed: Job[]) => {
    setJobs((prev) => {
      const refreshedMap = new Map(refreshed.map((j) => [j.id, j]));
      // Update existing jobs with refreshed data, preserving any jobs not in refreshed
      const merged = prev.map((j) => refreshedMap.get(j.id) || j);
      // Append any new jobs from refreshed that weren't in prev
      const existingIds = new Set(prev.map((j) => j.id));
      for (const j of refreshed) {
        if (!existingIds.has(j.id)) {
          merged.push(j);
        }
      }
      return merged;
    });
  };

  return (
    <div
      data-theme={theme}
      className={`job-platform-container ${embedded ? 'flex-1 min-h-0' : 'h-screen max-h-screen'} bg-slate-900 text-slate-100 flex flex-col font-sans overflow-hidden`}
    >
      <Navbar
        appName={appName}
        embedded={embedded}
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        onOpenAddJob={() => setIsAddJobOpen(true)}
        onOpenImportUrl={() => setIsImportUrlOpen(true)}
        onOpenSettings={(tab) => {
          setSettingsTab(tab || 'ai');
          setIsSettingsOpen(true);
        }}
        jobCount={jobs.length}
      />

      <main className="flex-1 min-h-0 flex flex-col overflow-hidden">
        {loading ? (
          <div className="flex-1 flex items-center justify-center text-slate-400 text-sm">
            Initializing local JobPulse pipeline...
          </div>
        ) : (
          <>
            {activeTab === 'pipeline' && (
              <KanbanBoard
                jobs={jobs}
                onSelectJob={(job) => setSelectedJob(job)}
                onUpdateJobStatus={handleUpdateJobStatus}
                onDeleteJob={handleDeleteJob}
                onJobsRefreshed={handleJobsRefreshed}
                updatingJobIds={updatingJobIds}
              />
            )}

            {discoveryOpened && (
            <div className={activeTab === 'discovery' ? 'flex-1 min-h-0 flex flex-col overflow-hidden' : 'hidden'}>
              <Suspense fallback={null}>
              <JobDiscovery
                pipelineJobs={jobs}
                onJobAdded={handleJobAdded}
                onOpenSettings={(tab) => {
                  setSettingsTab(tab || 'hidden');
                  setIsSettingsOpen(true);
                }}
              />
              </Suspense>
            </div>
            )}

            {activeTab === 'profile' && (
              <div className="flex-1 overflow-y-auto">
                <Suspense fallback={null}>
                  <ProfileManager onJobsScored={handleJobsRefreshed} />
                </Suspense>
              </div>
            )}

            {activeTab === 'analytics' && (
              <div className="flex-1 overflow-y-auto">
                <Suspense fallback={null}>
                  <AnalyticsDashboard />
                </Suspense>
              </div>
            )}
          </>
        )}
      </main>

      {/* Loaded on first use (see the lazy imports above); mounted from then on
          so each keeps its close animation and state as before. */}
      <Suspense fallback={null}>
        {(selectedJob || drawerOpened) && (
          <JobDetailDrawer
            job={selectedJob}
            onClose={() => setSelectedJob(null)}
            onJobUpdated={handleJobUpdated}
            onDeleteJob={handleDeleteJob}
          />
        )}

        {(isImportUrlOpen || importOpened) && (
          <ImportJobModal
            isOpen={isImportUrlOpen}
            onClose={() => setIsImportUrlOpen(false)}
            onJobAdded={handleJobAdded}
          />
        )}

        {(isAddJobOpen || addOpened) && (
          <AddJobModal
            isOpen={isAddJobOpen}
            onClose={() => setIsAddJobOpen(false)}
            onJobAdded={handleJobAdded}
          />
        )}

        {(isSettingsOpen || settingsOpened) && (
          <SettingsModal
            isOpen={isSettingsOpen}
            onClose={() => setIsSettingsOpen(false)}
            initialTab={settingsTab}
          />
        )}
      </Suspense>

      {liveUpdateToast && (
        <div className="fixed bottom-4 right-4 z-50 flex items-center gap-2 px-3.5 py-2 rounded-lg bg-emerald-950/90 border border-emerald-500/40 text-emerald-200 text-xs font-medium shadow-lg backdrop-blur-sm">
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          <span>Live update synced</span>
        </div>
      )}
    </div>
  );
};

export default App;
