import React from 'react';
import { 
  Briefcase, 
  Compass, 
  UserCheck, 
  BarChart3, 
  Plus, 
  Link2, 
  Settings 
} from 'lucide-react';

interface NavbarProps {
  appName?: string;
  activeTab: 'pipeline' | 'discovery' | 'profile' | 'analytics';
  setActiveTab: (tab: 'pipeline' | 'discovery' | 'profile' | 'analytics') => void;
  onOpenAddJob: () => void;
  onOpenImportUrl: () => void;
  onOpenSettings: (tab?: 'ai' | 'hidden') => void;
  jobCount: number;
}

export const Navbar: React.FC<NavbarProps> = ({
  appName,
  activeTab,
  setActiveTab,
  onOpenAddJob,
  onOpenImportUrl,
  onOpenSettings,
  jobCount,
}) => {
  return (
    <header className="bg-slate-900 border-b border-slate-800 shrink-0 z-30">
      <div className="w-full px-4 sm:px-5 lg:px-6">
        <div className="flex items-center justify-between h-16">
          {/* Brand */}
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-emerald-600 to-teal-400 flex items-center justify-center shadow-lg shadow-emerald-500/20">
              <Briefcase className="w-5 h-5 text-white" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <span className="font-bold text-lg text-white tracking-tight">{appName || 'JobPulse'}</span>
                <span className="text-xs bg-emerald-500/10 text-emerald-400 font-medium px-2 py-0.5 rounded-full border border-emerald-500/20">
                  Local Copilot
                </span>
              </div>
              <p className="text-xs text-slate-400">Autonomous Job Pipeline & ATS Assistant</p>
            </div>
          </div>

          {/* Navigation Tabs */}
          <nav className="flex space-x-1 bg-slate-800/80 p-1 rounded-xl border border-slate-700/60">
            <button
              onClick={() => setActiveTab('pipeline')}
              className={`flex items-center space-x-2 px-3.5 py-1.5 rounded-lg text-sm font-medium transition-all ${
                activeTab === 'pipeline'
                  ? 'bg-emerald-600 text-white shadow-sm'
                  : 'text-slate-300 hover:text-white hover:bg-slate-700/50'
              }`}
            >
              <Briefcase className="w-4 h-4" />
              <span>Pipeline</span>
              <span className={`text-xs px-1.5 py-0.2 rounded-full font-semibold ${
                activeTab === 'pipeline' ? 'bg-emerald-700 text-emerald-100' : 'bg-slate-700 text-slate-300'
              }`}>
                {jobCount}
              </span>
            </button>

            <button
              onClick={() => setActiveTab('discovery')}
              className={`flex items-center space-x-2 px-3.5 py-1.5 rounded-lg text-sm font-medium transition-all ${
                activeTab === 'discovery'
                  ? 'bg-emerald-600 text-white shadow-sm'
                  : 'text-slate-300 hover:text-white hover:bg-slate-700/50'
              }`}
            >
              <Compass className="w-4 h-4" />
              <span>Discover Jobs</span>
            </button>

            <button
              onClick={() => setActiveTab('profile')}
              className={`flex items-center space-x-2 px-3.5 py-1.5 rounded-lg text-sm font-medium transition-all ${
                activeTab === 'profile'
                  ? 'bg-emerald-600 text-white shadow-sm'
                  : 'text-slate-300 hover:text-white hover:bg-slate-700/50'
              }`}
            >
              <UserCheck className="w-4 h-4" />
              <span>My Profile</span>
            </button>

            <button
              onClick={() => setActiveTab('analytics')}
              className={`flex items-center space-x-2 px-3.5 py-1.5 rounded-lg text-sm font-medium transition-all ${
                activeTab === 'analytics'
                  ? 'bg-emerald-600 text-white shadow-sm'
                  : 'text-slate-300 hover:text-white hover:bg-slate-700/50'
              }`}
            >
              <BarChart3 className="w-4 h-4" />
              <span>Analytics</span>
            </button>
          </nav>

          {/* Action Buttons */}
          <div className="flex items-center space-x-2.5">
            <button
              onClick={onOpenImportUrl}
              className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-sm font-medium bg-slate-800 hover:bg-slate-700 text-emerald-400 border border-slate-700 transition"
              title="Import Job from URL"
            >
              <Link2 className="w-4 h-4" />
              <span>Import URL</span>
            </button>

            <button
              onClick={onOpenAddJob}
              className="flex items-center space-x-1.5 px-3.5 py-1.5 rounded-lg text-sm font-medium bg-emerald-600 hover:bg-emerald-500 text-white shadow-sm transition"
            >
              <Plus className="w-4 h-4" />
              <span>Add Job</span>
            </button>

            <button
              onClick={() => onOpenSettings()}
              className="p-2 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 border border-transparent hover:border-slate-700 transition"
              title="Settings & AI Configuration"
            >
              <Settings className="w-5 h-5" />
            </button>
          </div>
        </div>
      </div>
    </header>
  );
};
