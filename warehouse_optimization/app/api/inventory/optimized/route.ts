import { NextResponse } from "next/server";
import { Pool } from "pg";

const pool = new Pool({
  user: process.env.DB_USER || "loh-yen-kuan",
  host: process.env.DB_HOST || "localhost",
  database: "wms",
  password: process.env.DB_PASSWORD || "Loh020518!@#",
  port: parseInt(process.env.DB_PORT || "5433"),
});

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const algorithm = searchParams.get("algorithm") || "coi";
    const tableName = algorithm === "ga" ? "proposed_layout_ga" : algorithm === "sa" ? "proposed_layout_sa" : "proposed_layout_coi";

    const query = `
      SELECT 
        location_id as location_code, 
        "Description" as name, 
        refined_category as category,
        "Height_Fixed" as height,
        "StockCode" as id,
        depth
      FROM ${tableName}
    `;

    const result = await pool.query(query);

    return NextResponse.json(result.rows);
  } catch (error) {
    console.error("Database Error:", error);
    return NextResponse.json(
      { error: "Failed to fetch optimized inventory" },
      { status: 500 },
    );
  }
}
