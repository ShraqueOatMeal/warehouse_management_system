import { NextResponse } from "next/server";
import { Pool } from "pg";

const pool = new Pool({
  user: process.env.DB_USER || "loh-yen-kuan",
  host: process.env.DB_HOST || "localhost",
  database: "wms",
  password: process.env.DB_PASSWORD || "Loh020518!@#",
  port: parseInt(process.env.DB_PORT || "5433"),
});

export async function GET() {
  const client = await pool.connect();
  try {
    const tables = [
      { id: "coi", name: "Heuristic (COI)", table: "proposed_layout_coi" },
      { id: "ga", name: "Genetic Algo (GA)", table: "proposed_layout_ga" },
      { id: "sa", name: "Simulated Annealing (SA)", table: "proposed_layout_sa" },
    ];

    const benchmarkResults = [];

    for (const t of tables) {
      // Query table stats joined with optimization_master for hits/weight
      const query = `
        SELECT 
          COUNT(*) as total_slotted,
          COALESCE(SUM(COALESCE(om."Total_Hits"::numeric, 1) * SQRT(POW(plc.x, 2) + POW(plc.z, 2))), 0) as estimated_travel,
          COALESCE(AVG(COALESCE(om."Total_Hits"::numeric, 1) * SQRT(POW(plc.x, 2) + POW(plc.z, 2))), 0) as avg_travel_per_hit,
          COUNT(CASE WHEN COALESCE(om."Weight_Fixed"::numeric, 0) >= 500 AND plc.y > 2.0 THEN 1 END) as heavy_violations
        FROM ${t.table} plc
        LEFT JOIN optimization_master om ON plc."StockCode" = om."StockCode"
      `;
      
      const res = await client.query(query);
      const row = res.rows[0];

      // Check safety conflicts (chemical vs food on same prefix)
      const conflictQuery = `
        SELECT COUNT(*) as conflict_count
        FROM ${t.table} c
        JOIN ${t.table} f ON c.prefix = f.prefix AND c."StockCode" != f."StockCode"
        WHERE c.refined_category IN ('Chemical', 'Hazardous') 
          AND f.refined_category = 'Food-Grade'
          AND SQRT(POW(c.x - f.x, 2) + POW(c.z - f.z, 2)) < 3.0
      `;
      const confRes = await client.query(conflictQuery);
      const conflictCount = parseInt(confRes.rows[0].conflict_count) || 0;

      const slotted = parseInt(row.total_slotted) || 0;
      const travel = Math.round(parseFloat(row.estimated_travel));
      const avgDist = parseFloat(row.avg_travel_per_hit).toFixed(1);

      benchmarkResults.push({
        id: t.id,
        name: t.name,
        slottedSkus: slotted,
        totalTravelCost: travel,
        avgTravelPerItem: avgDist,
        safetyConflicts: conflictCount,
        structuralViolations: parseInt(row.heavy_violations) || 0,
        efficiencyScore: Math.round(10000 / (parseFloat(row.avg_travel_per_hit) || 100))
      });
    }

    return NextResponse.json(benchmarkResults);
  } catch (error: any) {
    console.error("Benchmark Error:", error);
    return NextResponse.json({ error: error.message }, { status: 500 });
  } finally {
    client.release();
  }
}
