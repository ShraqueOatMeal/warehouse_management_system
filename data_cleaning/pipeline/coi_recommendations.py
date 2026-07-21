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
                "Primary_Location" as "CurrentLocation",
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
                "Primary_Location" as "CurrentLocation",
                "zone",
                "is_cold_room"
            FROM optimization_master
        """

    df = pl.read_database_uri(query, uri)
    df = df.with_columns(
        coi_score=(pl.col("Cubic_Vol_Fixed") / (pl.col("Total_Hits") + 0.1))
    )
    return df.sort("coi_score")


def get_recommendations(target_stock_codes):
    """
    Returns top 5 recommended slots for each target SKU.
    Does NOT modify the database.
    """
    uri_pg = get_pg_connection_uri()
    print(f"--- Generating Recommendations for {len(target_stock_codes)} SKUs ---")

    # 1. Load All Slots and Reality
    all_slots_df = generate_location_master()
    reality_query = """
        SELECT 
            "StockCode", "Description", "refined_category", "Height_Fixed",
            "Primary_Location_Fixed" as "location_id"
        FROM optimization_master 
    """
    reality_df = pl.read_database_uri(reality_query, uri_pg)

    # Baseline: Items correctly mapped to 3D racks (for safety positions and slot blocking)
    baseline_df = reality_df.join(all_slots_df, on="location_id", how="inner")

    # Identify empty slots
    used_slot_ids = baseline_df["location_id"].to_list()
    available_slots = all_slots_df.filter(~pl.col("location_id").is_in(used_slot_ids))

    # Load SKUs to recommend for
    to_recommend = load_sku_data(uri_pg, target_stock_codes)

    # --- Robust Zone Assignment ---
    VALID_ZONES = ["INSIDE_STORAGE", "OUTSIDE", "COLD_ROOM_HDL", "COLD_ROOM_MIX"]
    if not to_recommend.is_empty():
        to_recommend = to_recommend.with_columns(
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

        to_recommend = to_recommend.with_columns(
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

    # Safety Positions from baseline
    fixed_haz = baseline_df.filter(
        pl.col("refined_category").is_in(["Chemical", "Hazardous"])
    )
    fixed_food = baseline_df.filter(pl.col("refined_category") == "Food-Grade")
    haz_positions = fixed_haz.select(["x", "z", "prefix"]).to_dicts()
    food_positions = fixed_food.select(["x", "z", "prefix"]).to_dicts()

    recommendations = {}

    for sku in to_recommend.to_dicts():
        zone = sku["zone"]
        is_haz = sku["refined_category"] in ["Chemical", "Hazardous"]
        is_food = sku["refined_category"] == "Food-Grade"

        # Get slots in the right zone, sorted by distance
        zone_slots = (
            available_slots.filter(pl.col("zone") == zone)
            .sort("dist_to_bay")
            .to_dicts()
        )

        sku_recs = []
        for slot in zone_slots:
            conflict = False
            # Check against FIXED items (reality)
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
                sku_recs.append(slot["location_id"])
                if len(sku_recs) >= 5:
                    break

        if len(sku_recs) < 5 and zone == "COLD_ROOM_MIX":
            hdl_slots = (
                available_slots.filter(pl.col("zone") == "COLD_ROOM_HDL")
                .sort("dist_to_bay")
                .to_dicts()
            )
            for slot in hdl_slots:
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
                    sku_recs.append(slot["location_id"])
                    if len(sku_recs) >= 5:
                        break

        recommendations[sku["StockCode"]] = sku_recs

    return recommendations


if __name__ == "__main__":
    if len(sys.argv) > 1:
        try:
            stocks = json.loads(sys.argv[1])
            # For this new "Recommendation" mode, we'll just print the JSON result
            recs = get_recommendations(target_stock_codes=stocks)
            print("REC_RESULT:" + json.dumps(recs))
        except Exception as e:
            print(f"Error: {e}")
    else:
        # If run without args, maybe we still do the full sync for backward compat or testing
        pass
