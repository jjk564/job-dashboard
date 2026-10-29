import React, { useState, useEffect } from 'react';
import {
  Sliders,
  Plus,
  Trash2,
  Star,
  Edit3,
  Check,
  X,
  RefreshCw,
  Building2,
  Tag,
  MapPin,
  Layers,
} from 'lucide-react';
import { SearchProfile, RoleLevel, IcLevel, ManagerLevel, Job } from '../../types';
import { api } from '../../api/client';

const IC_LEVEL_OPTIONS: { value: IcLevel; label: string }[] = [
  { value: 'junior', label: 'Junior / New Grad' },
  { value: 'mid', label: 'Mid-Level (II/III)' },
  { value: 'senior', label: 'Senior' },
  { value: 'staff', label: 'Staff' },
  { value: 'principal', label: 'Principal' },
  { value: 'fellow', label: 'Distinguished / Fellow' },
];

const MANAGER_LEVEL_OPTIONS: { value: ManagerLevel; label: string }[] = [
  { value: 'manager', label: 'Engineering Manager' },
  { value: 'senior_manager', label: 'Sr. / Group Manager' },
  { value: 'director', label: 'Director' },
  { value: 'vp', label: 'VP / Head of' },
  { value: 'cxo', label: 'C-Level (CTO/CIO)' },
];

interface SearchProfilesSectionProps {
  onJobsScored?: (jobs: Job[]) => void;
}

