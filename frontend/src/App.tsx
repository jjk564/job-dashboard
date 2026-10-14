import React, { useState, useEffect } from 'react';
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

  // Modals & Drawers
  const [selectedJob, setSelectedJob] = useState<Job | null>(null);
  const [isAddJobOpen, setIsAddJobOpen] = useState(false);
  const [isImportUrlOpen, setIsImportUrlOpen] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);

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

  // Status Change handler
  const handleUpdateJobStatus = async (id: number, newStatus: JobStatus) => {
    // Optimistic update
    setJobs((prev) =>
      prev.map((j) => (j.id === id ? { ...j, status: newStatus } : j))
    );

    try {
      const updated = await api.updateJob(id, { status: newStatus });
      setJobs((prev) => prev.map((j) => (j.id === id ? updated : j)));
      if (selectedJob && selectedJob.id === id) {
        setSelectedJob(updated);
      }
    } catch (err) {
      console.error('Status update failed, reloading:', err);
      loadJobs();
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
    setJobs((prev) => prev.map((j) => (j.id === updated.id ? updated : j)));
    if (selectedJob?.id === updated.id) {
      setSelectedJob(updated);
    }
  };

  return (
    <div className="min-h-screen bg-slate-900 text-slate-100 flex flex-col font-sans">
      <Navbar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        onOpenAddJob={() => setIsAddJobOpen(true)}
        onOpenImportUrl={() => setIsImportUrlOpen(true)}
        onOpenSettings={() => setIsSettingsOpen(true)}
        jobCount={jobs.length}
      />

      <main className="flex-1 flex flex-col overflow-hidden">
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
              />
            )}

            {activeTab === 'discovery' && (
              <JobDiscovery onJobAdded={handleJobAdded} />
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
      />
    </div>
  );
};

export default App;
