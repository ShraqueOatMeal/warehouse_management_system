import polars as pl
from db_utils import get_pg_connection_uri
from location_master import generate_location_master
import sys
import json


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
    return df.sort("coi_score")


def run_coi_optimization(target_stock_codes=None, reoptimize_all=False):
    uri_pg = get_pg_connection_uri()

    if reoptimize_all:
        mode_str = "Complete Re-optimization (Entire Stock)"
    else:
        mode_str = "Targeted" if target_stock_codes else "Strict Incremental"
    print(f"--- Starting {mode_str} Safety-Aware Per-Zone COI Optimization ---")

    # 1. Load All Possible Slots
    all_slots_df = generate_location_master()
    valid_slot_ids = all_slots_df["location_id"].to_list()

    # 2. Identify Current Reality (Aligned with UI which uses Cured_Location)
    reality_query = """
        SELECT 
            "StockCode", "Description", "refined_category", "Height_Fixed", "Weight_Fixed",
            "Cured_Location" as "location_id"
        FROM optimization_master 
    """
    reality_df = pl.read_database_uri(reality_query, uri_pg)

    if reoptimize_all:
        # For complete re-optimization, there is no fixed baseline because everything can move.
        # We start with an empty baseline but preserve the schema.
        baseline_df = reality_df.clear().join(
            all_slots_df.clear(), on="location_id", how="inner"
        )
        slotted_stock_codes = []
        used_slot_ids = []
    else:
        # Baseline: Filter for items in valid 3D slots AND JOIN with all_slots_df for correct prefix/coords/zone
        baseline_df = reality_df.join(all_slots_df, on="location_id", how="inner")
        if target_stock_codes:
            baseline_df = baseline_df.filter(
                ~pl.col("StockCode").is_in(target_stock_codes)
            )
        slotted_stock_codes = baseline_df["StockCode"].to_list()
        used_slot_ids = baseline_df["location_id"].to_list()

    print(f"  Fixed Baseline: {len(baseline_df)} items correctly mapped to 3D racks.")

    # 3. Identify SKUs to Optimize
    all_potential = load_sku_data(uri_pg, target_stock_codes)

    if reoptimize_all:
        # In complete optimization, we optimize ALL items that are currently in the warehouse.
        to_optimize = all_potential
    elif target_stock_codes:
        # In targeted optimization, we specifically slot the requested items
        to_optimize = all_potential
    else:
        # FILTER: Only optimize items that are truly unassigned
        # We ignore items that are already in racks (slotted_stock_codes)
        # AND we ignore items that have a non-rack location (FREE ZONE, FLOOR, etc.)
        to_optimize = all_potential.filter(
            (pl.col("CurrentLocation").is_null())
            | (pl.col("CurrentLocation") == "")
            | (pl.col("CurrentLocation").str.contains("UNASSIGNED"))
        ).filter(~pl.col("StockCode").is_in(slotted_stock_codes))

    print(f"  Target SKUs: {len(to_optimize)} items awaiting rack assignment.")

    # 4. Identify Available Slots
    available_slots = all_slots_df.filter(~pl.col("location_id").is_in(used_slot_ids))
    print(f"  Available Slots: {len(available_slots)} empty bins.")

    # Robust Zone Assignment for unassigned items
    VALID_ZONES = ["INSIDE_STORAGE", "OUTSIDE", "COLD_ROOM_HDL", "COLD_ROOM_MIX"]

    if not to_optimize.is_empty():
        # Map based on prefix if present, otherwise default by cold_room flag
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

    # 5. Safety Constraints (Fixed Positions)
    fixed_haz = baseline_df.filter(
        pl.col("refined_category").is_in(["Chemical", "Hazardous"])
    )
    fixed_food = baseline_df.filter(pl.col("refined_category") == "Food-Grade")

    haz_positions = fixed_haz.select(["x", "z", "prefix"]).to_dicts()
    food_positions = fixed_food.select(["x", "z", "prefix"]).to_dicts()

    # 6. Optimize Per Zone with Safety
    results = []
    if not to_optimize.is_empty():
        zones = to_optimize["zone"].unique().to_list()
        if "COLD_ROOM_MIX" in zones and "COLD_ROOM_HDL" in zones:
            zones.remove("COLD_ROOM_MIX")
            zones.insert(0, "COLD_ROOM_MIX")

        hdl_slots = (
            available_slots.filter(pl.col("zone") == "COLD_ROOM_HDL")
            .sort("dist_to_bay")
            .to_dicts()
        )

        for zone in zones:
            if zone is None:
                continue
            print(f"  Optimizing zone: {zone}...")
            # Sort by safety tier (1: Haz, 2: Food, 3: Normal) to prevent "checkerboarding" and overlapping exclusion zones, then by COI score
            zone_skus_df = to_optimize.filter(pl.col("zone") == zone)
            zone_skus_df = zone_skus_df.with_columns(
                safety_tier=pl.when(
                    pl.col("refined_category").is_in(["Chemical", "Hazardous"])
                )
                .then(1)
                .when(pl.col("refined_category") == "Food-Grade")
                .then(2)
                .otherwise(3)
            )
            zone_skus = zone_skus_df.sort(["safety_tier", "coi_score"]).to_dicts()

            if zone == "COLD_ROOM_HDL":
                zone_slots = hdl_slots
            else:
                zone_slots = (
                    available_slots.filter(pl.col("zone") == zone)
                    .sort("dist_to_bay")
                    .to_dicts()
                )

            assignments = []
            batch_haz = []
            batch_food = []

            for sku in zone_skus:
                is_haz = sku["refined_category"] in ["Chemical", "Hazardous"]
                is_food = sku["refined_category"] == "Food-Grade"
                try:
                    weight_val = float(sku.get("Weight_Fixed") or 0.0)
                except Exception:
                    weight_val = 0.0
                is_heavy = weight_val >= 500.0

                target_idx = -1
                for i, slot in enumerate(zone_slots):
                    # Strict Weight Check: Heavier items (>= 500kg) must stay at bottom tier (Level 0 or Level 1)
                    if is_heavy and slot.get("level", 0) > 1:
                        continue
                    conflict = False
                    if is_haz:
                        for pos in food_positions:
                            if (
                                slot["prefix"] == pos["prefix"]
                                and (
                                    (slot["x"] - pos["x"]) ** 2
                                    + (slot["z"] - pos["z"]) ** 2
                                )
                                ** 0.5
                                < 3.0
                            ):
                                conflict = True
                                break
                    elif is_food:
                        for pos in haz_positions:
                            if (
                                slot["prefix"] == pos["prefix"]
                                and (
                                    (slot["x"] - pos["x"]) ** 2
                                    + (slot["z"] - pos["z"]) ** 2
                                )
                                ** 0.5
                                < 3.0
                            ):
                                conflict = True
                                break

                    if not conflict:
                        if is_haz:
                            for fx, fz, fpref in batch_food:
                                if (
                                    slot["prefix"] == fpref
                                    and ((slot["x"] - fx) ** 2 + (slot["z"] - fz) ** 2)
                                    ** 0.5
                                    < 3.0
                                ):
                                    conflict = True
                                    break
                        elif is_food:
                            for hx, hz, hpref in batch_haz:
                                if (
                                    slot["prefix"] == hpref
                                    and ((slot["x"] - hx) ** 2 + (slot["z"] - hz) ** 2)
                                    ** 0.5
                                    < 3.0
                                ):
                                    conflict = True
                                    break

                    if not conflict:
                        target_idx = i
                        break

                used_hdl = False
                if target_idx == -1 and zone == "COLD_ROOM_MIX":
                    for i, slot in enumerate(hdl_slots):
                        if is_heavy and slot.get("level", 0) > 1:
                            continue
                        conflict = False
                        if is_haz:
                            for pos in food_positions:
                                if (
                                    slot["prefix"] == pos["prefix"]
                                    and ((slot["x"] - pos["x"]) ** 2 + (slot["z"] - pos["z"]) ** 2)
                                    ** 0.5
                                    < 3.0
                                ):
                                    conflict = True
                                    break
                        elif is_food:
                            for pos in haz_positions:
                                if (
                                    slot["prefix"] == pos["prefix"]
                                    and ((slot["x"] - pos["x"]) ** 2 + (slot["z"] - pos["z"]) ** 2)
                                    ** 0.5
                                    < 3.0
                                ):
                                    conflict = True
                                    break
                        if not conflict:
                            if is_haz:
                                for fx, fz, fpref in batch_food:
                                    if (
                                        slot["prefix"] == fpref
                                        and ((slot["x"] - fx) ** 2 + (slot["z"] - fz) ** 2)
                                        ** 0.5
                                        < 3.0
                                    ):
                                        conflict = True
                                        break
                            elif is_food:
                                for hx, hz, hpref in batch_haz:
                                    if (
                                        slot["prefix"] == hpref
                                        and ((slot["x"] - hx) ** 2 + (slot["z"] - hz) ** 2)
                                        ** 0.5
                                        < 3.0
                                    ):
                                        conflict = True
                                        break
                        if not conflict:
                            target_idx = i
                            used_hdl = True
                            break

                if target_idx != -1:
                    if used_hdl:
                        slot = hdl_slots.pop(target_idx)
                    else:
                        slot = zone_slots.pop(target_idx)
                    if is_haz:
                        batch_haz.append((slot["x"], slot["z"], slot["prefix"]))
                    if is_food:
                        batch_food.append((slot["x"], slot["z"], slot["prefix"]))
                    slot.update(sku)
                    if used_hdl:
                        slot["zone"] = "COLD_ROOM_HDL"
                    assignments.append(slot)

            if assignments:
                results.append(pl.DataFrame(assignments))

    # 4. Finalize
    if results:
        new_assignments_df = pl.concat(results)
        if baseline_df.is_empty():
            final_layout = new_assignments_df
        else:
            final_layout = pl.concat([baseline_df, new_assignments_df], how="diagonal")
    else:
        final_layout = baseline_df

    # 5. Save
    if not final_layout.is_empty():
        columns_to_keep = [
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
            [c for c in columns_to_keep if c in final_layout.columns]
        )

        final_layout.write_database(
            table_name="proposed_layout_coi",
            connection=uri_pg,
            if_table_exists="replace",
            engine="adbc",
        )
        if reoptimize_all:
            print(
                f"Complete re-optimization complete. Optimized {len(final_layout)} total SKUs."
            )
        else:
            print(
                f"Targeted optimization complete. Reality ({len(baseline_df)}) + New ({len(final_layout) - len(baseline_df)}) = {len(final_layout)} total SKUs."
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

    run_coi_optimization(
        target_stock_codes=target_stocks, reoptimize_all=reoptimize_all
    )