export const SearchProfilesSection: React.FC<SearchProfilesSectionProps> = ({ onJobsScored }) => {
  const [profiles, setProfiles] = useState<SearchProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingProfile, setEditingProfile] = useState<Partial<SearchProfile> | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [scoringProfileId, setScoringProfileId] = useState<number | null>(null);
  const [statusBanner, setStatusBanner] = useState<string | null>(null);

  // Chip inputs inside modal/editor
  const [keywordInput, setKeywordInput] = useState('');
  const [companyInput, setCompanyInput] = useState('');

  useEffect(() => {
    loadProfiles();
  }, []);

  const loadProfiles = async () => {
    try {
      setLoading(true);
      const data = await api.getSearchProfiles();
      setProfiles(data);
    } catch (err) {
      console.error('Failed to load search profiles:', err);
    } finally {
      setLoading(false);
    }
  };

  const showStatus = (msg: string) => {
    setStatusBanner(msg);
    setTimeout(() => setStatusBanner(null), 3500);
  };

  const openCreateModal = () => {
    setIsCreating(true);
    setEditingProfile({
      name: '',
      is_default: profiles.length === 0,
      keywords: [],
      target_companies: [],
      track: 'ic',
      levels: ['mid', 'senior'],
      remote_pref: 'any',
      location: '',
      radius_miles: 50,
      min_salary: null,
      include_undisclosed_salary: true,
      us_only: true,
    });
    setKeywordInput('');
    setCompanyInput('');
  };

  const openEditModal = (sp: SearchProfile) => {
    setIsCreating(false);
    setEditingProfile({ ...sp });
    setKeywordInput('');
    setCompanyInput('');
  };

  const toggleLevel = (lvl: RoleLevel) => {
    if (!editingProfile) return;
    const current = editingProfile.levels || [];
    const next = current.includes(lvl)
      ? current.filter((l) => l !== lvl)
      : [...current, lvl];
    setEditingProfile({ ...editingProfile, levels: next });
  };

  const addKeyword = () => {
    if (!editingProfile || !keywordInput.trim()) return;
    const parts = keywordInput
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean);
    const existing = new Set((editingProfile.keywords || []).map((k) => k.toLowerCase()));
    const merged = [...(editingProfile.keywords || [])];
    for (const p of parts) {
      if (!existing.has(p.toLowerCase())) {
        existing.add(p.toLowerCase());
        merged.push(p);
      }
    }
    setEditingProfile({ ...editingProfile, keywords: merged });
    setKeywordInput('');
  };

  const removeKeyword = (kw: string) => {
    if (!editingProfile) return;
    setEditingProfile({
      ...editingProfile,
      keywords: (editingProfile.keywords || []).filter((k) => k !== kw),
    });
  };

  const addCompany = () => {
    if (!editingProfile || !companyInput.trim()) return;
    const parts = companyInput
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean);
    const existing = new Set((editingProfile.target_companies || []).map((c) => c.toLowerCase()));
    const merged = [...(editingProfile.target_companies || [])];
    for (const p of parts) {
      if (!existing.has(p.toLowerCase())) {
        existing.add(p.toLowerCase());
        merged.push(p);
      }
    }
    setEditingProfile({ ...editingProfile, target_companies: merged });
    setCompanyInput('');
  };

  const removeCompany = (comp: string) => {
    if (!editingProfile) return;
    setEditingProfile({
      ...editingProfile,
      target_companies: (editingProfile.target_companies || []).filter((c) => c !== comp),
    });
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingProfile || !editingProfile.name?.trim()) return;

    try {
      if (isCreating) {
        const created = await api.createSearchProfile({
          name: editingProfile.name.trim(),
          is_default: Boolean(editingProfile.is_default),
          keywords: editingProfile.keywords || [],
          target_companies: editingProfile.target_companies || [],
          track: editingProfile.track || 'ic',
          levels: editingProfile.levels || [],
          remote_pref: editingProfile.remote_pref || 'any',
          location: editingProfile.location || '',
          radius_miles: editingProfile.radius_miles ?? 50,
          min_salary: editingProfile.min_salary ?? null,
          include_undisclosed_salary: editingProfile.include_undisclosed_salary ?? true,
          us_only: editingProfile.us_only ?? true,
        });
        await loadProfiles();
        showStatus(`Created search profile "${created.name}"`);
      } else if (editingProfile.id) {
        const updated = await api.updateSearchProfile(editingProfile.id, editingProfile);
        await loadProfiles();
        showStatus(`Updated search profile "${updated.name}"`);
      }
      setEditingProfile(null);
    } catch (err) {
      console.error('Failed to save search profile:', err);
    }
  };

  const handleSetDefault = async (sp: SearchProfile) => {
    try {
      await api.updateSearchProfile(sp.id, { is_default: true });
      await loadProfiles();
      showStatus(`Set "${sp.name}" as active default profile`);
    } catch (err) {
      console.error('Failed to set default profile:', err);
    }
  };

  const handleDelete = async (sp: SearchProfile) => {
    if (profiles.length <= 1) return;
    try {
      await api.deleteSearchProfile(sp.id);
      await loadProfiles();
      showStatus(`Deleted profile "${sp.name}"`);
    } catch (err) {
      console.error('Failed to delete search profile:', err);
    }
  };

  const handleScorePipeline = async (sp: SearchProfile) => {
    try {
      setScoringProfileId(sp.id);
      const res = await api.scorePipelineWithProfile(sp.id);
      if (onJobsScored) {
        onJobsScored(res.jobs);
      }
      showStatus(`Re-scored ${res.jobs_scored} pipeline jobs against "${sp.name}"`);
    } catch (err) {
      console.error('Failed to score pipeline:', err);
    } finally {
      setScoringProfileId(null);
    }
  };

  return (
    <div className="bg-slate-800/60 border border-slate-700/60 rounded-2xl p-6 space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-bold uppercase tracking-wider text-slate-200 flex items-center space-x-2">
            <Sliders className="w-4 h-4 text-emerald-400" />
            <span>Role Search Profiles & Scraper Directives</span>
          </h2>
          <p className="text-slate-400 text-xs mt-0.5">
            Define multiple role criteria profiles (orthogonal IC vs. Manager track, seniority ladder rungs, target companies, keywords & geo radius).
          </p>
        </div>

        <div className="flex items-center space-x-2">
          {statusBanner && (
            <span className="px-3 py-1 rounded-lg bg-emerald-950/80 border border-emerald-500/40 text-emerald-300 text-xs font-medium flex items-center space-x-1.5">
              <Check className="w-3.5 h-3.5" />
              <span>{statusBanner}</span>
            </span>
          )}
          <button
            type="button"
            onClick={openCreateModal}
            className="px-3.5 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold flex items-center space-x-1.5 shadow-sm transition"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>New Search Profile</span>
          </button>
        </div>
      </div>

      {loading ? (
        <div className="py-6 text-center text-slate-400 text-xs">Loading search profiles...</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {profiles.map((sp) => (
            <div
              key={sp.id}
              className={`rounded-xl p-4 border transition flex flex-col justify-between space-y-3 ${
                sp.is_default
                  ? 'bg-slate-900/90 border-emerald-500/50 shadow-sm'
                  : 'bg-slate-900/60 border-slate-700/70'
              }`}
            >
              <div className="space-y-2.5">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center space-x-2">
                    <span className="font-bold text-sm text-slate-100">{sp.name}</span>
                    {sp.is_default && (
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
                        Default
                      </span>
                    )}
                  </div>
                  <div className="flex items-center space-x-1">
                    {!sp.is_default && (
                      <button
                        type="button"
                        onClick={() => handleSetDefault(sp)}
                        title="Set as Default Profile"
                        className="p-1.5 rounded-lg text-slate-400 hover:text-amber-400 hover:bg-slate-800 transition"
                      >
                        <Star className="w-3.5 h-3.5" />
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => openEditModal(sp)}
                      title="Edit Profile Criteria"
                      className="p-1.5 rounded-lg text-slate-400 hover:text-slate-100 hover:bg-slate-800 transition"
                    >
                      <Edit3 className="w-3.5 h-3.5" />
                    </button>
                    {profiles.length > 1 && (
                      <button
                        type="button"
                        onClick={() => handleDelete(sp)}
                        title="Delete Profile"
                        className="p-1.5 rounded-lg text-slate-400 hover:text-rose-400 hover:bg-slate-800 transition"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    )}
                  </div>
                </div>

                {/* Track, Levels & Workplace */}
                <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
                  <span className="px-2 py-0.5 rounded-md bg-slate-800 border border-slate-700 text-emerald-300 font-semibold uppercase">
                    Track: {sp.track === 'ic' ? 'IC (No Reports)' : sp.track === 'manager' ? 'Manager' : 'Either'}
                  </span>
                  <span className="px-2 py-0.5 rounded-md bg-slate-800 border border-slate-700 text-slate-300 capitalize">
                    Workplace: {sp.remote_pref}
                  </span>
                  {sp.levels.length > 0 && (
                    <span className="px-2 py-0.5 rounded-md bg-slate-800 border border-slate-700 text-slate-300">
                      Levels: {sp.levels.join(', ')}
                    </span>
                  )}
                  {sp.location && (
                    <span className="px-2 py-0.5 rounded-md bg-slate-800 border border-slate-700 text-slate-300 flex items-center gap-1">
                      <MapPin className="w-3 h-3 text-emerald-400" />
                      {sp.location} ({sp.radius_miles}mi)
                    </span>
                  )}
                </div>

                {/* Keywords */}
                {sp.keywords.length > 0 && (
                  <div className="flex flex-wrap gap-1 pt-0.5">
                    {sp.keywords.slice(0, 8).map((kw) => (
                      <span
                        key={kw}
                        className="px-2 py-0.5 rounded-md bg-slate-800/80 text-slate-300 text-[11px] border border-slate-700/60"
                      >
                        {kw}
                      </span>
                    ))}
                    {sp.keywords.length > 8 && (
                      <span className="text-[11px] text-slate-400 px-1">
                        +{sp.keywords.length - 8} more
                      </span>
                    )}
                  </div>
                )}

                {/* Target Companies */}
                {sp.target_companies.length > 0 && (
                  <div className="text-[11px] text-slate-400 flex items-center gap-1.5">
                    <Building2 className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                    <span className="truncate">
                      Targets: {sp.target_companies.join(', ')}
                    </span>
                  </div>
                )}
              </div>

              <div className="pt-2 border-t border-slate-800 flex items-center justify-between">
                <span className="text-[11px] text-slate-400">
                  {sp.keywords.length} keywords · {sp.target_companies.length} companies
                </span>
                <button
                  type="button"
                  onClick={() => handleScorePipeline(sp)}
                  disabled={scoringProfileId === sp.id}
                  className="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-emerald-400 text-xs font-semibold flex items-center space-x-1.5 transition disabled:opacity-50"
                >
                  <RefreshCw className={`w-3 h-3 ${scoringProfileId === sp.id ? 'animate-spin' : ''}`} />
                  <span>{scoringProfileId === sp.id ? 'Scoring...' : 'Re-Score Pipeline'}</span>
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Full-Screen / Dimmed Profile Editor Modal */}
      {editingProfile && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-sm p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-2xl w-full max-h-[90vh] overflow-y-auto p-6 space-y-5 shadow-lg">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center space-x-2">
                <Layers className="w-5 h-5 text-emerald-400" />
                <h3 className="text-base font-bold text-slate-100">
                  {isCreating ? 'Create Role Search Profile' : `Edit Profile: ${editingProfile.name}`}
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setEditingProfile(null)}
                className="p-1.5 rounded-lg text-slate-400 hover:text-slate-100 hover:bg-slate-800"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleSave} className="space-y-4">
              {/* Name & Default */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 items-end">
                <div className="sm:col-span-2">
                  <label className="text-xs font-semibold text-slate-300 block mb-1">
                    Profile Name
                  </label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. Senior Backend SWE (IC) or IT & Cloud Ops"
                    value={editingProfile.name || ''}
                    onChange={(e) => setEditingProfile({ ...editingProfile, name: e.target.value })}
                    className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-xl text-xs text-slate-100 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                  />
                </div>
                <label className="flex items-center space-x-2 text-xs text-slate-300 pb-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={Boolean(editingProfile.is_default)}
                    onChange={(e) =>
                      setEditingProfile({ ...editingProfile, is_default: e.target.checked })
                    }
                    className="rounded border-slate-700 bg-slate-800 text-emerald-500"
                  />
                  <span>Active Default Profile</span>
                </label>
              </div>

              {/* Orthogonal Track & Workplace */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="text-xs font-semibold text-slate-300 block mb-1">
                    Role Track (Hard Filter)
                  </label>
                  <select
                    value={editingProfile.track || 'ic'}
                    onChange={(e) =>
                      setEditingProfile({
                        ...editingProfile,
                        track: e.target.value as 'ic' | 'manager' | 'either',
                      })
                    }
                    className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-xl text-xs text-slate-100 focus:outline-none"
                  >
                    <option value="ic">Individual Contributor (IC — No Direct Reports)</option>
                    <option value="manager">People Manager (Manager / Director / VP)</option>
                    <option value="either">Either Track (IC or Manager)</option>
                  </select>
                </div>

                <div>
                  <label className="text-xs font-semibold text-slate-300 block mb-1">
                    Workplace Preference
                  </label>
                  <select
                    value={editingProfile.remote_pref || 'any'}
                    onChange={(e) =>
                      setEditingProfile({
                        ...editingProfile,
                        remote_pref: e.target.value as 'remote' | 'hybrid' | 'onsite' | 'any',
                      })
                    }
                    className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-xl text-xs text-slate-100 focus:outline-none"
                  >
                    <option value="any">Any (Remote, Hybrid, or Onsite)</option>
                    <option value="remote">Remote Preferred</option>
                    <option value="hybrid">Hybrid Preferred</option>
                    <option value="onsite">Onsite Preferred</option>
                  </select>
                </div>
              </div>

              {/* Target Seniority Ladder Rungs */}
              <div>
                <label className="text-xs font-semibold text-slate-300 block mb-1.5">
                  Target Seniority Ladder Rungs (Scored by Rung Distance)
                </label>
                <div className="flex flex-wrap gap-1.5">
                  {(editingProfile.track === 'manager'
                    ? MANAGER_LEVEL_OPTIONS
                    : editingProfile.track === 'either'
                    ? [...IC_LEVEL_OPTIONS, ...MANAGER_LEVEL_OPTIONS]
                    : IC_LEVEL_OPTIONS
                  ).map((opt) => {
                    const active = (editingProfile.levels || []).includes(opt.value);
                    return (
                      <button
                        key={opt.value}
                        type="button"
                        onClick={() => toggleLevel(opt.value)}
                        className={`px-2.5 py-1 rounded-lg text-xs font-medium border transition ${
                          active
                            ? 'bg-emerald-600 text-white border-emerald-500'
                            : 'bg-slate-800 text-slate-300 border-slate-700 hover:bg-slate-700'
                        }`}
                      >
                        {opt.label}
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Location, Radius & Salary */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div>
                  <label className="text-xs font-semibold text-slate-300 block mb-1">
                    Preferred City / State
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. Raleigh, NC"
                    value={editingProfile.location || ''}
                    onChange={(e) =>
                      setEditingProfile({ ...editingProfile, location: e.target.value })
                    }
                    className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-xl text-xs text-slate-100 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="text-xs font-semibold text-slate-300 block mb-1">
                    Radius (Miles)
                  </label>
                  <input
                    type="number"
                    min={5}
                    max={500}
                    value={editingProfile.radius_miles ?? 50}
                    onChange={(e) =>
                      setEditingProfile({
                        ...editingProfile,
                        radius_miles: parseInt(e.target.value, 10) || 50,
                      })
                    }
                    className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-xl text-xs text-slate-100 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="text-xs font-semibold text-slate-300 block mb-1">
                    Salary Floor (USD)
                  </label>
                  <input
                    type="number"
                    placeholder="Optional e.g. 90000"
                    value={editingProfile.min_salary ?? ''}
                    onChange={(e) =>
                      setEditingProfile({
                        ...editingProfile,
                        min_salary: e.target.value ? parseFloat(e.target.value) : null,
                      })
                    }
                    className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-xl text-xs text-slate-100 focus:outline-none"
                  />
                </div>
              </div>

              {/* Keywords Chip Input */}
              <div>
                <label className="text-xs font-semibold text-slate-300 flex items-center gap-1.5 mb-1">
                  <Tag className="w-3.5 h-3.5 text-emerald-400" />
                  <span>Target Keywords & Technologies (Fed to Scraper & Scorer)</span>
                </label>
                <div className="flex gap-2 mb-2">
                  <input
                    type="text"
                    placeholder="Add comma-separated keywords (e.g. Python, Go, Kubernetes, Active Directory)..."
                    value={keywordInput}
                    onChange={(e) => setKeywordInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault();
                        addKeyword();
                      }
                    }}
                    className="flex-1 px-3 py-1.5 bg-slate-800 border border-slate-700 rounded-xl text-xs text-slate-100 focus:outline-none"
                  />
                  <button
                    type="button"
                    onClick={addKeyword}
                    className="px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 text-emerald-400 text-xs font-bold"
                  >
                    Add
                  </button>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {(editingProfile.keywords || []).map((kw) => (
                    <span
                      key={kw}
                      className="inline-flex items-center space-x-1 px-2.5 py-1 rounded-lg bg-slate-800 border border-slate-700 text-xs text-slate-200"
                    >
                      <span>{kw}</span>
                      <button
                        type="button"
                        onClick={() => removeKeyword(kw)}
                        className="text-slate-400 hover:text-rose-400"
                      >
                        <X className="w-3 h-3" />
                      </button>
                    </span>
                  ))}
                </div>
              </div>

              {/* Target Companies Chip Input */}
              <div>
                <label className="text-xs font-semibold text-slate-300 flex items-center gap-1.5 mb-1">
                  <Building2 className="w-3.5 h-3.5 text-emerald-400" />
                  <span>Target Companies / ATS Slugs (Optional)</span>
                </label>
                <div className="flex gap-2 mb-2">
                  <input
                    type="text"
                    placeholder="Add companies (e.g. Stripe, Cloudflare, Anthropic, Linear)..."
                    value={companyInput}
                    onChange={(e) => setCompanyInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault();
                        addCompany();
                      }
                    }}
                    className="flex-1 px-3 py-1.5 bg-slate-800 border border-slate-700 rounded-xl text-xs text-slate-100 focus:outline-none"
                  />
                  <button
                    type="button"
                    onClick={addCompany}
                    className="px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 text-emerald-400 text-xs font-bold"
                  >
                    Add
                  </button>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {(editingProfile.target_companies || []).map((comp) => (
                    <span
                      key={comp}
                      className="inline-flex items-center space-x-1 px-2.5 py-1 rounded-lg bg-slate-800 border border-slate-700 text-xs text-slate-200"
                    >
                      <span>{comp}</span>
                      <button
                        type="button"
                        onClick={() => removeCompany(comp)}
                        className="text-slate-400 hover:text-rose-400"
                      >
                        <X className="w-3 h-3" />
                      </button>
                    </span>
                  ))}
                </div>
              </div>

              <div className="flex justify-end space-x-2 pt-3 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setEditingProfile(null)}
                  className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold shadow-sm"
                >
                  {isCreating ? 'Create Profile' : 'Save Profile'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
