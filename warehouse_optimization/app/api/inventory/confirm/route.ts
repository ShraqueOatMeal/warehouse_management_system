import { NextResponse } from "next/server";
import { Pool } from "pg";

const pool = new Pool({
  user: process.env.DB_USER || "loh-yen-kuan",
  host: process.env.DB_HOST || "localhost",
  database: "wms",
  password: process.env.DB_PASSWORD || "Loh020518!@#",
  port: parseInt(process.env.DB_PORT || "5433"),
});

export async function POST(request: Request) {
  const { algorithm = "coi" } = await request.json().catch(() => ({ algorithm: "coi" }));
  const tableName = algorithm === "ga" ? "proposed_layout_ga" : algorithm === "sa" ? "proposed_layout_sa" : "proposed_layout_coi";
  const client = await pool.connect();
  try {
    await client.query("BEGIN");

    // Update optimization_master based on proposed_layout table
    // We update the primary location and the normalized location ID
    const updateQuery = `
      UPDATE optimization_master om
      SET 
        "Primary_Location_Fixed" = plc.location_id,
        "Cured_Location" = plc.location_id,
        "zone" = plc.zone,
        "prefix" = plc.prefix,
        "x" = plc.x,
        "y" = plc.y,
        "z" = plc.z
      FROM ${tableName} plc
      WHERE om."StockCode" = plc."StockCode"
    `;

    const result = await client.query(updateQuery);

    await client.query("COMMIT");

    return NextResponse.json({
      message: "Placement confirmed and master updated",
      updatedCount: result.rowCount,
    });
  } catch (error) {
    await client.query("ROLLBACK");
    console.error("Confirmation Error:", error);
    return NextResponse.json(
      { error: "Failed to confirm and commit placement" },
      { status: 500 },
    );
  } finally {
    client.release();
  }
}
