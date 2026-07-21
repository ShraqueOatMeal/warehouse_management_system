import { NextResponse } from "next/server";
import { exec } from "child_process";
import { promisify } from "util";
import path from "path";

const execPromise = promisify(exec);

export async function POST(request: Request) {
  try {
    const { stockCodes, algorithm = "coi" } = await request.json();

    if (!stockCodes || !Array.isArray(stockCodes) || stockCodes.length === 0) {
      return NextResponse.json(
        { error: "Invalid stock codes provided" },
        { status: 400 },
      );
    }

    // Path to your python environment and script
    const pythonPath = "/home/loh-yen-kuan/Coding/JupyterNotebook/notenv/bin/python";
    const scriptName = algorithm === "ga" ? "ga_optimization.py" : algorithm === "sa" ? "sa_optimization.py" : "coi_optimization.py";
    const scriptPath = path.join(process.cwd(), "..", "data_cleaning", "pipeline", scriptName);
    
    // Pass stock codes as a JSON string argument
    const stockCodesJson = JSON.stringify(stockCodes);
    const command = `${pythonPath} ${scriptPath} '${stockCodesJson}'`;

    console.log(`Executing targeted optimization: ${command}`);
    const { stdout, stderr } = await execPromise(command);

    if (stderr && !stdout) {
      console.error("Python Error:", stderr);
      return NextResponse.json({ error: stderr }, { status: 500 });
    }

    console.log("Python Output:", stdout);

    return NextResponse.json({ message: "Targeted optimization complete", detail: stdout });
  } catch (error) {
    console.error("API Error:", error);
    return NextResponse.json(
      { error: "Failed to trigger targeted optimization" },
      { status: 500 },
    );
  }
}
