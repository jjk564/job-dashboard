import React, { useEffect, useState } from 'react';
import { CheckCircle2, ExternalLink, FileText, HelpCircle, Loader2, Send } from 'lucide-react';
import {
  api,
  type ApplicationEntry,
  type ApplicationStatus,
  type PacketEntry,
  type UnansweredQuestion,
} from '../../api/client';

/**
 * hadoku's application runner, in three parts:
 * - the queue: postings handed to the runner ("Queue for Auto-Apply" in a job's
 *   drawer). It fills each form from your packet and stops at `filled` for you
 *   to approve; only an approved form is submitted.
 * - questions a form asked that you have not answered yet. An answer saved here
 *   is reused on every later form that asks the same question.
 * - packets: the tailored résumé + cover letter page minted for each posting.
 */

const STATUS: Record<ApplicationStatus, { label: string; tone: string }> = {
  queued: { label: 'Queued', tone: 'bg-slate-800 text-slate-300 border-slate-700' },
  filled: { label: 'Filled: approve to submit', tone: 'bg-amber-950/60 text-amber-300 border-amber-700/60' },
  approved: { label: 'Approved', tone: 'bg-sky-950/60 text-sky-300 border-sky-700/60' },
  submitted: { label: 'Submitted', tone: 'bg-emerald-950/60 text-emerald-300 border-emerald-700/60' },
  needs_manual: { label: 'Needs you', tone: 'bg-amber-950/60 text-amber-300 border-amber-700/60' },
  failed: { label: 'Failed', tone: 'bg-red-950/60 text-red-300 border-red-800/60' },
  job_closed: { label: 'Posting closed', tone: 'bg-slate-800 text-slate-400 border-slate-700' },
};

const errText = (err: unknown, fallback: string) => (err instanceof Error ? err.message : fallback);

