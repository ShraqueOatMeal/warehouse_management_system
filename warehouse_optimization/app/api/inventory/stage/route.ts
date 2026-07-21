import { NextResponse } from "next/server";
import { Pool } from "pg";

const pool = new Pool({
  user: process.env.DB_USER || "loh-yen-kuan",
  host: process.env.DB_HOST || "localhost",
  database: "wms",
  password: process.env.DB_PASSWORD || "Loh020518!@#",
  port: parseInt(process.env.DB_PORT || "5433"),
});

/**
 * Stage a proposed layout to the proposed_layout_coi table.
 */
export async function POST(request: Request) {
    const client = await pool.connect();
    try {
        const { placements } = await request.json(); // Array of { location_id, StockCode, ... }

        if (!placements || !Array.isArray(placements)) {
            return NextResponse.json({ error: "Invalid placements data" }, { status: 400 });
        }

        await client.query("BEGIN");
        
        // Clear old proposed layout or just append? 
        // Let's assume we replace the entire proposed view for simplicity
        await client.query("DELETE FROM proposed_layout_coi");

        for (const p of placements) {
            const query = `
                INSERT INTO proposed_layout_coi (
                    location_id, "StockCode", "Description", refined_category, "Height_Fixed", zone, prefix, x, y, z
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            `;
            await client.query(query, [
                p.location_id, p.StockCode, p.Description, p.refined_category, p.Height_Fixed, 
                p.zone, p.prefix, p.x, p.y, p.z
            ]);
        }

        await client.query("COMMIT");
        return NextResponse.json({ message: "Staged to proposed layout" });
    } catch (error) {
        await client.query("ROLLBACK");
        console.error("Stage Error:", error);
        return NextResponse.json({ error: "Failed to stage layout" }, { status: 500 });
    } finally {
        client.release();
    }
}
