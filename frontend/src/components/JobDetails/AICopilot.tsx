import React, { useState } from 'react';
import { 
  Sparkles, 
  Copy, 
  Check, 
  Send, 
  FileText, 
  Globe, 
  RefreshCw, 
  ExternalLink,
  Bot,
  HelpCircle
} from 'lucide-react';
import { Job, FitBreakdown, AutofillPayload } from '../../types';
import { api } from '../../api/client';

interface AICopilotProps {
  job: Job;
  onJobUpdated: (updated: Job) => void;
}

export const AICopilot: React.FC<AICopilotProps> = ({ job, onJobUpdated }) => {
  const [activeTab, setActiveTab] = useState<'match' | 'generate' | 'autofill'>('match');
  const [docType, setDocType] = useState<'tailored_resume' | 'cover_letter' | 'application_kit' | 'resume_bullets' | 'pitch'>('tailored_resume');
  const [tone, setTone] = useState<'professional' | 'confident' | 'concise'>('professional');
  const [customInstructions, setCustomInstructions] = useState('');
  
  const [generating, setGenerating] = useState(false);
  const [generatedContent, setGeneratedContent] = useState<string>('');
  const [providerUsed, setProviderUsed] = useState<string>('');

  const [mintingPacket, setMintingPacket] = useState(false);
  const [mintedPacket, setMintedPacket] = useState<{ slug: string; url: string; pdf_url: string } | null>(null);
  const [packetError, setPacketError] = useState<string | null>(null);

  const [analyzingMatch, setAnalyzingMatch] = useState(false);
  const [matchData, setMatchData] = useState<FitBreakdown | undefined>(job.fit_breakdown);

  const [autofillData, setAutofillData] = useState<AutofillPayload | null>(null);
  const [loadingAutofill, setLoadingAutofill] = useState(false);
  const [loadingKit, setLoadingKit] = useState(false);
  const [appKit, setAppKit] = useState<{
    provider_used: string;
    why_hook: string;
    intro_email: string;
    linkedin_note: string;
    salary_line: string;
    talking_points: string[];
    screening_answers: { q: string; a: string }[];
  } | null>(null);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  const [launchingBrowser, setLaunchingBrowser] = useState(false);
  const [browserMessage, setBrowserMessage] = useState<string | null>(null);

  // Copy helper
  const copyToClipboard = (text: string, key: string) => {
    navigator.clipboard.writeText(text);
    setCopiedKey(key);
    setTimeout(() => setCopiedKey(null), 2000);
  };

  // Re-run match analysis
  const handleAnalyzeMatch = async () => {
    setAnalyzingMatch(true);
    try {
      const result = await api.analyzeJobMatch(job.id);
      setMatchData(result);
      const updatedJob = await api.getJob(job.id);
      onJobUpdated(updatedJob);
    } catch (err) {
      console.error('Match analysis failed:', err);
    } finally {
      setAnalyzingMatch(false);
    }
  };

  // Generate Document
  const handleGenerateDocument = async () => {
    setGenerating(true);
    try {
      const res = await api.generateDocument(
        job.id,
        docType,
        tone,
        customInstructions || undefined,
        'hadoku'
      );
      setGeneratedContent(res.content);
      setProviderUsed(res.provider_used);
      const updatedJob = await api.getJob(job.id);
      onJobUpdated(updatedJob);
    } catch (err) {
      console.error('Generation failed:', err);
    } finally {
      setGenerating(false);
    }
  };

  // Mint Shareable Hadoku Resume Packet
  const handleMintPacket = async () => {
    setMintingPacket(true);
    setPacketError(null);
    try {
      const packet = await api.mintResumePacket(job.id);
      setMintedPacket(packet);
      const updatedJob = await api.getJob(job.id);
      onJobUpdated(updatedJob);
    } catch (err: any) {
      setPacketError(err.message || 'Failed to mint shareable packet.');
    } finally {
      setMintingPacket(false);
    }
  };

  // Load Autofill Payload
  const loadAutofill = async () => {
    setLoadingAutofill(true);
    try {
      const data = await api.getAutofillPayload(job.id);
      setAutofillData(data);
    } catch (err) {
      console.error('Autofill load failed:', err);
    } finally {
      setLoadingAutofill(false);
    }
  };

  // Load Hadoku Screening Answers & Application Kit
  const handleLoadApplicationKit = async () => {
    setLoadingKit(true);
    try {
      const kit = await api.generateApplicationKit(job.id);
      setAppKit(kit);
    } catch (err) {
      console.error('Application kit load failed:', err);
    } finally {
      setLoadingKit(false);
    }
  };

  // Launch Assisted Browser
  const handleLaunchBrowser = async () => {
    setLaunchingBrowser(true);
    setBrowserMessage(null);
    try {
      const res = await api.launchBrowserAssistant(job.id);
      setBrowserMessage(res.message);
    } catch (err: any) {
      setBrowserMessage(err.message || 'Failed to start browser assistant.');
    } finally {
      setLaunchingBrowser(false);
    }
  };

  return (
    <div className="flex flex-col h-full bg-slate-900 border-l border-slate-800">
      {/* Sub-navigation tabs */}
      <div className="flex border-b border-slate-800 bg-slate-950/40 p-1">
        <button
          onClick={() => setActiveTab('match')}
          className={`flex-1 py-2 text-xs font-semibold rounded-lg flex items-center justify-center space-x-1.5 transition ${
            activeTab === 'match'
              ? 'bg-slate-800 text-emerald-400 shadow-xs'
              : 'text-slate-400 hover:text-white'
          }`}
        >
          <Sparkles className="w-3.5 h-3.5" />
          <span>ATS Match ({job.fit_score || 0}%)</span>
        </button>

        <button
          onClick={() => setActiveTab('generate')}
          className={`flex-1 py-2 text-xs font-semibold rounded-lg flex items-center justify-center space-x-1.5 transition ${
            activeTab === 'generate'
              ? 'bg-slate-800 text-emerald-400 shadow-xs'
              : 'text-slate-400 hover:text-white'
          }`}
        >
          <FileText className="w-3.5 h-3.5" />
          <span>AI Generator</span>
        </button>

        <button
          onClick={() => {
            setActiveTab('autofill');
            if (!autofillData) loadAutofill();
          }}
          className={`flex-1 py-2 text-xs font-semibold rounded-lg flex items-center justify-center space-x-1.5 transition ${
            activeTab === 'autofill'
              ? 'bg-slate-800 text-emerald-400 shadow-xs'
              : 'text-slate-400 hover:text-white'
          }`}
        >
          <Bot className="w-3.5 h-3.5" />
          <span>Autofill Copilot</span>
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-5 space-y-5">
        {/* TAB 1: ATS MATCH */}
        {activeTab === 'match' && (
          <div className="space-y-5">
            {/* Score Card */}
            <div className="bg-slate-800/70 rounded-2xl p-4 border border-slate-700/60 flex items-center justify-between">
              <div>
                <span className="text-xs font-medium text-slate-400">Calculated ATS Fit</span>
                <div className="flex items-baseline space-x-2">
                  <span className="text-3xl font-extrabold text-white">
                    {matchData?.score ?? job.fit_score ?? '--'}%
                  </span>
                  <span className="text-xs text-emerald-400 font-medium">Match</span>
                </div>
                <p className="text-xs text-slate-400 mt-1 max-w-xs">
                  {matchData?.summary || "Analyzed against your profile's master skills & resume summary."}
                </p>
              </div>

              <button
                onClick={handleAnalyzeMatch}
                disabled={analyzingMatch}
                className="flex items-center space-x-1 px-3 py-2 rounded-xl bg-slate-700 hover:bg-slate-600 text-white text-xs font-semibold border border-slate-600 transition disabled:opacity-50"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${analyzingMatch ? 'animate-spin' : ''}`} />
                <span>Re-Score</span>
              </button>
            </div>

            {/* Matched Skills */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wider text-emerald-400 flex items-center space-x-1">
                  <Check className="w-3.5 h-3.5" />
                  <span>Matched Skills ({matchData?.matched_skills?.length || 0})</span>
                </span>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {(matchData?.matched_skills && matchData.matched_skills.length > 0) ? (
                  matchData.matched_skills.map((skill) => (
                    <span
                      key={skill}
                      className="text-xs px-2.5 py-1 rounded-lg bg-emerald-950/40 border border-emerald-800/60 text-emerald-300 font-medium capitalize"
                    >
                      {skill}
                    </span>
                  ))
                ) : (
                  <span className="text-xs text-slate-500 italic">No exact matches isolated yet.</span>
                )}
              </div>
            </div>

            {/* Missing Skills */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wider text-rose-400 flex items-center space-x-1">
                  <span>Missing Requirements ({matchData?.missing_skills?.length || 0})</span>
                </span>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {(matchData?.missing_skills && matchData.missing_skills.length > 0) ? (
                  matchData.missing_skills.map((skill) => (
                    <span
                      key={skill}
                      className="text-xs px-2.5 py-1 rounded-lg bg-rose-950/30 border border-rose-800/40 text-rose-300 font-medium capitalize"
                    >
                      {skill}
                    </span>
                  ))
                ) : (
                  <span className="text-xs text-emerald-400/80">No missing technical skills identified!</span>
                )}
              </div>
            </div>

            {/* Tips Banner */}
            <div className="bg-slate-950/50 rounded-xl p-3.5 border border-slate-800 text-xs text-slate-400 space-y-1.5">
              <div className="font-semibold text-slate-300 flex items-center space-x-1">
                <Sparkles className="w-3.5 h-3.5 text-amber-400" />
                <span>Optimization Tip</span>
              </div>
              <p>
                To boost your fit score, ensure your profile's skills list includes any technologies you know that are flagged under "Missing Requirements".
              </p>
            </div>
          </div>
        )}

        {/* TAB 2: AI GENERATOR */}
        {activeTab === 'generate' && (
          <div className="space-y-4">
            {/* Document Controls */}
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
              {[
                { id: 'tailored_resume', label: 'Tailored Resume' },
                { id: 'cover_letter', label: 'Cover Letter' },
                { id: 'application_kit', label: 'Full Apply Kit' },
                { id: 'resume_bullets', label: 'Talking Points' },
                { id: 'pitch', label: 'Intro Pitch' },
              ].map((item) => (
                <button
                  key={item.id}
                  onClick={() => setDocType(item.id as any)}
                  className={`py-2 px-2 text-xs font-semibold rounded-xl border text-center transition ${
                    docType === item.id
                      ? 'bg-emerald-600/20 border-emerald-500/60 text-emerald-300'
                      : 'bg-slate-800 border-slate-700 text-slate-400 hover:text-white'
                  }`}
                >
                  {item.label}
                </button>
              ))}
            </div>

            {/* Tone Selector */}
            <div className="flex items-center space-x-2 text-xs">
              <span className="text-slate-400 font-medium">Tone:</span>
              {(['professional', 'confident', 'concise'] as const).map((t) => (
                <button
                  key={t}
                  onClick={() => setTone(t)}
                  className={`px-2.5 py-1 rounded-lg capitalize font-medium transition ${
                    tone === t
                      ? 'bg-slate-700 text-white font-semibold'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  {t}
                </button>
              ))}
            </div>

            {/* Custom Instructions */}
            <div>
              <label className="text-xs text-slate-400 block mb-1">
                Custom Instructions or Focus (Optional):
              </label>
              <input
                type="text"
                placeholder="e.g. Highlight Python performance tuning and AWS migration..."
                value={customInstructions}
                onChange={(e) => setCustomInstructions(e.target.value)}
                className="w-full px-3 py-1.5 bg-slate-800 border border-slate-700 rounded-lg text-xs text-slate-200 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              />
            </div>

            {/* Generate Trigger + Mint Hadoku Shareable Packet */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              <button
                onClick={handleGenerateDocument}
                disabled={generating}
                className="py-2.5 px-3 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-500 hover:from-emerald-500 hover:to-teal-400 text-white text-xs font-bold shadow-lg shadow-emerald-500/20 flex items-center justify-center space-x-1.5 transition disabled:opacity-50"
              >
                <Sparkles className={`w-3.5 h-3.5 ${generating ? 'animate-spin' : ''}`} />
                <span>{generating ? 'Drafting via Hadoku...' : 'Generate Document'}</span>
              </button>

              <button
                onClick={handleMintPacket}
                disabled={mintingPacket}
                className="py-2.5 px-3 rounded-xl bg-slate-800 hover:bg-slate-700 border border-emerald-500/40 text-emerald-300 text-xs font-bold flex items-center justify-center space-x-1.5 transition disabled:opacity-50"
                title="Mints a shareable packet link (hadoku.me/resume?v=...) and downloadable PDF"
              >
                <Send className={`w-3.5 h-3.5 ${mintingPacket ? 'animate-pulse' : ''}`} />
                <span>{mintingPacket ? 'Minting Packet...' : 'Mint Packet + PDF Link'}</span>
              </button>
            </div>

            {packetError && (
              <div className="text-xs p-2.5 rounded-xl bg-rose-950/40 border border-rose-800/60 text-rose-300">
                {packetError}
              </div>
            )}

            {mintedPacket && (
              <div className="p-3 rounded-xl bg-emerald-950/40 border border-emerald-700/60 space-y-2 text-xs">
                <div className="flex items-center justify-between">
                  <span className="font-bold text-emerald-300">
                    Minted Hadoku Packet (`{mintedPacket.slug}`)
                  </span>
                  <button
                    onClick={() => copyToClipboard(mintedPacket.url, 'packet_url')}
                    className="text-emerald-400 hover:text-emerald-200 flex items-center space-x-1 font-semibold"
                  >
                    {copiedKey === 'packet_url' ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                    <span>{copiedKey === 'packet_url' ? 'Copied' : 'Copy Link'}</span>
                  </button>
                </div>
                <div className="flex flex-wrap items-center gap-3 pt-1">
                  <a
                    href={mintedPacket.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center space-x-1 text-emerald-300 hover:underline font-medium"
                  >
                    <ExternalLink className="w-3.5 h-3.5" />
                    <span>Open Web Packet</span>
                  </a>
                  <a
                    href={mintedPacket.pdf_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center space-x-1 text-emerald-300 hover:underline font-medium"
                  >
                    <FileText className="w-3.5 h-3.5" />
                    <span>Download Server PDF</span>
                  </a>
                </div>
              </div>
            )}

            {/* Generated Output */}
            {generatedContent && (
              <div className="space-y-2 pt-2 border-t border-slate-800">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium text-slate-400">
                    Generated Output ({providerUsed})
                  </span>
                  <button
                    onClick={() => copyToClipboard(generatedContent, 'doc')}
                    className="flex items-center space-x-1 px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-emerald-400 border border-slate-700 text-xs font-semibold transition"
                  >
                    {copiedKey === 'doc' ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                    <span>{copiedKey === 'doc' ? 'Copied!' : 'Copy Markdown'}</span>
                  </button>
                </div>

                <div className="bg-slate-950/80 rounded-xl p-4 border border-slate-800 text-xs text-slate-300 font-mono leading-relaxed whitespace-pre-wrap max-h-72 overflow-y-auto">
                  {generatedContent}
                </div>
              </div>
            )}
          </div>
        )}

        {/* TAB 3: AUTOFILL COPILOT */}
        {activeTab === 'autofill' && (
          <div className="space-y-5">
            {/* Assisted Browser Banner */}
            <div className="bg-gradient-to-br from-emerald-950/40 to-slate-900 border border-emerald-800/40 rounded-2xl p-4 space-y-3">
              <div className="flex items-start justify-between">
                <div>
                  <h4 className="font-bold text-sm text-emerald-400 flex items-center space-x-1.5">
                    <Globe className="w-4 h-4" />
                    <span>Assisted Browser Pre-Fill</span>
                  </h4>
                  <p className="text-xs text-slate-400 mt-1">
                    Opens a browser session to automatically fill standard fields on Greenhouse, Lever, or Ashby.
                  </p>
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                <button
                  onClick={handleLaunchBrowser}
                  disabled={launchingBrowser || !job.url}
                  className="py-2 px-3 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold flex items-center justify-center space-x-1.5 transition disabled:opacity-50"
                >
                  <ExternalLink className="w-3.5 h-3.5" />
                  <span>{launchingBrowser ? 'Launching Session...' : 'Open with Auto-Fill'}</span>
                </button>

                <button
                  onClick={handleLoadApplicationKit}
                  disabled={loadingKit}
                  className="py-2 px-3 rounded-xl bg-slate-800 hover:bg-slate-700 border border-emerald-500/40 text-emerald-300 text-xs font-bold flex items-center justify-center space-x-1.5 transition disabled:opacity-50"
                >
                  <Sparkles className={`w-3.5 h-3.5 ${loadingKit ? 'animate-spin' : ''}`} />
                  <span>{loadingKit ? 'Drafting Answers...' : 'Draft Screening Answers'}</span>
                </button>
              </div>

              {browserMessage && (
                <div className="text-xs p-2 rounded bg-slate-900 text-slate-300 border border-slate-700">
                  {browserMessage}
                </div>
              )}
            </div>

            {/* Hadoku Drafted Screening Answers & Hooks */}
            {appKit && (
              <div className="space-y-2.5 p-3.5 rounded-2xl bg-slate-950/60 border border-slate-800">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold uppercase tracking-wider text-emerald-400">
                    Tailored Screening Answers ({appKit.provider_used})
                  </span>
                  <span className="text-[11px] text-slate-500">Click any card to copy</span>
                </div>

                {[
                  { label: `Why ${job.company}? Hook`, val: appKit.why_hook, key: 'kit_why' },
                  { label: 'LinkedIn Note (≤300 chars)', val: appKit.linkedin_note, key: 'kit_li' },
                  { label: 'Expected Compensation Line', val: appKit.salary_line, key: 'kit_sal' },
                  { label: 'Recruiter Intro Email', val: appKit.intro_email, key: 'kit_email' },
                ]
                  .filter((item) => item.val)
                  .map((item) => (
                    <button
                      key={item.key}
                      onClick={() => copyToClipboard(item.val, item.key)}
                      className="w-full text-left p-2.5 bg-slate-900 hover:bg-slate-800/90 rounded-xl border border-slate-800 hover:border-emerald-500/50 transition flex items-start justify-between gap-2"
                    >
                      <div className="space-y-0.5">
                        <span className="text-[10px] uppercase font-bold text-emerald-400 block">
                          {item.label}
                        </span>
                        <span className="text-xs text-slate-200 leading-relaxed block">
                          {item.val}
                        </span>
                      </div>
                      <span className="shrink-0 text-slate-400 mt-1">
                        {copiedKey === item.key ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                      </span>
                    </button>
                  ))}

                {appKit.screening_answers?.map((qa, idx) => (
                  <button
                    key={idx}
                    onClick={() => copyToClipboard(qa.a, `qa_${idx}`)}
                    className="w-full text-left p-2.5 bg-slate-900 hover:bg-slate-800/90 rounded-xl border border-slate-800 hover:border-emerald-500/50 transition flex items-start justify-between gap-2"
                  >
                    <div className="space-y-0.5">
                      <span className="text-[10px] font-bold text-slate-400 block">{qa.q}</span>
                      <span className="text-xs text-slate-200 leading-relaxed block">{qa.a}</span>
                    </div>
                    <span className="shrink-0 text-slate-400 mt-1">
                      {copiedKey === `qa_${idx}` ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                    </span>
                  </button>
                ))}
              </div>
            )}

            {/* Quick-Copy Clipboard Palette */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold uppercase tracking-wider text-slate-300">
                  1-Click Clipboard Palette
                </span>
                <span className="text-[11px] text-slate-500">Click any field to copy</span>
              </div>

              {loadingAutofill ? (
                <div className="text-xs text-slate-400 py-4 text-center">Loading answers...</div>
              ) : autofillData ? (
                <div className="grid grid-cols-1 gap-2">
                  {[
                    { label: 'Full Name', val: autofillData.full_name, key: 'name' },
                    { label: 'Email', val: autofillData.email, key: 'email' },
                    { label: 'Phone', val: autofillData.phone, key: 'phone' },
                    { label: 'Location', val: autofillData.location, key: 'loc' },
                    { label: 'LinkedIn', val: autofillData.linkedin_url, key: 'li' },
                    { label: 'GitHub', val: autofillData.github_url, key: 'gh' },
                    { label: 'Portfolio', val: autofillData.portfolio_url, key: 'port' },
                    { label: 'Work Auth', val: autofillData.work_authorization, key: 'auth' },
                    { label: 'Desired Salary', val: autofillData.desired_salary, key: 'sal' },
                    { label: 'Notice Period', val: autofillData.notice_period, key: 'notice' },
                  ].map((field) => (
                    <button
                      key={field.key}
                      onClick={() => copyToClipboard(field.val, field.key)}
                      className="flex items-center justify-between p-2.5 bg-slate-800/80 hover:bg-slate-800 rounded-xl border border-slate-700/60 hover:border-emerald-500/50 transition group text-left"
                    >
                      <div className="truncate pr-2">
                        <span className="text-[10px] uppercase font-bold text-slate-400 block">
                          {field.label}
                        </span>
                        <span className="text-xs text-slate-200 font-medium truncate block">
                          {field.val || '<empty>'}
                        </span>
                      </div>

                      <div className="shrink-0 text-slate-400 group-hover:text-emerald-400">
                        {copiedKey === field.key ? (
                          <Check className="w-4 h-4 text-emerald-400" />
                        ) : (
                          <Copy className="w-4 h-4" />
                        )}
                      </div>
                    </button>
                  ))}
                </div>
              ) : (
                <button
                  onClick={loadAutofill}
                  className="text-xs text-emerald-400 hover:underline"
                >
                  Load Candidate Answers
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
