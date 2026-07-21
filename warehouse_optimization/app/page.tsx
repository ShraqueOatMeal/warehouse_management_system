"use client";

import { useState, useMemo, useEffect } from "react";
import { Canvas } from "@react-three/fiber";
import { OrbitControls, Box, Edges, Html } from "@react-three/drei";
import { AlertTriangle, CheckCircle, Package, Zap } from "lucide-react";
import BenchmarkModal from "../components/BenchmarkModal";

// --- TYPES ---
type Category =
  | "Hazardous"
  | "Food-Grade"
  | "General / Other"
  | "Chemical"
  | "Electronics"
  | "Ambient"
  | "Packaging Material";
type Pallet = {
  id: string;
  name: string;
  category: Category;
  height: number;
  status: "queue" | "slotted";
  isManual?: boolean;
  isNew?: boolean;
};
type Bin = {
  id: string;
  locationCode: string;
  prefix: string;
  x: number;
  z: number;
  level: number;
  clearance: number;
  occupant: Pallet | null;
  hasConflict: boolean;
  depth: "Front" | "Back";
};

// --- MOCK INBOUND DATA ---
const INBOUND_LOAD: Pallet[] = [
  { id: "AHU05", name: "CYBER WALL UNIT 380KW", category: "Electronics", height: 1.8, status: "queue" },
  { id: "333250", name: "NETWORK SWITCH", category: "Electronics", height: 0.5, status: "queue" },
  { id: "JT/0333_BOTTLE", name: "BOTTLE", category: "General / Other", height: 1.0, status: "queue" },
  { id: "4724984", name: "TARO & SWEET POTATO BALLS", category: "Food-Grade", height: 1.1, status: "queue" },
  { id: "RED DATES MANTOU", name: "RED DATES MANTOU", category: "Food-Grade", height: 0.9, status: "queue" },
  { id: "COO_PC319_DRUM_190KG", name: "FEELZ PC 319", category: "Chemical", height: 1.2, status: "queue" },
];

const COLORS: Record<string, string> = {
  Hazardous: "#f59e0b",
  "Food-Grade": "#22c55e",
  "General / Other": "#3b82f6",
  "Packaging Material": "#94a3b8",
  Wasted: "#ef4444",
  Chemical: "#8b5cf6",
  Electronics: "#ec4899",
  Ambient: "#64748b",
};

const ZONES = {
  inside: ["Y", "A", "B", "C", "D", "E", "F", "G", "H", "LGF"],
  outside: ["D1", "C1", "B1", "A1"],
  coldroom_hdl: ["FA", "FB", "FC", "FD"],
  coldroom_mix: ["FE", "FF", "FG", "FH"],
};

// --- DRAWING-BASED LAYOUT GENERATOR ---
const generateBinsFromDrawings = (): Bin[] => {
  const bins: Bin[] = [];
  const addBins = (aisles: string[], xOff: number, areas: number, xGap: number, zone: string) => {
    aisles.forEach((prefix, aIdx) => {
      const isColdRoom = ["FA", "FB", "FC", "FD", "FE", "FF", "FG", "FH"].includes(prefix);
      for (let area = 1; area <= areas; area++) {
        const areaStr = area.toString().padStart(2, "0");
        for (let level = 1; level <= 5; level++) {
          // Front Slot
          bins.push({
            id: `${prefix}-${areaStr}-${level}`,
            locationCode: `${prefix}-${areaStr}-${level * 10}`,
            prefix,
            x: xOff + aIdx * xGap,
            z: area * 1.5 - 15,
            level: level - 1,
            clearance: 1.6,
            occupant: null,
            hasConflict: false,
            depth: "Front",
          });

          // Double Deep Back Slot
          if (isColdRoom) {
            bins.push({
              id: `${prefix}-${areaStr}-${level}-B`,
              locationCode: `${prefix}-${areaStr}-${level * 10}-B`,
              prefix,
              x: xOff + aIdx * xGap + 1.2, // Offset for back pallet
              z: area * 1.5 - 15,
              level: level - 1,
              clearance: 1.6,
              occupant: null,
              hasConflict: false,
              depth: "Back",
            });
          }
        }
      }
    });
  };

  addBins(["FE", "FF", "FG", "FH"], -20, 20, 5, "COLD_ROOM_MIX");
  addBins(["FA", "FB", "FC", "FD"], -50, 20, 5, "COLD_ROOM_HDL");
  addBins(["D1", "C1", "B1", "A1"], 5, 22, 6, "OUTSIDE");

  let currentX = 5;
  ["Y", "A", "B", "C", "D", "E", "F", "G", "H", "LGF"].forEach((prefix) => {
    for (let area = 1; area <= 22; area++) {
      const areaStr = area.toString().padStart(2, "0");
      for (let level = 1; level <= 5; level++) {
        bins.push({
          id: `${prefix}-${areaStr}-${level}`,
          locationCode: `${prefix}-${areaStr}-${level * 10}`,
          prefix,
          x: currentX,
          z: area * 1.5 - 15,
          level: level - 1,
          clearance: 1.6,
          occupant: null,
          hasConflict: false,
          depth: "Front",
        });
      }
    }
    currentX += prefix === "A" || prefix === "Y" || prefix === "LGF" ? 12 : 6;
  });
  return bins;
};

