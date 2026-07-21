import { NextResponse } from "next/server";
import { Pool } from "pg";

// Configure your PostgreSQL connection here or via .env
const pool = new Pool({
  user: process.env.DB_USER || "loh-yen-kuan",
  host: process.env.DB_HOST || "localhost",
  database: "wms",
  password: process.env.DB_PASSWORD || "Loh020518!@#",
  port: parseInt(process.env.DB_PORT || "5433"),
});

export async function GET() {
  try {
    // We fetch the most recent stock mapping.
    // If you have a 'date' or 'timestamp' column, add 'ORDER BY timestamp_column DESC'
    const query = `
      SELECT 
        "Cured_Location" as location_code, 
        "Description" as name, 
        "refined_category" as category,
        "Height_Fixed" as height,
        "StockCode" as id,
        "depth"
      FROM optimization_master
    `;

    const result = await pool.query(query);

    return NextResponse.json(result.rows);
  } catch (error) {
    console.error("Database Error:", error);
    return NextResponse.json(
      { error: "Failed to fetch inventory" },
      { status: 500 },
    );
  }
}
