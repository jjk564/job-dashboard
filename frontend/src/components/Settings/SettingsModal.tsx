import React, { useState, useEffect } from 'react';
import { X, Settings, Sparkles, Check, Key, Shield } from 'lucide-react';

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const SettingsModal: React.FC<SettingsModalProps> = ({ isOpen, onClose }) => {
  if (!isOpen) return null;

  const [aiProvider, setAiProvider] = useState<string>('template');
  const [apiKey, setApiKey] = useState<string>('');
  const [adzunaAppId, setAdzunaAppId] = useState<string>('');
  const [adzunaAppKey, setAdzunaAppKey] = useState<string>('');
  const [savedBanner, setSavedBanner] = useState(false);

  useEffect(() => {
    const savedProvider = localStorage.getItem('job_pulse_ai_provider') || 'template';
    const savedKey = localStorage.getItem('job_pulse_api_key') || '';
    const savedAdzunaId = localStorage.getItem('job_pulse_adzuna_app_id') || '';
    const savedAdzunaKey = localStorage.getItem('job_pulse_adzuna_app_key') || '';
    setAiProvider(savedProvider);
    setApiKey(savedKey);
    setAdzunaAppId(savedAdzunaId);
    setAdzunaAppKey(savedAdzunaKey);
  }, []);

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    localStorage.setItem('job_pulse_ai_provider', aiProvider);
    localStorage.setItem('job_pulse_api_key', apiKey);
    localStorage.setItem('job_pulse_adzuna_app_id', adzunaAppId);
    localStorage.setItem('job_pulse_adzuna_app_key', adzunaAppKey);
    setSavedBanner(true);
    setTimeout(() => {
      setSavedBanner(false);
      onClose();
    }, 1200);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-fadeIn">
      <div className="bg-slate-900 border border-slate-800 rounded-3xl w-full max-w-lg overflow-hidden shadow-2xl p-6 space-y-5">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2.5">
            <div className="w-9 h-9 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400">
              <Settings className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-bold text-slate-100 text-base">Dashboard Settings</h3>
              <p className="text-xs text-slate-400">Configure AI tailoring engine and privacy preferences</p>
            </div>
          </div>

          <button onClick={onClose} className="p-1.5 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <form onSubmit={handleSave} className="space-y-4">
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
                Your key is stored only in your local browser storage and never transmitted to third parties.
              </p>
            </div>
          )}

          {/* Adzuna API for Indeed / ZipRecruiter aggregator */}
          <div className="space-y-2 pt-2 border-t border-slate-800">
            <div className="flex items-center justify-between">
              <label className="text-xs font-bold uppercase tracking-wider text-slate-300">
                Adzuna API (Indeed & ZipRecruiter Aggregator)
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
              Enables live searches across millions of jobs indexed from Indeed, ZipRecruiter, and company career sites.
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
      </div>
    </div>
  );
};
