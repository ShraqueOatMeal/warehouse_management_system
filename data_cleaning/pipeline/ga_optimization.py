import polars as pl
import numpy as np
from db_utils import get_pg_connection_uri
from location_master import generate_location_master
import sys
import json
import random


def load_sku_data(uri, target_stock_codes=None):
    """Loads SKU performance data for optimization."""
    if target_stock_codes:
        placeholders = ",".join([f"'{sc}'" for sc in target_stock_codes])
        query = f"""
            SELECT
                "StockCode",
                "Description",
                "refined_category",
                "Total_Hits",
                "Cubic_Vol_Fixed",
                "Height_Fixed",
                "Weight_Fixed",
                "Cured_Location" as "CurrentLocation",
                "zone",
                "is_cold_room"
            FROM optimization_master
            WHERE "StockCode" IN ({placeholders})
        """
    else:
        query = """
            SELECT
                "StockCode",
                "Description",
                "refined_category",
                "Total_Hits",
                "Cubic_Vol_Fixed",
                "Height_Fixed",
                "Weight_Fixed",
                "Cured_Location" as "CurrentLocation",
                "zone",
                "is_cold_room"
            FROM optimization_master
        """
    df = pl.read_database_uri(query, uri)
    df = df.with_columns(
        coi_score=(pl.col("Cubic_Vol_Fixed") / (pl.col("Total_Hits") + 0.1))
    )
    return df


