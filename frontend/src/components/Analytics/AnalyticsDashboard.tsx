import React, { useState, useEffect } from 'react';
import { 
  BarChart3, 
  TrendingUp, 
  Send, 
  MessageSquare, 
  Award, 
  Layers, 
  Globe, 
  Sparkles,
  PieChart
} from 'lucide-react';
import { Metrics } from '../../types';
import { api } from '../../api/client';

export const AnalyticsDashboard: React.FC = () => {
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadMetrics();
    const onReload = () => {
      loadMetrics(true);
    };
    window.addEventListener('jobpulse:backend-reloaded', onReload);
    return () => window.removeEventListener('jobpulse:backend-reloaded', onReload);
  }, []);

  const loadMetrics = async (silent: boolean = false) => {
    if (!silent) setLoading(true);
    try {
      const data = await api.getMetrics();
      setMetrics(data);
    } catch (err) {
      console.error('Failed to load metrics:', err);
    } finally {
      if (!silent) setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="py-20 text-center text-slate-400 text-sm">
        Loading analytics metrics...
      </div>
    );
  }

  if (!metrics) return null;

  const { funnel, top_demanded_skills, workplace_distribution } = metrics;

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-extrabold text-white tracking-tight flex items-center space-x-2">
          <BarChart3 className="w-6 h-6 text-emerald-400" />
          <span>Application Analytics & Skills Intelligence</span>
        </h1>
        <p className="text-slate-400 text-xs mt-1">
          Monitor your job search pipeline performance, interview conversion rates, and the most demanded skills in your target jobs.
        </p>
      </div>

      {/* Funnel Metrics Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
        {[
          { label: 'Total Tracked', val: funnel.total_tracked, color: 'text-white', icon: Layers },
          { label: 'To Apply', val: (funnel.to_apply || 0) + (funnel.wishlist || 0), color: 'text-blue-400', icon: Layers },
          { label: 'Applications Sent', val: funnel.applied, color: 'text-amber-400', icon: Send },
          { label: 'Interview Rounds', val: funnel.interviewing, color: 'text-cyan-400', icon: MessageSquare },
          { label: 'Offers Received', val: funnel.offer, color: 'text-emerald-400', icon: Award },
          { label: 'Interview Rate', val: `${funnel.interview_rate_percent}%`, color: 'text-teal-400', icon: TrendingUp },
        ].map((stat, idx) => {
          const Icon = stat.icon;
          return (
            <div
              key={idx}
              className="bg-slate-800/70 border border-slate-700/60 rounded-2xl p-4 flex flex-col justify-between shadow-sm"
            >
              <div className="flex items-center justify-between text-slate-400 text-xs">
                <span>{stat.label}</span>
                <Icon className="w-3.5 h-3.5 text-slate-500" />
              </div>
              <div className={`text-2xl font-black mt-2 ${stat.color}`}>
                {stat.val}
              </div>
            </div>
          );
        })}
      </div>

      {/* Two Column Section: Skills In-Demand & Workplace Distribution */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Most Demanded Skills */}
        <div className="lg:col-span-8 bg-slate-800/60 border border-slate-700/60 rounded-2xl p-6 space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-sm font-bold uppercase tracking-wider text-slate-200 flex items-center space-x-2">
                <Sparkles className="w-4 h-4 text-emerald-400" />
                <span>Top Demanded Skills Across Your Tracked Jobs</span>
              </h2>
              <p className="text-xs text-slate-400 mt-0.5">
                Identifies which frameworks and tools employers in your pipeline mention most.
              </p>
            </div>
          </div>

          {top_demanded_skills.length === 0 ? (
            <p className="text-xs text-slate-500 py-6 text-center">
              Add jobs with descriptions to your pipeline to see skill demand trends.
            </p>
          ) : (
            <div className="space-y-3 pt-2">
              {top_demanded_skills.map((skill) => {
                const maxCount = top_demanded_skills[0]?.count || 1;
                const percentage = Math.round((skill.count / maxCount) * 100);

                return (
                  <div key={skill.name} className="space-y-1">
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-semibold text-slate-300 capitalize">{skill.name}</span>
                      <span className="text-slate-400 font-mono text-[11px]">
                        {skill.count} {skill.count === 1 ? 'job' : 'jobs'}
                      </span>
                    </div>
                    <div className="w-full bg-slate-900 rounded-full h-2 overflow-hidden border border-slate-700/40">
                      <div
                        className="bg-gradient-to-r from-emerald-500 to-teal-400 h-2 rounded-full transition-all duration-500"
                        style={{ width: `${percentage}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Workplace Distribution */}
        <div className="lg:col-span-4 bg-slate-800/60 border border-slate-700/60 rounded-2xl p-6 space-y-4">
          <h2 className="text-sm font-bold uppercase tracking-wider text-slate-200 flex items-center space-x-2">
            <Globe className="w-4 h-4 text-emerald-400" />
            <span>Workplace Distribution</span>
          </h2>
          <p className="text-xs text-slate-400">
            Breakdown of remote vs. hybrid vs. onsite roles in your pipeline.
          </p>

          <div className="space-y-3 pt-2">
            {Object.entries(workplace_distribution).length === 0 ? (
              <p className="text-xs text-slate-500 py-6 text-center">No jobs tracked yet.</p>
            ) : (
              Object.entries(workplace_distribution).map(([type, count]) => (
                <div
                  key={type}
                  className="flex items-center justify-between p-3 rounded-xl bg-slate-900 border border-slate-700/60"
                >
                  <span className="text-xs font-semibold uppercase text-slate-300 tracking-wider font-mono">
                    {type}
                  </span>
                  <span className="text-xs font-bold text-emerald-400 px-2 py-0.5 rounded-full bg-emerald-950/40 border border-emerald-800/40">
                    {count}
                  </span>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
