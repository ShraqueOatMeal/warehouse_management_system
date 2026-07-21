import { NextResponse } from "next/server";
import { exec } from "child_process";
import { promisify } from "util";
import path from "path";

const execPromise = promisify(exec);

export async function POST(request: Request) {
  try {
    const { stockCodes } = await request.json();

    if (!stockCodes || !Array.isArray(stockCodes) || stockCodes.length === 0) {
      return NextResponse.json(
        { error: "Invalid stock codes provided" },
        { status: 400 },
      );
    }

    const pythonPath = "/home/loh-yen-kuan/Coding/JupyterNotebook/notenv/bin/python";
    const scriptPath = path.join(process.cwd(), "..", "data_cleaning", "pipeline", "coi_recommendations.py");
    
    const stockCodesJson = JSON.stringify(stockCodes);
    const command = `${pythonPath} ${scriptPath} '${stockCodesJson}'`;

    console.log(`Executing recommendation engine: ${command}`);
    const { stdout, stderr } = await execPromise(command);

    if (stderr && !stdout) {
      console.error("Python Error:", stderr);
      return NextResponse.json({ error: stderr }, { status: 500 });
    }

    // Extract the JSON result from stdout
    const match = stdout.match(/REC_RESULT:(.*)/);
    if (!match) {
        return NextResponse.json({ error: "Failed to parse recommendation result", raw: stdout }, { status: 500 });
    }
    
    const recommendations = JSON.parse(match[1]);

    return NextResponse.json({ recommendations });
  } catch (error) {
    console.error("API Error:", error);
    return NextResponse.json(
      { error: "Failed to generate recommendations" },
      { status: 500 },
    );
  }
}
