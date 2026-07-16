import subprocess
import csv
import math
import os
import io
from collections import Counter, defaultdict

# ── Configuration ──────────────────────────────────────────────────────────
ENV_PATH = "/home/loh-yen-kuan/Coding/FYP/data_cleaning/.env"
OPT_MASTER_CSV = (
    "/home/loh-yen-kuan/Coding/FYP/data_cleaning/pipeline/optimization_master.csv"
)

# Load .env
env = {}
if os.path.exists(ENV_PATH):
    with open(ENV_PATH) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")

PG_HOST = env.get("POSTGRES_HOST", "localhost")
PG_PORT = env.get("POSTGRES_PORT", "5432")
PG_USER = env.get("POSTGRES_USERNAME", "")
PG_PASS = env.get("POSTGRES_PASSWORD", "")
PG_DB = env.get("POSTGRES_DATABASE", "")


def psql_query(sql):
    """Run a SQL query via psql and return rows as list of dicts."""
    cmd = [
        "psql",
        f"postgresql://{PG_USER}:{PG_PASS}@{PG_HOST}:{PG_PORT}/{PG_DB}",
        "--csv",
        "-c",
        sql,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        print(f"  ERROR: {result.stderr.strip()}")
        return []
    reader = csv.DictReader(io.StringIO(result.stdout))
    return list(reader)


def read_csv(path):
    """Read a CSV file and return list of dicts."""
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def safe_float(val, default=0.0):
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def analyze_layout(name, layout, opt_master):
    """Analyze a layout and return metrics dict."""
    total_skus = len(opt_master)
    n = len(layout)

    print(f"\n{'=' * 80}")
    print(f"  {name}")
    print(f"{'=' * 80}")
    print(f"  Total Assigned: {n}")
    print(f"  Coverage: {n}/{total_skus} = {n / total_skus * 100:.1f}%")

    # Zone breakdown
    zones = Counter(r.get("zone", "(null)") or "(null)" for r in layout)
    print(f"\n  Zone Breakdown:")
    for z, c in zones.most_common():
        print(f"    {z}: {c} ({c / n * 100:.1f}%)")

    # Category breakdown
    cats = Counter(r.get("refined_category", "(null)") for r in layout)
    print(f"\n  Category Breakdown:")
    for cat, c in cats.most_common():
        print(f"    {cat}: {c} ({c / n * 100:.1f}%)")

    # Travel distance (Euclidean from origin)
    dists = []
    for r in layout:
        x = safe_float(r.get("x"))
        z_val = safe_float(r.get("z"))
        dists.append(math.sqrt(x * x + z_val * z_val))

    mean_d = sum(dists) / len(dists) if dists else 0
    dists_s = sorted(dists)
    mid = len(dists_s) // 2
    median_d = (
        dists_s[mid]
        if len(dists_s) % 2
        else (dists_s[mid - 1] + dists_s[mid]) / 2
        if dists_s
        else 0
    )
    var = sum((d - mean_d) ** 2 for d in dists) / len(dists) if dists else 0

    print(f"\n  Travel Distance (Euclidean from origin):")
    print(f"    Mean:   {mean_d:.2f}")
    print(f"    Median: {median_d:.2f}")
    print(f"    Min:    {min(dists):.2f}")
    print(f"    Max:    {max(dists):.2f}")
    print(f"    Sum:    {sum(dists):.2f}")
    print(f"    Std:    {var**0.5:.2f}")

    # Per-zone travel
    print(f"\n  Per-Zone Travel Distance:")
    zone_dists = defaultdict(list)
    for r, d in zip(layout, dists):
        zone_dists[r.get("zone", "(null)") or "(null)"].append(d)
    for z in sorted(zone_dists.keys()):
        zd = zone_dists[z]
        print(
            f"    {z}: count={len(zd)}, mean={sum(zd) / len(zd):.2f}, sum={sum(zd):.2f}"
        )

    # Rack level distribution
    print(f"\n  Rack Level Distribution:")
    levels = Counter()
    for r in layout:
        y = safe_float(r.get("y"))
        level = round(y / 1.6) if y > 0 else 0
        levels[level] += 1
    for lv in sorted(levels.keys()):
        y_val = lv * 1.6
        pct = levels[lv] / n * 100
        print(f"    Level {lv} (y={y_val:.1f}): {levels[lv]} ({pct:.1f}%)")
    lower = sum(levels[l] for l in levels if l <= 1)
    print(f"    Levels 0-1: {lower} ({lower / n * 100:.1f}%)")

    # Safety violations
    print(f"\n  Safety Violation Check:")
    chem = [
        r for r in layout if r.get("refined_category", "") in ("Chemical", "Hazardous")
    ]
    food = [r for r in layout if r.get("refined_category", "") == "Food-Grade"]
    print(f"    Chemical/Hazardous: {len(chem)}")
    print(f"    Food-Grade: {len(food)}")

    violations = 0
    for c in chem:
        for f in food:
            c_zone = c.get("zone", "")
            f_zone = f.get("zone", "")
            c_pref = c.get("prefix", "")
            f_pref = f.get("prefix", "")
            if c_zone != f_zone or c_pref != f_pref:
                continue
            if not c_zone or not c_pref:
                continue
            dx = safe_float(c.get("x")) - safe_float(f.get("x"))
            dz = safe_float(c.get("z")) - safe_float(f.get("z"))
            dist = math.sqrt(dx * dx + dz * dz)
            if dist < 3.0:
                violations += 1
    print(f"    Safety Violations: {violations}")

    # Weight constraint
    print(f"\n  Weight Constraint Check:")
    heavy = [r for r in layout if safe_float(r.get("Weight_Fixed")) >= 500]
    heavy_high = [r for r in heavy if safe_float(r.get("y")) > 1.5]
    print(f"    Heavy items (>=500kg): {len(heavy)}")
    print(
        f"    Heavy on high racks (y>1.5): {len(heavy_high)} ({len(heavy_high) / len(heavy) * 100:.1f}%)"
        if heavy
        else "    No heavy items"
    )

    return {
        "name": name,
        "count": n,
        "coverage": n / total_skus * 100,
        "mean_dist": mean_d,
        "sum_dist": sum(dists),
        "min_dist": min(dists) if dists else 0,
        "max_dist": max(dists) if dists else 0,
        "violations": violations,
        "heavy_total": len(heavy),
        "heavy_high": len(heavy_high),
        "lower_rack_pct": lower / n * 100 if n else 0,
    }


# ── Main ───────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 80)
    print("  COMPREHENSIVE MODEL EVALUATION — ALL 3 OPTIMIZATION MODELS")
    print("=" * 80)

    # Load optimization master
    opt_master = read_csv(OPT_MASTER_CSV)
    print(f"\nOptimization Master: {len(opt_master)} SKUs")

    cats = Counter(r["refined_category"] for r in opt_master)
    print("Category Breakdown:")
    for cat, c in cats.most_common():
        print(f"  {cat}: {c} ({c / len(opt_master) * 100:.1f}%)")

    # Query all 3 layouts from database
    print("\n--- Querying layouts from PostgreSQL ---")
    models = {}

    for table, label in [
        ("proposed_layout_coi", "COI GREEDY (T1)"),
        ("proposed_layout_ga", "MEMETIC GA (T2)"),
        ("proposed_layout_sa", "SIMULATED ANNEALING (T3)"),
    ]:
        rows = psql_query(f"SELECT * FROM {table}")
        if rows:
            models[label] = rows
            print(f"  {label}: {len(rows)} rows loaded")
        else:
            print(f"  {label}: FAILED or EMPTY")

    # Analyze each model
    results = {}
    for label, layout in models.items():
        results[label] = analyze_layout(label, layout, opt_master)

    # Comparative Summary
    if len(results) >= 2:
        print(f"\n{'=' * 80}")
        print("  COMPARATIVE SUMMARY")
        print(f"{'=' * 80}")

        headers = list(results.keys())
        print(f"\n  {'Metric':<30}", end="")
        for h in headers:
            print(f" | {h.split('(')[1].rstrip(')'):>8}", end="")
        print()
        print(f"  {'-' * 30}", end="")
        for _ in headers:
            print(f" | {'-' * 8}", end="")
        print()

        metrics = [
            ("count", "Assigned SKUs", "{:>8d}"),
            ("coverage", "Coverage (%)", "{:>7.1f}%"),
            ("mean_dist", "Mean Distance", "{:>8.2f}"),
            ("sum_dist", "Total Distance", "{:>8.0f}"),
            ("violations", "Safety Violations", "{:>8d}"),
            ("heavy_total", "Heavy Items", "{:>8d}"),
            ("heavy_high", "Heavy on High", "{:>8d}"),
            ("lower_rack_pct", "Levels 0-1 (%)", "{:>7.1f}%"),
        ]

        for key, label, fmt in metrics:
            print(f"  {label:<30}", end="")
            for h in headers:
                val = results[h].get(key, 0)
                print(f" | {fmt.format(val)}", end="")
            print()

    print(f"\n{'=' * 80}")
    print("  EVALUATION COMPLETE")
    print(f"{'=' * 80}")
