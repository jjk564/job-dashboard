import React, { useState, useEffect, useMemo } from 'react';
import { 
  UserCheck, 
  Save, 
  Plus, 
  Trash2, 
  Check, 
  Sparkles, 
  Link2, 
  FileText 
} from 'lucide-react';
import { Profile, Skill, Job } from '../../types';
import { api } from '../../api/client';
import { SearchProfilesSection } from './SearchProfilesSection';

interface ProfileManagerProps {
  onJobsScored?: (jobs: Job[]) => void;
}

export const ProfileManager: React.FC<ProfileManagerProps> = ({ onJobsScored }) => {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [initialProfile, setInitialProfile] = useState<Profile | null>(null);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savedBanner, setSavedBanner] = useState(false);

  // New skill input
  const [newSkillName, setNewSkillName] = useState('');
  const [newSkillCategory, setNewSkillCategory] = useState('languages');
  const [newSkillProficiency, setNewSkillProficiency] = useState<'beginner' | 'intermediate' | 'expert'>('intermediate');

  useEffect(() => {
    loadData();
    const onReload = () => {
      loadData(true);
    };
    window.addEventListener('jobpulse:backend-reloaded', onReload);
    return () => window.removeEventListener('jobpulse:backend-reloaded', onReload);
  }, []);

  const loadData = async (silent: boolean = false) => {
    if (!silent) setLoading(true);
    try {
      const [profData, skillsData] = await Promise.all([
        api.getProfile(),
        api.getSkills(),
      ]);
      setProfile(profData);
      setInitialProfile(profData);
      setSkills(skillsData);
    } catch (err) {
      console.error('Failed to load profile data:', err);
    } finally {
      if (!silent) setLoading(false);
    }
  };

  const handleProfileChange = (key: keyof Profile, value: string) => {
    if (!profile) return;
    setProfile({ ...profile, [key]: value });
  };

  const hasChanges = useMemo(() => {
    if (!profile || !initialProfile) return false;
    return (
      (profile.full_name || '') !== (initialProfile.full_name || '') ||
      (profile.title || '') !== (initialProfile.title || '') ||
      (profile.email || '') !== (initialProfile.email || '') ||
      (profile.phone || '') !== (initialProfile.phone || '') ||
      (profile.location || '') !== (initialProfile.location || '') ||
      (profile.summary || '') !== (initialProfile.summary || '') ||
      (profile.linkedin_url || '') !== (initialProfile.linkedin_url || '') ||
      (profile.github_url || '') !== (initialProfile.github_url || '') ||
      (profile.portfolio_url || '') !== (initialProfile.portfolio_url || '') ||
      (profile.work_authorization || '') !== (initialProfile.work_authorization || '') ||
      (profile.desired_salary || '') !== (initialProfile.desired_salary || '') ||
      (profile.notice_period || '') !== (initialProfile.notice_period || '') ||
      (profile.master_resume_text || '') !== (initialProfile.master_resume_text || '')
    );
  }, [profile, initialProfile]);

  const handleSaveProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!profile || !hasChanges) return;
    setSaving(true);
    try {
      const updated = await api.updateProfile(profile);
      setProfile(updated);
      setInitialProfile(updated);
      setSavedBanner(true);
      setTimeout(() => setSavedBanner(false), 3000);
    } catch (err) {
      console.error('Failed to save profile:', err);
    } finally {
      setSaving(false);
    }
  };

  const handleAddSkill = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newSkillName.trim()) return;

    try {
      const created = await api.addSkill(
        newSkillName.trim(),
        newSkillCategory,
        newSkillProficiency
      );
      setSkills((prev) => [...prev.filter((s) => s.id !== created.id), created]);
      setNewSkillName('');
    } catch (err) {
      console.error('Failed to add skill:', err);
    }
  };

  const handleDeleteSkill = async (id: number) => {
    try {
      await api.deleteSkill(id);
      setSkills((prev) => prev.filter((s) => s.id !== id));
    } catch (err) {
      console.error('Failed to delete skill:', err);
    }
  };

  if (loading) {
    return (
      <div className="py-20 text-center text-slate-400 text-sm">
        Loading candidate profile & skills...
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-extrabold text-white tracking-tight flex items-center space-x-2">
            <UserCheck className="w-6 h-6 text-emerald-400" />
            <span>Master Candidate Profile & Skills</span>
          </h1>
          <p className="text-slate-400 text-xs mt-1">
            This information powers ATS match score calculations, 1-click tailored cover letters, and application autofill.
          </p>
        </div>

        {savedBanner && (
          <div className="flex items-center space-x-1.5 px-3 py-1.5 rounded-xl bg-emerald-950/60 border border-emerald-800/60 text-emerald-400 text-xs font-semibold animate-pulse">
            <Check className="w-4 h-4" />
            <span>Changes Saved!</span>
          </div>
        )}
      </div>

      {/* Multi-Profile Search Criteria & Scraper Directives */}
      <SearchProfilesSection onJobsScored={onJobsScored} />

      {profile && (
        <form onSubmit={handleSaveProfile} className="space-y-8">
          {/* Section 1: Contact & Basics */}
          <div className="bg-slate-800/60 border border-slate-700/60 rounded-2xl p-6 space-y-4">
            <h2 className="text-sm font-bold uppercase tracking-wider text-slate-300">
              1. Contact & Identity
            </h2>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="text-xs font-semibold text-slate-400 block mb-1">Full Name</label>
                <input
                  type="text"
                  value={profile.full_name}
                  onChange={(e) => handleProfileChange('full_name', e.target.value)}
                  className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-xs text-slate-100 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-400 block mb-1">Target Professional Title</label>
                <input
                  type="text"
                  value={profile.title}
                  onChange={(e) => handleProfileChange('title', e.target.value)}
                  className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-xs text-slate-100 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-400 block mb-1">Email Address</label>
                <input
                  type="email"
                  value={profile.email}
                  onChange={(e) => handleProfileChange('email', e.target.value)}
                  className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-xs text-slate-100 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-400 block mb-1">Phone Number</label>
                <input
                  type="tel"
                  value={profile.phone}
                  onChange={(e) => handleProfileChange('phone', e.target.value)}
                  className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-xs text-slate-100 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-400 block mb-1">Location / Residence</label>
                <input
                  type="text"
                  value={profile.location}
                  onChange={(e) => handleProfileChange('location', e.target.value)}
                  className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-xs text-slate-100 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                />
              </div>
            </div>

            {/* Summary */}
            <div className="pt-2">
              <label className="text-xs font-semibold text-slate-400 block mb-1">Executive Summary / Bio</label>
              <textarea
                rows={3}
                value={profile.summary}
                onChange={(e) => handleProfileChange('summary', e.target.value)}
                className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-xs text-slate-100 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              />
            </div>
          </div>

          {/* Section 2: Online Presence & ATS Answers */}
          <div className="bg-slate-800/60 border border-slate-700/60 rounded-2xl p-6 space-y-4">
            <h2 className="text-sm font-bold uppercase tracking-wider text-slate-300">
              2. Links & Standard ATS Application Answers
            </h2>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div>
                <label className="text-xs font-semibold text-slate-400 block mb-1">LinkedIn Profile URL</label>
                <input
                  type="url"
                  value={profile.linkedin_url}
                  onChange={(e) => handleProfileChange('linkedin_url', e.target.value)}
                  className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-xs text-slate-100 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-400 block mb-1">GitHub Profile URL</label>
                <input
                  type="url"
                  value={profile.github_url}
                  onChange={(e) => handleProfileChange('github_url', e.target.value)}
                  className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-xs text-slate-100 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-400 block mb-1">Portfolio / Personal Site</label>
                <input
                  type="url"
                  value={profile.portfolio_url}
                  onChange={(e) => handleProfileChange('portfolio_url', e.target.value)}
                  className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-xs text-slate-100 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-400 block mb-1">Work Authorization</label>
                <input
                  type="text"
                  value={profile.work_authorization}
                  onChange={(e) => handleProfileChange('work_authorization', e.target.value)}
                  className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-xs text-slate-100 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-400 block mb-1">Desired Compensation</label>
                <input
                  type="text"
                  value={profile.desired_salary}
                  onChange={(e) => handleProfileChange('desired_salary', e.target.value)}
                  className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-xs text-slate-100 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-400 block mb-1">Notice Period / Start Date</label>
                <input
                  type="text"
                  value={profile.notice_period}
                  onChange={(e) => handleProfileChange('notice_period', e.target.value)}
                  className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-xs text-slate-100 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                />
              </div>
            </div>
          </div>

          {/* Section 3: Master Skills Inventory */}
          <div className="bg-slate-800/60 border border-slate-700/60 rounded-2xl p-6 space-y-5">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-sm font-bold uppercase tracking-wider text-slate-300">
                  3. Skills Matrix ({skills.length} skills tracked)
                </h2>
                <p className="text-slate-400 text-xs">
                  The ATS matching engine automatically scores jobs by checking against this inventory.
                </p>
              </div>
            </div>

            {/* Add Skill Mini Form */}
            <div className="flex flex-wrap gap-2 items-center bg-slate-900/80 p-3 rounded-xl border border-slate-700/60">
              <input
                type="text"
                placeholder="Add skill (e.g. Kubernetes, GraphQL, Rust)..."
                value={newSkillName}
                onChange={(e) => setNewSkillName(e.target.value)}
                className="flex-1 min-w-[200px] px-3 py-1.5 bg-slate-800 border border-slate-700 rounded-lg text-xs text-slate-100 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              />

              <select
                value={newSkillCategory}
                onChange={(e) => setNewSkillCategory(e.target.value)}
                className="bg-slate-800 border border-slate-700 text-slate-200 text-xs rounded-lg px-2.5 py-1.5 focus:outline-none"
              >
                <option value="languages">Languages</option>
                <option value="frameworks">Frameworks & Libs</option>
                <option value="databases">Databases</option>
                <option value="cloud_devops">Cloud & DevOps</option>
                <option value="architecture">Architecture & Patterns</option>
                <option value="tools">Tools & Platforms</option>
                <option value="soft_skills">Soft Skills</option>
              </select>

              <select
                value={newSkillProficiency}
                onChange={(e) => setNewSkillProficiency(e.target.value as any)}
                className="bg-slate-800 border border-slate-700 text-slate-200 text-xs rounded-lg px-2.5 py-1.5 focus:outline-none"
              >
                <option value="intermediate">Intermediate</option>
                <option value="expert">Expert</option>
                <option value="beginner">Beginner</option>
              </select>

              <button
                type="button"
                onClick={handleAddSkill}
                disabled={!newSkillName.trim()}
                className="px-3.5 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold flex items-center space-x-1 disabled:opacity-50"
              >
                <Plus className="w-3.5 h-3.5" />
                <span>Add Skill</span>
              </button>
            </div>

            {/* Skills Badges */}
            <div className="flex flex-wrap gap-2 pt-1">
              {skills.map((s) => (
                <span
                  key={s.id}
                  className="inline-flex items-center space-x-1.5 px-3 py-1 rounded-xl bg-slate-900 border border-slate-700 text-xs font-medium text-slate-200"
                >
                  <span className="capitalize">{s.name}</span>
                  <span className="text-[10px] text-slate-500 font-mono">({s.proficiency[0].toUpperCase()})</span>
                  <button
                    type="button"
                    onClick={() => handleDeleteSkill(s.id)}
                    className="text-slate-500 hover:text-rose-400 ml-1 transition"
                  >
                    <Trash2 className="w-3 h-3" />
                  </button>
                </span>
              ))}
            </div>
          </div>

          {/* Section 4: Master Resume Text */}
          <div className="bg-slate-800/60 border border-slate-700/60 rounded-2xl p-6 space-y-3">
            <h2 className="text-sm font-bold uppercase tracking-wider text-slate-300 flex items-center space-x-2">
              <FileText className="w-4 h-4 text-emerald-400" />
              <span>4. Master Resume / Work History Text</span>
            </h2>
            <p className="text-xs text-slate-400">
              Paste the text content of your complete resume. The AI Copilot references these achievements to draft tailored cover letters and resume bullets.
            </p>
            <textarea
              rows={6}
              value={profile.master_resume_text}
              onChange={(e) => handleProfileChange('master_resume_text', e.target.value)}
              className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-xs text-slate-200 font-mono leading-relaxed focus:outline-none focus:ring-1 focus:ring-emerald-500"
              placeholder="Paste your resume sections, work experience bullet points, certifications, and educational background here..."
            />
          </div>

          {/* Save Button Bar */}
          <div className="flex justify-end pt-2">
            <button
              type="submit"
              disabled={!hasChanges || saving}
              className={`px-6 py-2.5 rounded-xl font-bold text-sm flex items-center space-x-2 transition ${
                hasChanges && !saving
                  ? 'bg-emerald-600 hover:bg-emerald-500 text-white shadow-lg shadow-emerald-500/20 cursor-pointer'
                  : 'bg-slate-800/80 text-slate-500 border border-slate-700/50 cursor-not-allowed opacity-60 shadow-none'
              }`}
            >
              <Save className={`w-4 h-4 ${hasChanges ? 'text-white' : 'text-slate-500'}`} />
              <span>{saving ? 'Saving Profile...' : 'Save All Changes'}</span>
            </button>
          </div>
        </form>
      )}
    </div>
  );
};
