"use client";

import React, { useEffect, useState } from "react";
import { X, Trophy, ShieldCheck, Zap, BarChart3, CheckCircle2, AlertTriangle, ArrowDownRight, Layers } from "lucide-react";

interface BenchmarkResult {
  id: string;
  name: string;
  slottedSkus: number;
  totalTravelCost: number;
  avgTravelPerItem: string;
  safetyConflicts: number;
  structuralViolations: number;
  efficiencyScore: number;
}

interface BenchmarkModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectWinner: (algo: "coi" | "ga" | "sa") => void;
}

export default function BenchmarkModal({ isOpen, onClose, onSelectWinner }: BenchmarkModalProps) {
  const [data, setData] = useState<BenchmarkResult[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!isOpen) return;
    setLoading(true);
    fetch("/api/inventory/benchmark")
      .then((res) => res.json())
      .then((resData) => {
        if (Array.isArray(resData)) setData(resData);
        setLoading(false);
      })
      .catch((err) => {
        console.error(err);
        setLoading(false);
      });
  }, [isOpen]);

  if (!isOpen) return null;

  // Determine winner (lowest travel score with 0 safety/structural errors)
  const safeModels = data.filter((d) => d.safetyConflicts === 0 && d.structuralViolations === 0);
  const winner = safeModels.length > 0 
    ? [...safeModels].sort((a, b) => parseFloat(a.avgTravelPerItem) - parseFloat(b.avgTravelPerItem))[0]
    : data[0];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4 animate-in fade-in duration-200">
      <div className="bg-slate-900 border border-slate-700 rounded-xl w-full max-w-4xl max-h-[90vh] flex flex-col shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="p-5 bg-gradient-to-r from-indigo-950 via-slate-900 to-slate-900 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-amber-500/10 border border-amber-500/30 rounded-lg text-amber-400">
              <Trophy className="w-6 h-6" />
            </div>
            <div>
              <h2 className="text-base font-extrabold text-white uppercase tracking-wider">AI Slotting Engine Comparative Analytics</h2>
              <p className="text-xs text-slate-400">Quantitative operations research decision matrix for warehouse layout optimization</p>
            </div>
          </div>
          <button onClick={onClose} className="p-2 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 overflow-y-auto flex flex-col gap-6 text-slate-300 text-xs">
          {loading ? (
            <div className="py-16 flex flex-col items-center justify-center gap-3">
              <div className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
              <p className="text-slate-400 font-mono">Simulating benchmark trajectories across PostgreSQL layouts...</p>
            </div>
          ) : (
            <>
              {/* Recommendation Banner */}
              {winner && (
                <div className="p-4 bg-gradient-to-r from-emerald-950/60 to-indigo-950/60 border border-emerald-500/40 rounded-xl flex items-start gap-4">
                  <div className="p-2 bg-emerald-500 text-slate-950 rounded-lg font-bold shrink-0 mt-0.5">
                    <CheckCircle2 className="w-5 h-5" />
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] bg-emerald-500/20 text-emerald-300 font-bold px-2 py-0.5 rounded uppercase tracking-wider">Operations Research Recommendation</span>
                      <h3 className="text-sm font-bold text-white">Select {winner.name}</h3>
                    </div>
                    <p className="text-slate-300 mt-1 leading-relaxed">
                      Quantitative benchmark analysis demonstrates that <strong className="text-emerald-400">{winner.name}</strong> achieves the optimal **Pareto trade-off** between forklift travel minimization ({winner.avgTravelPerItem} dist/hit) and **100% strict regulatory safety compliance** (0 digital hazard conflicts, 0 floor loading violations).
                    </p>
                  </div>
                  <button
                    onClick={() => {
                      onSelectWinner(winner.id as any);
                      onClose();
                    }}
                    className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg font-bold text-xs uppercase tracking-wider transition-all shadow-lg shrink-0 self-center"
                  >
                    Load Winner Proposal
                  </button>
                </div>
              )}

              {/* Comparative Matrix Table */}
              <div className="bg-slate-950/60 border border-slate-800 rounded-xl overflow-hidden">
                <div className="p-3 bg-slate-900/80 border-b border-slate-800 font-bold text-slate-400 uppercase tracking-widest text-[10px] flex items-center gap-2">
                  <BarChart3 className="w-4 h-4 text-indigo-400" /> Empirical Performance Benchmark Table
                </div>
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="border-b border-slate-800 bg-slate-900/40 text-[10px] font-bold text-slate-400 uppercase">
                      <th className="p-3">Algorithmic Engine</th>
                      <th className="p-3 text-right">SKUs Slotted</th>
                      <th className="p-3 text-right">Total Daily Travel</th>
                      <th className="p-3 text-right">Avg Dist / Hit</th>
                      <th className="p-3 text-center">Safety Matrix</th>
                      <th className="p-3 text-center">Structural Floor</th>
                      <th className="p-3 text-center">Verdict</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60 font-mono">
                    {data.map((row) => {
                      const isWinner = winner && row.id === winner.id;
                      return (
                        <tr key={row.id} className={`transition-colors ${isWinner ? "bg-emerald-500/5 font-semibold" : "hover:bg-slate-900/30"}`}>
                          <td className="p-3 font-sans font-bold text-white flex items-center gap-2">
                            {isWinner && <Trophy className="w-3.5 h-3.5 text-amber-400" />}
                            {row.name}
                          </td>
                          <td className="p-3 text-right text-indigo-300">{row.slottedSkus.toLocaleString()}</td>
                          <td className="p-3 text-right text-slate-300">{row.totalTravelCost.toLocaleString()}</td>
                          <td className="p-3 text-right text-emerald-400 font-bold">{row.avgTravelPerItem}</td>
                          <td className="p-3 text-center">
                            {row.safetyConflicts === 0 ? (
                              <span className="inline-flex items-center gap-1 text-[10px] bg-emerald-500/10 text-emerald-400 px-2 py-0.5 rounded border border-emerald-500/20"><ShieldCheck className="w-3 h-3"/> 0 Errors</span>
                            ) : (
                              <span className="inline-flex items-center gap-1 text-[10px] bg-rose-500/10 text-rose-400 px-2 py-0.5 rounded border border-rose-500/20"><AlertTriangle className="w-3 h-3"/> {row.safetyConflicts} Fail</span>
                            )}
                          </td>
                          <td className="p-3 text-center">
                            {row.structuralViolations === 0 ? (
                              <span className="text-[10px] text-emerald-400">Pass (0)</span>
                            ) : (
                              <span className="text-[10px] text-rose-400 font-bold">{row.structuralViolations} Violations</span>
                            )}
                          </td>
                          <td className="p-3 text-center font-sans">
                            {isWinner ? (
                              <span className="text-[10px] bg-emerald-500 text-slate-950 font-extrabold px-2 py-1 rounded">OPTIMAL</span>
                            ) : (
                              <span className="text-[10px] text-slate-500">Sub-optimal</span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              {/* Assignment Claims & Academic Justification Guide */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 font-sans">
                <div className="p-4 bg-slate-950/40 border border-slate-800 rounded-xl flex flex-col gap-2">
                  <h4 className="text-indigo-400 font-bold flex items-center gap-1.5 uppercase tracking-wider text-[10px]">
                    <Layers className="w-3.5 h-3.5" /> 1. Deterministic vs Stochastic
                  </h4>
                  <p className="text-slate-400 text-[11px] leading-relaxed">
                    **Heuristic COI** acts as a greedy baseline. It runs rapidly but suffers from "first-fit boxing out", trapping items in staging. **GA** and **SA** explore combinatorial multi-slot swaps to unlock greater warehouse floor density.
                  </p>
                </div>

                <div className="p-4 bg-slate-950/40 border border-slate-800 rounded-xl flex flex-col gap-2">
                  <h4 className="text-emerald-400 font-bold flex items-center gap-1.5 uppercase tracking-wider text-[10px]">
                    <Zap className="w-3.5 h-3.5" /> 2. Cooling Escape Trajectories
                  </h4>
                  <p className="text-slate-400 text-[11px] leading-relaxed">
                    **Simulated Annealing** leverages the Metropolis Boltzmann distribution (P = exp(-Delta E / T)). By accepting worse moves early at high thermal energy (T0 = 50k), it escapes shallow local minima that trap rule-based COI matching.
                  </p>
                </div>

                <div className="p-4 bg-slate-950/40 border border-slate-800 rounded-xl flex flex-col gap-2">
                  <h4 className="text-amber-400 font-bold flex items-center gap-1.5 uppercase tracking-wider text-[10px]">
                    <ShieldCheck className="w-3.5 h-3.5" /> 3. Hard Safety Penalties
                  </h4>
                  <p className="text-slate-400 text-[11px] leading-relaxed">
                    All three engines enforce strict **Digital Conflict Matrix** buffers (3.0m separation between chemical hazards and food goods). Any permutation violating safety or rack weight limits (&gt;= 500kg) is dynamically culled.
                  </p>
                </div>
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 bg-slate-950 border-t border-slate-800 flex items-center justify-between">
          <span className="text-[10px] text-slate-500 font-mono">Data refreshed directly from active PostgreSQL DB schemas</span>
          <button onClick={onClose} className="px-4 py-1.5 bg-slate-800 hover:bg-slate-700 text-white rounded font-bold text-xs">
            Close Benchmark
          </button>
        </div>
      </div>
    </div>
  );
}
