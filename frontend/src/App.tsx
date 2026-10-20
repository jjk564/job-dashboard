import React, { useState, useEffect, useRef } from 'react';
import { Navbar } from './components/Navbar';
import { KanbanBoard } from './components/Kanban/KanbanBoard';
import { JobDiscovery } from './components/Discovery/JobDiscovery';
import { ProfileManager } from './components/Profile/ProfileManager';
import { AnalyticsDashboard } from './components/Analytics/AnalyticsDashboard';
import { JobDetailDrawer } from './components/JobDetails/JobDetailDrawer';
import { ImportJobModal } from './components/Common/ImportJobModal';
import { AddJobModal } from './components/Common/AddJobModal';
import { SettingsModal } from './components/Settings/SettingsModal';
import { Job, JobStatus } from './types';
import { api } from './api/client';

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'pipeline' | 'discovery' | 'profile' | 'analytics'>('pipeline');
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [updatingJobIds, setUpdatingJobIds] = useState<Set<number>>(new Set());
  const updateSeqRef = useRef<Map<number, number>>(new Map());

  // Modals & Drawers
  const [selectedJob, setSelectedJob] = useState<Job | null>(null);
  const [isAddJobOpen, setIsAddJobOpen] = useState(false);
  const [isImportUrlOpen, setIsImportUrlOpen] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [settingsTab, setSettingsTab] = useState<'ai' | 'hidden'>('ai');

  // Load jobs on mount
  useEffect(() => {
    loadJobs();
  }, []);

  const loadJobs = async () => {
    try {
      const data = await api.getJobs();
      setJobs(data);
    } catch (err) {
      console.error('Failed to load jobs:', err);
    } finally {
      setLoading(false);
    }
  };

  // Status Change handler with race-condition and stale-response protection
  const handleUpdateJobStatus = async (id: number, newStatus: JobStatus) => {
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
  const handleDeleteJob = async (id: number) => {
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

  return (
    <div className="h-screen max-h-screen bg-slate-900 text-slate-100 flex flex-col font-sans overflow-hidden">
      <Navbar
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
                onJobsRefreshed={(refreshed) => setJobs(refreshed)}
                updatingJobIds={updatingJobIds}
              />
            )}

            {activeTab === 'discovery' && (
              <JobDiscovery
                pipelineJobs={jobs}
                onJobAdded={handleJobAdded}
                onOpenSettings={(tab) => {
                  setSettingsTab(tab || 'hidden');
                  setIsSettingsOpen(true);
                }}
              />
            )}

            {activeTab === 'profile' && (
              <div className="flex-1 overflow-y-auto">
                <ProfileManager />
              </div>
            )}

            {activeTab === 'analytics' && (
              <div className="flex-1 overflow-y-auto">
                <AnalyticsDashboard />
              </div>
            )}
          </>
        )}
      </main>

      {/* Side Drawer for Selected Job */}
      <JobDetailDrawer
        job={selectedJob}
        onClose={() => setSelectedJob(null)}
        onJobUpdated={handleJobUpdated}
        onDeleteJob={handleDeleteJob}
      />

      {/* Modals */}
      <ImportJobModal
        isOpen={isImportUrlOpen}
        onClose={() => setIsImportUrlOpen(false)}
        onJobAdded={handleJobAdded}
      />

      <AddJobModal
        isOpen={isAddJobOpen}
        onClose={() => setIsAddJobOpen(false)}
        onJobAdded={handleJobAdded}
      />

      <SettingsModal
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
        initialTab={settingsTab}
      />
    </div>
  );
};

export default App;
