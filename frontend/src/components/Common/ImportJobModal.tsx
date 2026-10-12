import React, { useState } from 'react';
import { 
  X, 
  Link2, 
  Sparkles, 
  Building2, 
  Check, 
  DollarSign, 
  MapPin, 
  ArrowRight,
  AlertCircle 
} from 'lucide-react';
import { Job } from '../../types';
import { api } from '../../api/client';

interface ImportJobModalProps {
  isOpen: boolean;
  onClose: () => void;
  onJobAdded: (job: Job) => void;
}

export const ImportJobModal: React.FC<ImportJobModalProps> = ({
  isOpen,
  onClose,
  onJobAdded,
}) => {
  if (!isOpen) return null;

  const [url, setUrl] = useState('');
  const [scraping, setScraping] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [extractedData, setExtractedData] = useState<Partial<Job> | null>(null);
  const [saving, setSaving] = useState(false);

  const handleScrape = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!url.trim()) return;

    setScraping(true);
    setError(null);
    try {
      const data = await api.importJobUrl(url.trim());
      setExtractedData(data);
    } catch (err: any) {
      setError(err.message || 'Failed to extract job from this link. Make sure the URL is public.');
    } finally {
      setScraping(false);
    }
  };

  const handleConfirmAdd = async () => {
    if (!extractedData) return;
    setSaving(true);
    try {
      const created = await api.createJob({
        ...extractedData,
        status: 'WISHLIST',
      });
      onJobAdded(created);
      onClose();
      setUrl('');
      setExtractedData(null);
    } catch (err: any) {
      setError(err.message || 'Failed to save job');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-fadeIn">
      <div className="bg-slate-900 border border-slate-800 rounded-3xl w-full max-w-xl overflow-hidden shadow-2xl space-y-5 p-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2.5">
            <div className="w-9 h-9 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400">
              <Link2 className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-bold text-slate-100 text-base">Import Job from URL</h3>
              <p className="text-xs text-slate-400">Supports Greenhouse, Lever, Ashby, or general job web pages</p>
            </div>
          </div>

          <button onClick={onClose} className="p-1.5 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Input Form */}
        <form onSubmit={handleScrape} className="space-y-3">
          <div className="flex gap-2">
            <input
              type="url"
              required
              placeholder="Paste job link (e.g. https://boards.greenhouse.io/...)..."
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              className="flex-1 px-4 py-2.5 bg-slate-800 border border-slate-700 rounded-xl text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-emerald-500/50"
            />
            <button
              type="submit"
              disabled={scraping || !url.trim()}
              className="px-4 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs flex items-center space-x-1.5 transition disabled:opacity-50"
            >
              <Sparkles className={`w-3.5 h-3.5 ${scraping ? 'animate-spin' : ''}`} />
              <span>{scraping ? 'Extracting...' : 'Fetch Job'}</span>
            </button>
          </div>

          {error && (
            <div className="p-3 rounded-xl bg-rose-950/40 border border-rose-800/40 text-xs text-rose-300 flex items-center space-x-2">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}
        </form>

        {/* Extracted Preview */}
        {extractedData && (
          <div className="space-y-4 pt-3 border-t border-slate-800 animate-fadeIn">
            <span className="text-xs font-bold uppercase tracking-wider text-emerald-400 flex items-center space-x-1">
              <Check className="w-4 h-4" />
              <span>Successfully Extracted Job Details</span>
            </span>

            <div className="bg-slate-800/70 p-4 rounded-2xl border border-slate-700/60 space-y-3">
              <div>
                <span className="text-xs text-slate-400 font-medium">{extractedData.company}</span>
                <h4 className="font-bold text-slate-100 text-sm">{extractedData.title}</h4>
              </div>

              <div className="flex flex-wrap gap-2 text-xs">
                {extractedData.location && (
                  <span className="inline-flex items-center space-x-1 text-slate-300 bg-slate-900/60 px-2 py-0.5 rounded border border-slate-700/50">
                    <MapPin className="w-3 h-3 text-slate-400" />
                    <span>{extractedData.location}</span>
                  </span>
                )}

                {extractedData.salary_min && (
                  <span className="inline-flex items-center space-x-1 text-emerald-400 bg-emerald-950/40 px-2 py-0.5 rounded border border-emerald-800/40 font-medium">
                    <DollarSign className="w-3 h-3" />
                    <span>${Math.round(extractedData.salary_min / 1000)}k+</span>
                  </span>
                )}
              </div>

              {extractedData.description && (
                <p className="text-xs text-slate-400 line-clamp-3">
                  {extractedData.description}
                </p>
              )}
            </div>

            <button
              onClick={handleConfirmAdd}
              disabled={saving}
              className="w-full py-2.5 px-4 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs shadow-md transition flex items-center justify-center space-x-2 disabled:opacity-50"
            >
              <span>{saving ? 'Adding to Pipeline...' : 'Add to Pipeline (Wishlist)'}</span>
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        )}
      </div>
    </div>
  );
};