def evolve_zone_ga(
    zone_skus, zone_slots, base_haz=None, base_food=None, pop_size=20, generations=25
):
    """Runs Memetic Genetic Algorithm to evolve optimal slotting for a single zone."""
    if len(zone_skus) > len(zone_slots):
        zone_skus = zone_skus[: len(zone_slots)]
    num_skus = len(zone_skus)
    num_slots = len(zone_slots)

    if num_skus == 0 or num_slots == 0:
        return []

    # Sort zone_skus by safety tier and coi_score for deterministic Heuristic Seeding
    def get_tier(sku):
        cat = sku.get("refined_category", "")
        if cat in ["Chemical", "Hazardous"]:
            return 1
        if cat == "Food-Grade":
            return 2
        return 3

    zone_skus = sorted(
        zone_skus, key=lambda s: (get_tier(s), float(s.get("coi_score") or 0.0))
    )

    # Extract NumPy arrays for fast vectorized fitness evaluation
    sku_hits = np.array([float(s.get("Total_Hits") or 1.0) for s in zone_skus])
    sku_weights = np.array([float(s.get("Weight_Fixed") or 0.0) for s in zone_skus])
    is_heavy = sku_weights >= 500.0

    cats = [s.get("refined_category", "") for s in zone_skus]
    is_chem = np.array([c in ["Chemical", "Hazardous"] for c in cats])
    is_food = np.array([c == "Food-Grade" for c in cats])

    slot_x = np.array([float(s["x"]) for s in zone_slots])
    slot_z = np.array([float(s["z"]) for s in zone_slots])
    slot_level = np.array([int(s["level"]) for s in zone_slots])
    slot_dist = np.array([float(s["dist_to_bay"]) for s in zone_slots])
    slot_pref = np.array([s["prefix"] for s in zone_slots])

    bh_list = base_haz or []
    bf_list = base_food or []

    # Initialize Population (Array of bin indices for each SKU)
    population = []

    # Seed 0: Heuristic COI Safe Assignment (Warm Start)
    seed_0 = np.full(num_skus, -1, dtype=int)
    used_seed_slots = set()

    for i in range(num_skus):
        chem_i = is_chem[i]
        food_i = is_food[i]
        heavy_i = is_heavy[i]

        chosen_j = -1
        for j in range(num_slots):
            if j in used_seed_slots:
                continue
            if heavy_i and slot_level[j] > 1:
                continue

            s_pref = slot_pref[j]
            s_x = slot_x[j]
            s_z = slot_z[j]
            conflict = False

            if chem_i:
                for bf in bf_list:
                    if (
                        s_pref == bf["prefix"]
                        and ((s_x - bf["x"]) ** 2 + (s_z - bf["z"]) ** 2) < 9.0
                    ):
                        conflict = True
                        break
                if not conflict:
                    for k in range(i):
                        if is_food[k] and seed_0[k] != -1:
                            sj = seed_0[k]
                            if (
                                s_pref == slot_pref[sj]
                                and ((s_x - slot_x[sj]) ** 2 + (s_z - slot_z[sj]) ** 2)
                                < 9.0
                            ):
                                conflict = True
                                break
            elif food_i:
                for bh in bh_list:
                    if (
                        s_pref == bh["prefix"]
                        and ((s_x - bh["x"]) ** 2 + (s_z - bh["z"]) ** 2) < 9.0
                    ):
                        conflict = True
                        break
                if not conflict:
                    for k in range(i):
                        if is_chem[k] and seed_0[k] != -1:
                            sj = seed_0[k]
                            if (
                                s_pref == slot_pref[sj]
                                and ((s_x - slot_x[sj]) ** 2 + (s_z - slot_z[sj]) ** 2)
                                < 9.0
                            ):
                                conflict = True
                                break
            if not conflict:
                chosen_j = j
                break

        if chosen_j != -1:
            seed_0[i] = chosen_j
            used_seed_slots.add(chosen_j)
        else:
            avail = [x for x in range(num_slots) if x not in used_seed_slots]
            if avail:
                chosen_j = avail[0]
                seed_0[i] = chosen_j
                used_seed_slots.add(chosen_j)

    population.append(seed_0)

    # Seed rest: Random permutations
    for _ in range(pop_size - 1):
        ind = np.random.choice(num_slots, size=num_skus, replace=False)
        population.append(ind)

    def calc_fitness(gene):
        b_dist = slot_dist[gene]
        b_level = slot_level[gene]
        b_x = slot_x[gene]
        b_z = slot_z[gene]
        b_pref = slot_pref[gene]

        # Objective 1: Travel Cost
        travel_cost = np.sum(sku_hits * b_dist)

        # Objective 2: Heavy Pallet Floor Penalty
        floor_penalty = np.sum(is_heavy & (b_level > 1)) * 100000.0

        # Objective 3: Digital Conflict Matrix (Chemical vs Food < 3.0m)
        chem_idx = np.where(is_chem)[0]
        food_idx = np.where(is_food)[0]
        safety_violations = 0

        # Internal newly evolving conflicts
        if len(chem_idx) > 0 and len(food_idx) > 0:
            c_pref = b_pref[chem_idx]
            f_pref = b_pref[food_idx]
            same_pref = c_pref[:, None] == f_pref[None, :]
            dx = b_x[chem_idx, None] - b_x[food_idx][None, :]
            dz = b_z[chem_idx, None] - b_z[food_idx][None, :]
            dist_sq = dx * dx + dz * dz
            safety_violations += np.sum(same_pref & (dist_sq < 9.0))

        # Baseline static inventory conflicts
        if len(chem_idx) > 0 and len(bf_list) > 0:
            bf_x = np.array([f["x"] for f in bf_list])
            bf_z = np.array([f["z"] for f in bf_list])
            bf_pref = np.array([f["prefix"] for f in bf_list])
            c_pref = b_pref[chem_idx]
            same_pref = c_pref[:, None] == bf_pref[None, :]
            dx = b_x[chem_idx, None] - bf_x[None, :]
            dz = b_z[chem_idx, None] - bf_z[None, :]
            safety_violations += np.sum(same_pref & ((dx * dx + dz * dz) < 9.0))

        if len(food_idx) > 0 and len(bh_list) > 0:
            bh_x = np.array([h["x"] for h in bh_list])
            bh_z = np.array([h["z"] for h in bh_list])
            bh_pref = np.array([h["prefix"] for h in bh_list])
            f_pref = b_pref[food_idx]
            same_pref = f_pref[:, None] == bh_pref[None, :]
            dx = b_x[food_idx, None] - bh_x[None, :]
            dz = b_z[food_idx, None] - bh_z[None, :]
            safety_violations += np.sum(same_pref & ((dx * dx + dz * dz) < 9.0))

        safety_penalty = safety_violations * 500000.0
        return -(travel_cost + floor_penalty + safety_penalty)

    # Evolution Loop
    for g in range(generations):
        fitnesses = np.array([calc_fitness(ind) for ind in population])

        sorted_indices = np.argsort(fitnesses)[::-1]
        population = [population[i] for i in sorted_indices]

        # Elitism: Keep top 2
        new_pop = [population[0].copy(), population[1].copy()]

        while len(new_pop) < pop_size:
            # Tournament Selection
            t1 = np.random.choice(pop_size, size=3)
            p1 = population[np.min(t1)]
            t2 = np.random.choice(pop_size, size=3)
            p2 = population[np.min(t2)]

            # Order Crossover (OX)
            if num_skus > 1:
                c1, c2 = sorted(np.random.choice(num_skus, size=2, replace=False))
                child = np.full(num_skus, -1, dtype=int)
                child[c1:c2] = p1[c1:c2]
                used_slots = set(child[c1:c2])

                ptr = 0
                for s_idx in p2:
                    if s_idx not in used_slots:
                        while ptr >= c1 and ptr < c2:
                            ptr += 1
                        if ptr < num_skus:
                            child[ptr] = s_idx
                            used_slots.add(s_idx)
                            ptr += 1
                if np.any(child == -1):
                    missing = [b for b in range(num_slots) if b not in used_slots]
                    child[child == -1] = missing[: np.sum(child == -1)]
            else:
                child = p1.copy()

            # Mutation: Swap 2 slots
            if random.random() < 0.25 and num_skus > 1:
                m1, m2 = np.random.choice(num_skus, size=2, replace=False)
                child[m1], child[m2] = child[m2], child[m1]

            new_pop.append(child)
        population = new_pop

    final_fits = [calc_fitness(ind) for ind in population]
    best_ind = population[np.argmax(final_fits)]

    assignments = []
    appended_food = bf_list.copy()
    appended_haz = bh_list.copy()

    for s_idx, b_idx in zip(range(num_skus), best_ind):
        slot = zone_slots[b_idx].copy()
        sku = zone_skus[s_idx]

        cat = sku.get("refined_category", "")
        is_h = cat in ["Chemical", "Hazardous"]
        is_f = cat == "Food-Grade"
        is_hvy = float(sku.get("Weight_Fixed") or 0.0) >= 500.0

        s_pref = slot["prefix"]
        s_x = float(slot["x"])
        s_z = float(slot["z"])
        s_lvl = int(slot["level"])
        conflict = False

        if is_hvy and s_lvl > 1:
            conflict = True
        elif is_h:
            for af in appended_food:
                if (
                    s_pref == af["prefix"]
                    and ((s_x - float(af["x"])) ** 2 + (s_z - float(af["z"])) ** 2)
                    < 9.0
                ):
                    conflict = True
                    break
        elif is_f:
            for ah in appended_haz:
                if (
                    s_pref == ah["prefix"]
                    and ((s_x - float(ah["x"])) ** 2 + (s_z - float(ah["z"])) ** 2)
                    < 9.0
                ):
                    conflict = True
                    break

        if not conflict:
            slot.update(sku)
            assignments.append(slot)
            if is_h:
                appended_haz.append({"x": s_x, "z": s_z, "prefix": s_pref})
            if is_f:
                appended_food.append({"x": s_x, "z": s_z, "prefix": s_pref})

    return assignments


