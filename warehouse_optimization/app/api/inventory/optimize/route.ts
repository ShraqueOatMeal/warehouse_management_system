import { NextResponse } from "next/server";
import { exec } from "child_process";
import { promisify } from "util";
import path from "path";

const execPromise = promisify(exec);

export async function POST(request: Request) {
  try {
    const { mode, algorithm = "coi" } = await request.json(); // "incremental" | "complete"

    // Path to your python environment and script
    const pythonPath = "/home/loh-yen-kuan/Coding/JupyterNotebook/notenv/bin/python";
    const scriptName = algorithm === "ga" ? "ga_optimization.py" : algorithm === "sa" ? "sa_optimization.py" : "coi_optimization.py";
    const scriptPath = path.join(process.cwd(), "..", "data_cleaning", "pipeline", scriptName);
    
    let command = `${pythonPath} ${scriptPath}`;
    if (mode === "complete") {
      command += " --complete";
    }

    console.log(`Executing optimization: ${command}`);
    const { stdout, stderr } = await execPromise(command);

    if (stderr && !stdout) {
      console.error("Python Error:", stderr);
      return NextResponse.json({ error: stderr }, { status: 500 });
    }

    console.log("Python Output:", stdout);

    return NextResponse.json({ message: "Optimization complete", detail: stdout });
  } catch (error: any) {
    console.error("API Error:", error);
    return NextResponse.json(
      { error: error.message || "Failed to trigger optimization" },
      { status: 500 },
    );
  }
}