export default function DSSDigitalTwin() {
  const [mode, setMode] = useState<"manual" | "optimized">("manual");
  const [activeTab, setActiveTab] = useState<"inside" | "outside" | "coldroom_hdl" | "coldroom_mix">("outside");
  const [queue, setQueue] = useState<Pallet[]>([]); 
  const [selectedPallet, setSelectedPallet] = useState<Pallet | null>(null);
  const [bins, setBins] = useState<Bin[]>([]);
  const [isSyncing, setIsSyncing] = useState(false);
  const [newStockInput, setNewStockInput] = useState("");
  const [recommendations, setRecommendations] = useState<Record<string, string[]>>({});
  const [stagedPlacements, setStagedPlacements] = useState<any[]>([]);
  const [globalTotal, setGlobalTotal] = useState(0);
  const [realityStockList, setRealityStockList] = useState<any[]>([]);
  const [changelog, setChangelog] = useState<{ id: string; name: string; oldLocation?: string; newLocation: string; type: "NEW" | "MOVED" }[]>([]);
  const [selectedAlgorithm, setSelectedAlgorithm] = useState<"coi" | "ga" | "sa">("coi");
  const [isBenchmarkOpen, setIsBenchmarkOpen] = useState(false);

  const stockCounts = useMemo(() => {
    const counts = {
      inside: 0,
      outside: 0,
      coldroom_hdl: 0,
      coldroom_mix: 0,
      total: 0
    };
    bins.forEach(bin => {
      if (bin.occupant) {
        counts.total++;
        if (ZONES.inside.includes(bin.prefix)) counts.inside++;
        else if (ZONES.outside.includes(bin.prefix)) counts.outside++;
        else if (ZONES.coldroom_hdl.includes(bin.prefix)) counts.coldroom_hdl++;
        else if (ZONES.coldroom_mix.includes(bin.prefix)) counts.coldroom_mix++;
      }
    });
    return counts;
  }, [bins]);

  const syncWithDatabase = async () => {
    setIsSyncing(true);
    setMode("manual");
    setRecommendations({});
    try {
      const layout = generateBinsFromDrawings();
      const response = await fetch("/api/inventory");
      const dbStock = await response.json();
      if (dbStock.error) throw new Error(dbStock.error);

      setGlobalTotal(dbStock.length);
      setRealityStockList(dbStock);
      setChangelog([]);

      // 1. Map Reality to 3D Layout
      const hydratedBins = layout.map((bin) => {
        const match = dbStock.find((s: any) => s.location_code === bin.locationCode);
        if (match) {
          return {
            ...bin,
            occupant: {
              id: match.id || Math.random().toString(),
              name: match.name || "Unknown Item",
              category: (match.category as Category) || "General / Other",
              height: parseFloat(match.height) || 1.0,
              status: "slotted" as const,
            },
          };
        }
        return bin;
      });

      // 2. Identify Unassigned Items for the Inbound Queue
      // Filter manifest to show items that are NOT currently in a bin that we have in 3D
      const slottedIdsIn3D = hydratedBins.filter(b => b.occupant).map(b => b.occupant!.id);
      setQueue(INBOUND_LOAD.filter(p => !slottedIdsIn3D.includes(p.id)));

      setBins(hydratedBins);
      evaluateSafetyConflicts(hydratedBins);
    } catch (err) {
      console.error("Sync Error:", err);
      setBins(generateBinsFromDrawings());
      setQueue(INBOUND_LOAD);
    } finally {
      setIsSyncing(false);
    }
  };

  useEffect(() => { syncWithDatabase(); }, []);

  const handleBinClick = (binId: string) => {
    if (mode === "optimized") return;
    setBins((prev) => {
      const newBins = [...prev];
      const targetBin = newBins.find((b) => b.id === binId);
      if (!targetBin) return prev;

      if (selectedPallet && !targetBin.occupant) {
        if (selectedPallet.height > targetBin.clearance) {
          alert("Physical Constraint Violation: Pallet exceeds bin clearance.");
          return prev;
        }
        targetBin.occupant = { ...selectedPallet, isManual: true };
        setStagedPlacements(prevS => [...prevS, {
          location_id: targetBin.locationCode, StockCode: selectedPallet.id, Description: selectedPallet.name,
          refined_category: selectedPallet.category, Height_Fixed: selectedPallet.height,
          zone: activeTab === "inside" ? "INSIDE_STORAGE" : activeTab === "outside" ? "OUTSIDE" : activeTab === "coldroom_hdl" ? "COLD_ROOM_HDL" : "COLD_ROOM_MIX",
          prefix: targetBin.prefix, x: targetBin.x, y: targetBin.level * 1.6, z: targetBin.z
        }]);
        setSelectedPallet(null);
        setQueue((q) => q.filter((p) => p.id !== selectedPallet.id));
      } else if (!selectedPallet && targetBin.occupant) {
        if (targetBin.occupant.isManual) {
          const removed = targetBin.occupant;
          targetBin.occupant = null;
          setStagedPlacements(prevS => prevS.filter(p => p.StockCode !== removed.id));
          setQueue((q) => [...q, { ...removed, isManual: false, isNew: false, status: "queue" }]);
        } else {
          alert("Safety: Only manually slotted items can be manually removed.");
        }
      }
      evaluateSafetyConflicts(newBins);
      return newBins;
    });
  };

  const evaluateSafetyConflicts = (currentBins: Bin[]) => {
    currentBins.forEach((bin) => (bin.hasConflict = false));
    const hazmats = currentBins.filter((b) => b.occupant?.category === "Hazardous" || b.occupant?.category === "Chemical");
    const foods = currentBins.filter((b) => b.occupant?.category === "Food-Grade");
    hazmats.forEach((h) => {
      foods.forEach((f) => {
        if (h.prefix === f.prefix && Math.sqrt(Math.pow(h.x - f.x, 2) + Math.pow(h.z - f.z, 2)) < 3.0) {
          h.hasConflict = true; f.hasConflict = true;
        }
      });
    });
  };

  const addToInbound = () => {
    if (!newStockInput.trim()) return;
    const searchTerm = newStockInput.trim().toUpperCase();
    const match = INBOUND_LOAD.find(p => p.id.toUpperCase() === searchTerm || p.name.toUpperCase().includes(searchTerm));
    if (match) {
      if (queue.find(p => p.id === match.id)) { alert(`${match.id} is already in the batch.`); }
      else { setQueue((prev) => [...prev, { ...match, status: "queue" }]); setNewStockInput(""); }
    } else { alert(`SKU "${newStockInput}" not found in inbound manifest.`); }
  };

  const runTargetedRecommendations = async () => {
    if (queue.length === 0) return;
    setIsSyncing(true);
    try {
      const response = await fetch("/api/inventory/optimize-targeted", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ stockCodes: queue.map(p => p.id), algorithm: selectedAlgorithm }),
      });
      const result = await response.json();
      if (result.error) throw new Error(result.error);
      alert("AI Suggestions slotted successfully! Showing proposed layout.");
      await syncWithProposedLayout(queue.map(p => p.id));
    } catch (err: any) { console.error(err); alert(`Failed to generate suggestions: ${err.message || err}`); } finally { setIsSyncing(false); }
  };

  const stageProposedLayout = async () => {
    if (stagedPlacements.length === 0) return;
    setIsSyncing(true);
    try {
      const response = await fetch("/api/inventory/stage", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ placements: stagedPlacements }) });
      const result = await response.json();
      if (result.error) throw new Error(result.error);
      alert("Layout staged to Proposed View.");
    } catch (err) { console.error(err); alert("Failed to stage layout."); } finally { setIsSyncing(false); }
  };

  const confirmPlacement = async () => {
    if (!confirm("Are you sure? This updates the Master Reality database permanently.")) return;
    setIsSyncing(true);
    try {
      const response = await fetch("/api/inventory/confirm", { 
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ algorithm: selectedAlgorithm })
      });
      const result = await response.json();
      if (result.error) throw new Error(result.error);
      alert(`Success! ${result.updatedCount} items committed.`);
      setStagedPlacements([]); setQueue([]); syncWithDatabase();
    } catch (err) { console.error(err); alert("Failed to commit."); } finally { setIsSyncing(false); }
  };

  const runOptimization = async (optimizationMode: "incremental" | "complete") => {
    setIsSyncing(true);
    try {
      const response = await fetch("/api/inventory/optimize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode: optimizationMode, algorithm: selectedAlgorithm }),
      });
      const result = await response.json();
      if (result.error) throw new Error(result.error);
      alert(`${optimizationMode === "complete" ? "Complete Re-optimization" : "Incremental Optimization"} finished successfully! Showing proposed layout.`);
      await syncWithProposedLayout();
    } catch (err: any) {
      console.error(err);
      alert(`Optimization failed: ${err.message || err}`);
    } finally {
      setIsSyncing(false);
    }
  };

  const syncWithProposedLayout = async (highlightIds: string[] = [], algoOverride?: "coi" | "ga" | "sa") => {
    const targetAlgo = algoOverride || selectedAlgorithm;
    setIsSyncing(true); setMode("optimized");
    try {
      const layout = generateBinsFromDrawings();
      const response = await fetch(`/api/inventory/optimized?algorithm=${targetAlgo}`);
      const optimizedStock = await response.json();
      if (optimizedStock.error) throw new Error(optimizedStock.error);

      // Compute changelog
      const computedChanges: { id: string; name: string; oldLocation?: string; newLocation: string; type: "NEW" | "MOVED" }[] = [];
      for (const opt of optimizedStock) {
        const realityMatch = realityStockList.find((r: any) => r.id === opt.id);
        if (!realityMatch || !realityMatch.location_code || realityMatch.location_code === "" || realityMatch.location_code.includes("UNASSIGNED")) {
          computedChanges.push({ id: opt.id, name: opt.name || opt.Description || opt.id, newLocation: opt.location_code || opt.location_id, type: "NEW" });
        } else if (realityMatch.location_code !== (opt.location_code || opt.location_id)) {
          computedChanges.push({ id: opt.id, name: opt.name || opt.Description || opt.id, oldLocation: realityMatch.location_code, newLocation: opt.location_code || opt.location_id, type: "MOVED" });
        }
      }
      setChangelog(computedChanges);

      const hydratedBins = layout.map((bin) => {
        const match = optimizedStock.find((s: any) => (s.location_code || s.location_id) === bin.locationCode);
        if (match) {
          return { ...bin, occupant: { id: match.id, name: match.name, category: match.category as Category, height: parseFloat(match.height), status: "slotted" as const, isNew: highlightIds.includes(match.id) } };
        }
        return bin;
      });

      // Update queue for Proposed View too
      const slottedIdsIn3D = hydratedBins.filter(b => b.occupant).map(b => b.occupant!.id);
      setQueue(INBOUND_LOAD.filter(p => !slottedIdsIn3D.includes(p.id)));

      setBins(hydratedBins); evaluateSafetyConflicts(hydratedBins);
    } catch (err) { console.error(err); } finally { setIsSyncing(false); }
  };

  const resetManual = () => { setMode("manual"); setQueue([]); setBins(generateBinsFromDrawings()); setStagedPlacements([]); setRecommendations({}); syncWithDatabase(); };

  const kpis = (() => {
    const conflicts = bins.filter((b) => b.hasConflict).length;
    let vUsed = 0, vCap = 0;
    bins.forEach((b) => { if (b.occupant) { vCap += b.clearance; vUsed += b.occupant.height; } });
    return { conflicts, efficiency: vCap === 0 ? 0 : Math.round((vUsed / vCap) * 100) };
  })();

  const RackSystem = () => {
    const [hoveredBin, setHoveredBin] = useState<string | null>(null);
    const filteredBins = bins.filter((b) => {
      if (activeTab === "inside") return ZONES.inside.includes(b.prefix);
      if (activeTab === "outside") return ZONES.outside.includes(b.prefix);
      if (activeTab === "coldroom_hdl") return ZONES.coldroom_hdl.includes(b.prefix);
      if (activeTab === "coldroom_mix") return ZONES.coldroom_mix.includes(b.prefix);
      return false;
    });
    const center = useMemo(() => {
      if (filteredBins.length === 0) return { x: 0, z: 0 };
      const xs = filteredBins.map((b) => b.x), zs = filteredBins.map((b) => b.z);
      return { x: (Math.min(...xs) + Math.max(...xs)) / 2, z: (Math.min(...zs) + Math.max(...zs)) / 2 };
    }, [filteredBins]);

    return (
      <group position={[-center.x, 0, -center.z]}>
        {filteredBins.map((bin) => {
          const beamY = bin.level * 1.6;
          const isColdRoom = ["FA", "FB", "FC", "FD", "FE", "FF", "FG", "FH"].includes(bin.prefix);
          const isSelected = mode === "manual" && selectedPallet && !bin.occupant && bin.clearance >= selectedPallet.height;
          const recsForPallet = selectedPallet ? recommendations[selectedPallet.id] : [];
          const isRecommended = recsForPallet?.includes(bin.locationCode);
          const isBestRec = isRecommended && recsForPallet?.[0] === bin.locationCode;

          return (
            <group key={bin.id} position={[bin.x, 0, bin.z]}>
              <Box args={[1.4, 0.1, 1.2]} position={[0, beamY, 0]}>
                <meshStandardMaterial color={isColdRoom ? "#3b82f6" : "#334155"} />
                <Edges color="black" />
              </Box>
              {isRecommended && (
                <mesh position={[0, beamY + 0.8, 0]}>
                   <boxGeometry args={[1.3, 1.5, 1.1]} />
                   <meshBasicMaterial color={isBestRec ? "#10b981" : "#f59e0b"} transparent opacity={0.3} />
                   <Edges color={isBestRec ? "#10b981" : "#f59e0b"} threshold={15} lineWidth={isBestRec ? 4 : 2} />
                </mesh>
              )}
              <mesh position={[0, beamY + 0.8, 0]} onClick={() => handleBinClick(bin.id)} onPointerOver={() => setHoveredBin(bin.id)} onPointerOut={() => setHoveredBin(null)}>
                <boxGeometry args={[1.2, 1.4, 1.0]} />
                <meshBasicMaterial color={isSelected ? "#4f46e5" : "#ffffff"} opacity={isSelected ? 0.3 : 0} transparent />
              </mesh>
              {bin.occupant && (
                <Box args={[0.9, bin.occupant.height, 0.9]} position={[0, beamY + 0.1 + bin.occupant.height / 2, 0]}>
                  <meshStandardMaterial color={bin.hasConflict ? "#ef4444" : COLORS[bin.occupant.category]} />
                  <Edges color={bin.occupant.isNew ? "#10b981" : "black"} threshold={15} lineWidth={bin.occupant.isNew ? 3 : 1} />
                </Box>
              )}
              {hoveredBin === bin.id && bin.occupant && (
                <Html position={[0, beamY + 2.0, 0]} center distanceFactor={10}>
                  <div className="bg-slate-900 border border-indigo-500 p-2 rounded shadow-xl whitespace-nowrap pointer-events-none text-white">
                    <div className="text-[10px] font-bold">{bin.occupant.name}</div>
                    <div className="text-[8px] text-indigo-400 font-mono mt-1">LOC: {bin.locationCode} ({bin.depth})</div>
                  </div>
                </Html>
              )}
              <Html position={[0, beamY + 0.1, 0.65]} center distanceFactor={15} occlude="blending">
                <div className="text-[4px] text-slate-400 font-mono bg-slate-900/50 px-0.5 rounded pointer-events-none">{bin.locationCode}</div>
              </Html>
            </group>
          );
        })}
      </group>
    );
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-50 flex flex-col">
      <div className="p-6 border-b border-slate-800 bg-slate-900 flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold italic tracking-tighter flex items-baseline gap-2">
            DIGITAL TWIN: <span className="text-indigo-500">WAREHOUSE</span>
            <span className={`text-xs px-2 py-0.5 rounded font-mono uppercase tracking-widest border ${mode === 'optimized' ? 'bg-amber-500/10 border-amber-500 text-amber-500' : 'bg-emerald-500/10 border-emerald-500 text-emerald-500'}`}>
              {mode === 'optimized' ? 'Proposed View' : 'Current Reality'}
            </span>
          </h1>
          <p className="text-slate-400 text-xs uppercase tracking-widest mt-1">Sprint Logistics (M) SDN BHD</p>
        </div>
        <div className="flex gap-4"><div className="flex items-center gap-2 text-xs"><div className="w-2 h-2 bg-blue-500 rounded-full"></div> Cold Storage</div><div className="flex items-center gap-2 text-xs"><div className="w-2 h-2 bg-slate-700 rounded-full"></div> Dry Storage</div></div>
      </div>
      <div className="flex flex-1 overflow-hidden">
        <div className="w-80 bg-slate-900 border-r border-slate-800 p-6 flex flex-col gap-6">
          <h2 className="font-bold text-sm flex items-center gap-2 text-indigo-400 uppercase tracking-widest"><Package className="w-4 h-4" /> Inbound Logistics</h2>
          <div className="flex flex-col gap-2 overflow-y-auto max-h-[300px] pr-2 custom-scrollbar">
            {queue.map((pallet) => (
              <div key={pallet.id} onClick={() => setSelectedPallet(pallet)} className={`p-3 rounded border transition-all cursor-pointer ${selectedPallet?.id === pallet.id ? "bg-indigo-600/20 border-indigo-500 shadow-[0_0_10px_rgba(79,70,229,0.3)]" : "bg-slate-800 border-slate-700 hover:border-slate-500"}`}>
                <div className="text-xs font-bold">{pallet.name}</div>
                <div className="text-[10px] text-slate-400 mt-1 flex justify-between"><span style={{ color: COLORS[pallet.category] }}>{pallet.category}</span><span>{pallet.height}m</span></div>
              </div>
            ))}
            {queue.length === 0 && <div className="text-[10px] text-slate-500 italic text-center py-4">All inbound items from the manifest have been assigned.</div>}
          </div>
          <div className="mt-4 p-4 bg-slate-800/50 border border-slate-700 rounded-lg flex flex-col gap-3">
            <h3 className="text-[10px] font-bold text-emerald-400 uppercase tracking-widest">Search Inbound Manifest</h3>
            <div className="flex gap-2">
              <input type="text" value={newStockInput} onChange={(e) => setNewStockInput(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && addToInbound()} placeholder="Search SKU or Name..." className="flex-1 bg-slate-900 border border-slate-700 rounded px-2 py-1 text-xs text-white focus:outline-none focus:border-emerald-500" />
              <button onClick={addToInbound} className="px-2 py-1 bg-emerald-600 hover:bg-emerald-500 rounded text-[10px] font-bold">ADD</button>
            </div>
            <button onClick={runTargetedRecommendations} disabled={isSyncing || queue.length === 0} className={`w-full p-2 rounded text-[10px] font-bold flex items-center justify-center gap-2 uppercase transition-all ${isSyncing || queue.length === 0 ? "bg-slate-700 text-slate-500 cursor-not-allowed" : "bg-emerald-600 hover:bg-emerald-500 text-white shadow-[0_0_10px_rgba(16,185,129,0.2)]"}`}><Zap className="w-3 h-3" /> Get AI Suggestions</button>
          </div>
          <div className="p-4 bg-slate-800/50 border border-slate-700 rounded-lg flex flex-col gap-3">
            <h3 className="text-[10px] font-bold text-indigo-400 uppercase tracking-widest flex items-center gap-1"><Zap className="w-3 h-3" /> AI Optimization Engines</h3>
            <div className="flex bg-slate-900 border border-slate-700 rounded p-1 gap-1">
              <button
                onClick={() => { setSelectedAlgorithm("coi"); if (mode === "optimized") syncWithProposedLayout([], "coi"); }}
                className={`flex-1 py-1 rounded text-[8px] font-bold uppercase transition-all ${selectedAlgorithm === "coi" ? "bg-indigo-600 text-white shadow" : "text-slate-400 hover:text-white"}`}
              >
                Heuristic (COI)
              </button>
              <button
                onClick={() => { setSelectedAlgorithm("ga"); if (mode === "optimized") syncWithProposedLayout([], "ga"); }}
                className={`flex-1 py-1 rounded text-[8px] font-bold uppercase transition-all ${selectedAlgorithm === "ga" ? "bg-indigo-600 text-white shadow" : "text-slate-400 hover:text-white"}`}
              >
                Genetic (GA)
              </button>
              <button
                onClick={() => { setSelectedAlgorithm("sa"); if (mode === "optimized") syncWithProposedLayout([], "sa"); }}
                className={`flex-1 py-1 rounded text-[8px] font-bold uppercase transition-all ${selectedAlgorithm === "sa" ? "bg-indigo-600 text-white shadow" : "text-slate-400 hover:text-white"}`}
              >
                Annealing (SA)
              </button>
            </div>
            <button 
              onClick={() => runOptimization("incremental")} 
              disabled={isSyncing} 
              className={`w-full p-2 rounded text-[10px] font-bold text-left flex flex-col gap-0.5 transition-all ${
                isSyncing 
                  ? "bg-slate-700 text-slate-500 cursor-not-allowed border border-transparent" 
                  : "bg-slate-900 border border-slate-700 hover:border-indigo-500 hover:bg-slate-800 text-slate-200 cursor-pointer"
              }`}
            >
              <span>INCREMENTAL OPTIMIZER (REALISTIC)</span>
              <span className="text-[8px] text-slate-400 font-normal normal-case">Places only new inventory, keeps existing stock static</span>
            </button>
            <button 
              onClick={() => runOptimization("complete")} 
              disabled={isSyncing} 
              className={`w-full p-2 rounded text-[10px] font-bold text-left flex flex-col gap-0.5 transition-all ${
                isSyncing 
                  ? "bg-slate-700 text-slate-500 cursor-not-allowed border border-transparent" 
                  : "bg-indigo-650 hover:bg-indigo-600 text-white shadow-[0_0_10px_rgba(79,70,229,0.2)] cursor-pointer"
              }`}
            >
              <span>FULL WAREHOUSE RE-OPTIMIZER</span>
              <span className="text-[8px] text-indigo-200 font-normal normal-case">Moves the entire stock to the most optimal layout</span>
            </button>
            <button 
              onClick={() => setIsBenchmarkOpen(true)} 
              className="w-full mt-1 p-2 rounded text-[10px] font-bold text-center flex items-center justify-center gap-2 uppercase transition-all bg-amber-500/10 border border-amber-500/30 text-amber-300 hover:bg-amber-500 hover:text-slate-950 shadow-[0_0_10px_rgba(245,158,11,0.15)] cursor-pointer"
            >
              📊 Compare AI Engine Analytics & KPIs
            </button>
          </div>
          <div className="mt-auto flex flex-col gap-3">
            {mode === 'optimized' && changelog.length > 0 && (
              <div className="p-3 bg-slate-900 border border-amber-500/50 rounded-lg max-h-48 overflow-y-auto flex flex-col gap-2 shadow-[0_0_15px_rgba(245,158,11,0.15)]">
                <div className="flex items-center justify-between">
                  <h3 className="text-[10px] font-bold text-amber-400 uppercase tracking-widest flex items-center gap-1">
                    <Zap className="w-3 h-3" /> Proposed Changes ({changelog.length})
                  </h3>
                  <span className="text-[9px] text-slate-400">Review before commit</span>
                </div>
                <div className="flex flex-col gap-1 text-[10px]">
                  {changelog.map((c, i) => (
                    <div key={i} className="flex items-center justify-between bg-slate-800/80 px-2 py-1 rounded">
                      <div className="flex flex-col truncate pr-2">
                        <span className="font-bold text-white truncate">{c.id} - {c.name}</span>
                        <span className="text-[8px] text-slate-400">
                          {c.type === 'NEW' ? 'New Slot Assignment' : `Relocated from ${c.oldLocation}`}
                        </span>
                      </div>
                      <span className={`px-1.5 py-0.5 rounded font-mono font-bold text-[9px] ${c.type === 'NEW' ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30' : 'bg-indigo-500/20 text-indigo-300 border border-indigo-500/30'}`}>
                        {c.newLocation}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
            <button onClick={syncWithDatabase} disabled={isSyncing} className="p-3 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 text-xs font-bold uppercase flex items-center justify-center gap-2"><Package className="w-3 h-3" /> Load Current Reality</button>
            <button onClick={confirmPlacement} disabled={isSyncing} className={`p-3 rounded text-xs font-bold uppercase flex items-center justify-center gap-2 ${isSyncing ? "bg-slate-800 text-slate-600 cursor-not-allowed" : "bg-emerald-600 hover:bg-emerald-500 text-white shadow-[0_0_15px_rgba(16,185,129,0.4)]"}`}><CheckCircle className="w-3 h-3" /> Commit to Master</button>
            <button onClick={resetManual} className="p-3 rounded bg-slate-800 hover:bg-slate-700 text-xs font-bold uppercase">Clear / Reset</button>
          </div>
        </div>
        <div className="flex-1 relative bg-slate-950">
          <div className="absolute top-6 left-6 right-6 flex flex-col gap-4 z-10 pointer-events-none">
            <div className="flex gap-2 pointer-events-auto">
              {["inside", "outside", "coldroom_hdl", "coldroom_mix"].map((t) => {
                const count = stockCounts[t as keyof typeof stockCounts];
                return (
                  <button key={t} onClick={() => setActiveTab(t as any)} className={`px-4 py-2 text-[10px] font-bold uppercase rounded-t border-t border-x transition-all ${activeTab === t ? "bg-slate-900 border-slate-700 text-indigo-400" : "bg-slate-950/50 border-transparent text-slate-500 hover:text-slate-300"}`}>
                    {t.replace("_", " ")} <span className="ml-1 opacity-60">({count})</span>
                  </button>
                );
              })}
            </div>
            <div className="flex gap-4">
              <div className={`flex-1 p-4 rounded-b rounded-tr bg-slate-900/80 backdrop-blur border ${kpis.conflicts > 0 ? "border-red-500" : "border-slate-800"} pointer-events-auto`}>
                <div className="text-[10px] text-slate-500 uppercase font-bold">Safety</div>
                <div className="text-xl font-black">{kpis.conflicts > 0 ? <span className="flex items-center gap-2 text-red-500"><AlertTriangle /> {kpis.conflicts} ERRORS</span> : <span className="flex items-center gap-2 text-emerald-500"><CheckCircle /> 100% OK</span>}</div>
              </div>
              <div className="flex-1 p-4 rounded bg-slate-900/80 backdrop-blur border border-slate-800 pointer-events-auto"><div className="text-[10px] text-slate-500 uppercase font-bold">Utilization</div><div className="text-xl font-black text-indigo-400">{kpis.efficiency}%</div></div>
              <div className="flex-1 p-4 rounded bg-slate-900/80 backdrop-blur border border-slate-800 pointer-events-auto">
                <div className="text-[10px] text-slate-500 uppercase font-bold">Slotted / Total Stock</div>
                <div className="text-xl font-black text-indigo-400">{stockCounts.total} <span className="text-slate-600 text-sm font-normal">/ {globalTotal}</span></div>
              </div>
            </div>
          </div>
          <Canvas style={{ visibility: isBenchmarkOpen ? "hidden" : "visible" }} camera={{ position: [15, 15, 15], fov: 40 }}><ambientLight intensity={0.5} /><pointLight position={[20, 20, 20]} intensity={1} /><RackSystem /><gridHelper args={[100, 50, 0x334155, 0x1e293b]} position={[0, -0.01, 0]} /><OrbitControls makeDefault minPolarAngle={0} maxPolarAngle={Math.PI / 2 - 0.1} /></Canvas>
        </div>
      </div>
      <BenchmarkModal 
        isOpen={isBenchmarkOpen} 
        onClose={() => setIsBenchmarkOpen(false)} 
        onSelectWinner={(algo) => { setSelectedAlgorithm(algo); if (mode === "optimized") syncWithProposedLayout([], algo); }} 
      />
    </div>
  );
}