function QuestionRow({ q, onSaved }: { q: UnansweredQuestion; onSaved: () => void }) {
  const [answer, setAnswer] = useState('');
  const [picked, setPicked] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const value = q.options.length > 0 ? picked.join(' | ') : answer.trim();

  const save = async () => {
    if (!value) return;
    setSaving(true);
    setError(null);
    try {
      await api.saveAnswer(q.question, value);
      onSaved();
    } catch (err) {
      setError(errText(err, 'Could not save the answer'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <li className="rounded-xl border border-slate-800 bg-slate-900/60 p-3 space-y-2">
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm text-slate-100">{q.question}</p>
        {q.blocking > 0 && (
          <span className="shrink-0 text-[10px] font-bold px-2 py-0.5 rounded-full border bg-amber-950/60 text-amber-300 border-amber-700/60">
            blocking {q.blocking}
          </span>
        )}
      </div>
      {q.companies.length > 0 && <p className="text-xs text-slate-400">Asked by {q.companies.join(', ')}</p>}
      {q.options.length > 0 ? (
        <div className="flex flex-wrap gap-1.5">
          {q.options.map((opt) => {
            const on = picked.includes(opt);
            return (
              <button
                key={opt}
                type="button"
                onClick={() =>
                  setPicked((prev) =>
                    q.multi ? (on ? prev.filter((p) => p !== opt) : [...prev, opt]) : on ? [] : [opt]
                  )
                }
                className={`px-2.5 py-1 rounded-lg text-xs border transition ${
                  on
                    ? 'bg-emerald-600/20 border-emerald-500/60 text-emerald-300'
                    : 'bg-slate-800 border-slate-700 text-slate-300 hover:text-white'
                }`}
              >
                {opt}
              </button>
            );
          })}
        </div>
      ) : (
        <textarea
          rows={2}
          value={answer}
          onChange={(e) => setAnswer(e.target.value)}
          placeholder="Your answer, reused on every form that asks this"
          className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-xs text-slate-200 focus:outline-none focus:ring-1 focus:ring-emerald-500"
        />
      )}
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => void save()}
          disabled={saving || !value}
          className="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold disabled:opacity-50"
        >
          {saving ? 'Saving…' : 'Save answer'}
        </button>
        {error && <span className="text-xs text-red-300">{error}</span>}
      </div>
    </li>
  );
}

export const ApplicationsTab: React.FC = () => {
  const [apps, setApps] = useState<ApplicationEntry[] | null>(null);
  const [questions, setQuestions] = useState<UnansweredQuestion[]>([]);
  const [packets, setPackets] = useState<PacketEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [approving, setApproving] = useState<string | null>(null);

  const load = async () => {
    setError(null);
    try {
      const [a, q, p] = await Promise.all([api.getApplications(), api.getUnansweredQuestions(), api.getPackets()]);
      setApps(a);
      setQuestions(q);
      setPackets(p);
    } catch (err) {
      setError(errText(err, 'Could not load applications'));
      setApps([]);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const approve = async (id: string) => {
    setApproving(id);
    try {
      await api.approveApplication(id);
      await load();
    } catch (err) {
      setError(errText(err, 'Could not approve'));
    } finally {
      setApproving(null);
    }
  };

  if (apps === null) {
    return (
      <div className="flex items-center justify-center py-16 text-slate-400 text-sm">
        <Loader2 className="w-4 h-4 mr-2 animate-spin" /> Loading applications…
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto p-6 space-y-8" data-testid="applications-tab">
      <header className="space-y-1">
        <h2 className="text-2xl font-bold text-white flex items-center gap-2">
          <Send className="w-6 h-6 text-emerald-400" /> Applications
        </h2>
        <p className="text-sm text-slate-400">
          Postings handed to hadoku's form runner. It fills each form from your packet and waits for your approval
          before anything is submitted. Queue one from a job's drawer.
        </p>
        {error && <p className="text-sm text-red-300">{error}</p>}
      </header>

      <section className="space-y-3">
        <h3 className="text-xs font-bold tracking-wider text-slate-400 uppercase">Queue</h3>
        {apps.length === 0 ? (
          <p className="text-sm text-slate-500">Nothing queued yet.</p>
        ) : (
          <ul className="space-y-2">
            {apps.map((a) => (
              <li
                key={a.id}
                className="rounded-xl border border-slate-800 bg-slate-900/60 p-3 flex flex-wrap items-center justify-between gap-3"
              >
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-slate-100 truncate">{a.title}</p>
                  <p className="text-xs text-slate-400">
                    {a.company}
                    {a.location ? ` · ${a.location}` : ''} · updated {new Date(a.updated_at).toLocaleDateString()}
                  </p>
                  {a.error && <p className="text-xs text-red-300 mt-1">{a.error}</p>}
                  {a.still_unanswered && a.still_unanswered.length > 0 && (
                    <p className="text-xs text-amber-300 mt-1">
                      Waiting on {a.still_unanswered.length} answer{a.still_unanswered.length === 1 ? '' : 's'} below
                    </p>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <span className={`text-[11px] font-bold px-2 py-0.5 rounded-full border ${STATUS[a.status]?.tone ?? ''}`}>
                    {STATUS[a.status]?.label ?? a.status}
                  </span>
                  <a
                    href={a.form_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs text-slate-300 hover:text-white inline-flex items-center gap-1"
                  >
                    Form <ExternalLink className="w-3 h-3" />
                  </a>
                  {a.status === 'filled' && (
                    <button
                      type="button"
                      onClick={() => void approve(a.id)}
                      disabled={approving === a.id}
                      className="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold inline-flex items-center gap-1 disabled:opacity-50"
                    >
                      <CheckCircle2 className="w-3.5 h-3.5" />
                      {approving === a.id ? 'Approving…' : 'Approve'}
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="space-y-3">
        <h3 className="text-xs font-bold tracking-wider text-slate-400 uppercase flex items-center gap-1.5">
          <HelpCircle className="w-3.5 h-3.5" /> Questions waiting for an answer
        </h3>
        {questions.length === 0 ? (
          <p className="text-sm text-slate-500">None: every question the runner met has an answer.</p>
        ) : (
          <ul className="space-y-2">
            {questions.map((q) => (
              <QuestionRow key={q.question_key} q={q} onSaved={() => void load()} />
            ))}
          </ul>
        )}
      </section>

      <section className="space-y-3">
        <h3 className="text-xs font-bold tracking-wider text-slate-400 uppercase flex items-center gap-1.5">
          <FileText className="w-3.5 h-3.5" /> Packets
        </h3>
        {packets.length === 0 ? (
          <p className="text-sm text-slate-500">No packets yet. A job's drawer makes one.</p>
        ) : (
          <ul className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {packets.map((p) => (
              <li key={`${p.job_id}-${p.variant_slug}`} className="rounded-xl border border-slate-800 bg-slate-900/60 p-3">
                <p className="text-sm font-semibold text-slate-100 truncate">{p.title}</p>
                <p className="text-xs text-slate-400">{p.company}</p>
                <div className="mt-2 flex gap-3 text-xs">
                  <a
                    href={`https://hadoku.me/resume?v=${encodeURIComponent(p.variant_slug)}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-emerald-300 hover:text-emerald-200 inline-flex items-center gap-1"
                  >
                    Open packet <ExternalLink className="w-3 h-3" />
                  </a>
                  <a
                    href={`https://hadoku.me/resume/api/resume.pdf?v=${encodeURIComponent(p.variant_slug)}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-slate-300 hover:text-white"
                  >
                    PDF
                  </a>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <p className="text-xs text-slate-500">
        To fill a form yourself instead, the hadoku Fill extension fills Greenhouse, Lever and Ashby forms from your
        profile in your own browser; get it from{' '}
        <a href="https://hadoku.me/jobplatform/#/applications" className="text-emerald-300 hover:text-emerald-200">
          Job Platform → Applications
        </a>
        .
      </p>
    </div>
  );
};