def run_ga_optimization(target_stock_codes=None, reoptimize_all=False):
    uri_pg = get_pg_connection_uri()

    mode_str = (
        "Complete GA Re-optimization"
        if reoptimize_all
        else "Targeted/Incremental GA Optimizer"
    )
    print(f"--- Starting {mode_str} (Memetic Travel vs Safety Tradeoff) ---")

    all_slots_df = generate_location_master()
    reality_query = """
        SELECT "StockCode", "Description", "refined_category", "Height_Fixed", "Weight_Fixed",
               "Cured_Location" as "location_id"
        FROM optimization_master 
    """
    reality_df = pl.read_database_uri(reality_query, uri_pg)

    if reoptimize_all:
        baseline_df = reality_df.clear().join(
            all_slots_df.clear(), on="location_id", how="inner"
        )
        used_slot_ids = []
    else:
        baseline_df = reality_df.join(all_slots_df, on="location_id", how="inner")
        if target_stock_codes:
            baseline_df = baseline_df.filter(
                ~pl.col("StockCode").is_in(target_stock_codes)
            )
        slotted_stock_codes = baseline_df["StockCode"].to_list()
        used_slot_ids = baseline_df["location_id"].to_list()

    all_potential = load_sku_data(uri_pg, target_stock_codes)

    if reoptimize_all:
        to_optimize = all_potential
    elif target_stock_codes:
        to_optimize = all_potential
    else:
        to_optimize = all_potential.filter(
            (pl.col("CurrentLocation").is_null())
            | (pl.col("CurrentLocation") == "")
            | (pl.col("CurrentLocation").str.contains("UNASSIGNED"))
        ).filter(~pl.col("StockCode").is_in(slotted_stock_codes))

    available_slots = all_slots_df.filter(~pl.col("location_id").is_in(used_slot_ids))

    VALID_ZONES = ["INSIDE_STORAGE", "OUTSIDE", "COLD_ROOM_HDL", "COLD_ROOM_MIX"]
    if not to_optimize.is_empty():
        to_optimize = to_optimize.with_columns(
            new_zone=pl.when(
                pl.col("refined_category").is_in(["Electronics", "Chemical", "Hazardous"])
            )
            .then(
                pl.when(pl.col("CurrentLocation").str.contains(r"^[ABCD]1"))
                .then(pl.lit("OUTSIDE"))
                .otherwise(pl.lit("INSIDE_STORAGE"))
            )
            .when(
                (pl.col("is_cold_room") == True)
                | (
                    pl.col("Description")
                    .str.to_uppercase()
                    .str.contains(r"\b(FROZEN|CHILLED|COLD|ICE CREAM)\b")
                )
                | pl.col("CurrentLocation").str.contains(r"^F[A-H]-")
            )
            .then(pl.lit("COLD_ROOM_MIX"))
            .when(pl.col("CurrentLocation").str.contains(r"^[ABCD]1"))
            .then(pl.lit("OUTSIDE"))
            .otherwise(pl.lit("INSIDE_STORAGE"))
        )
        to_optimize = to_optimize.with_columns(
            zone=pl.when(
                pl.col("refined_category").is_in(["Electronics", "Chemical", "Hazardous"])
            )
            .then(pl.col("new_zone"))
            .when(
                (pl.col("is_cold_room") == True)
                | (
                    pl.col("Description")
                    .str.to_uppercase()
                    .str.contains(r"\b(FROZEN|CHILLED|COLD|ICE CREAM)\b")
                )
                | pl.col("CurrentLocation").str.contains(r"^F[A-H]-")
            )
            .then(pl.col("new_zone"))
            .when((pl.col("zone").is_null()) | (~pl.col("zone").is_in(VALID_ZONES)))
            .then(pl.col("new_zone"))
            .otherwise(pl.col("zone"))
        ).drop("new_zone")

    base_haz_all = []
    base_food_all = []
    if not baseline_df.is_empty():
        base_haz_all = (
            baseline_df.filter(
                pl.col("refined_category").is_in(["Chemical", "Hazardous"])
            )
            .select(["x", "z", "prefix", "zone"])
            .to_dicts()
        )
        base_food_all = (
            baseline_df.filter(pl.col("refined_category") == "Food-Grade")
            .select(["x", "z", "prefix", "zone"])
            .to_dicts()
        )

    results = []
    if not to_optimize.is_empty():
        zones = to_optimize["zone"].unique().to_list()
        for zone in zones:
            if zone is None:
                continue
            print(f"  Evolving Memetic GA population for zone: {zone}...")
            z_skus = to_optimize.filter(pl.col("zone") == zone).to_dicts()
            z_slots = available_slots.filter(pl.col("zone") == zone).to_dicts()

            bh_z = [h for h in base_haz_all if h.get("zone") == zone]
            bf_z = [f for f in base_food_all if f.get("zone") == zone]

            z_assigned = evolve_zone_ga(
                z_skus, z_slots, bh_z, bf_z, pop_size=16, generations=20
            )
            if z_assigned:
                results.append(pl.DataFrame(z_assigned))

    if results:
        new_assignments_df = pl.concat(results)
        final_layout = (
            pl.concat([baseline_df, new_assignments_df], how="diagonal")
            if not baseline_df.is_empty()
            else new_assignments_df
        )
    else:
        final_layout = baseline_df

    if not final_layout.is_empty():
        cols = [
            "location_id",
            "StockCode",
            "Description",
            "refined_category",
            "Height_Fixed",
            "Weight_Fixed",
            "zone",
            "prefix",
            "x",
            "y",
            "z",
            "depth",
        ]
        final_layout = final_layout.select(
            [c for c in cols if c in final_layout.columns]
        )
        final_layout.write_database(
            table_name="proposed_layout_ga",
            connection=uri_pg,
            if_table_exists="replace",
            engine="adbc",
        )
        print(
            f"GA Evolution complete. Evolved optimal memetic layout for {len(final_layout)} SKUs."
        )

    return final_layout


if __name__ == "__main__":
    reoptimize_all = False
    target_stocks = None
    for arg in sys.argv[1:]:
        if arg == "--complete":
            reoptimize_all = True
        else:
            try:
                target_stocks = json.loads(arg)
            except Exception:
                pass
    run_ga_optimization(target_stock_codes=target_stocks, reoptimize_all=reoptimize_all)
