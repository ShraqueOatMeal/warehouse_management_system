import polars as pl


def generate_location_master():
    locations = []

    # 1. COLD ROOM: MIX (FE, FF, FG, FH)
    cold_room_mix_aisles = ["FE", "FF", "FG", "FH"]
    x_offset_mix = -20
    for a_idx, prefix in enumerate(cold_room_mix_aisles):
        for area in range(1, 21):  # 1 to 20
            for level in range(1, 6):  # 1 to 5
                # Front Position
                locations.append(
                    {
                        "location_id": f"{prefix}-{area:02d}-{level * 10}",
                        "zone": "COLD_ROOM_MIX",
                        "prefix": prefix,
                        "x": x_offset_mix + (a_idx * 5),
                        "y": (level - 1) * 1.6,
                        "z": (area * 1.5) - 15,
                        "level": level - 1,
                        "depth": "Front"
                    }
                )
                # Back Position (Double Deep)
                locations.append(
                    {
                        "location_id": f"{prefix}-{area:02d}-{level * 10}-B",
                        "zone": "COLD_ROOM_MIX",
                        "prefix": prefix,
                        "x": x_offset_mix + (a_idx * 5) + 1.2, # Shifted back
                        "y": (level - 1) * 1.6,
                        "z": (area * 1.5) - 15,
                        "level": level - 1,
                        "depth": "Back"
                    }
                )

    # 2. COLD ROOM: HDL (FA, FB, FC, FD)
    cold_room_hdl_aisles = ["FA", "FB", "FC", "FD"]
    x_offset_hdl = -50
    for a_idx, prefix in enumerate(cold_room_hdl_aisles):
        for area in range(1, 21):
            for level in range(1, 6):
                # Front Position
                locations.append(
                    {
                        "location_id": f"{prefix}-{area:02d}-{level * 10}",
                        "zone": "COLD_ROOM_HDL",
                        "prefix": prefix,
                        "x": x_offset_hdl + (a_idx * 5),
                        "y": (level - 1) * 1.6,
                        "z": (area * 1.5) - 15,
                        "level": level - 1,
                        "depth": "Front"
                    }
                )
                # Back Position (Double Deep)
                locations.append(
                    {
                        "location_id": f"{prefix}-{area:02d}-{level * 10}-B",
                        "zone": "COLD_ROOM_HDL",
                        "prefix": prefix,
                        "x": x_offset_hdl + (a_idx * 5) + 1.2,
                        "y": (level - 1) * 1.6,
                        "z": (area * 1.5) - 15,
                        "level": level - 1,
                        "depth": "Back"
                    }
                )

    # 3. OUTSIDE: D, C, B, A
    outside_aisles = ["D1", "C1", "B1", "A1"]
    x_offset_outside = 5
    for a_idx, prefix in enumerate(outside_aisles):
        for area in range(1, 23):  # 1 to 22
            for level in range(1, 6):
                locations.append(
                    {
                        "location_id": f"{prefix}-{area:02d}-{level * 10}",
                        "zone": "OUTSIDE",
                        "prefix": prefix,
                        "x": x_offset_outside + (a_idx * 6),
                        "y": (level - 1) * 1.6,
                        "z": (area * 1.5) - 15,
                        "level": level - 1,
                        "depth": "Front"
                    }
                )

    # 4. INSIDE: LGF, H, G, F, E, D, C, B, A, Y
    inside_aisles = ["LGF", "H", "G", "F", "E", "D", "C", "B", "A", "Y"]
    current_x = 5
    for prefix in inside_aisles:
        max_areas = 22
        for area in range(1, max_areas + 1):
            for level in range(1, 6):
                locations.append(
                    {
                        "location_id": f"{prefix}-{area:02d}-{level * 10}",
                        "zone": "INSIDE_STORAGE",
                        "prefix": prefix,
                        "x": current_x,
                        "z": (area * 1.5) - 15,
                        "y": (level - 1) * 1.6,
                        "level": level - 1,
                        "depth": "Front"
                    }
                )
        # Dynamic X spacing logic from your TypeScript
        if prefix in ["A", "Y", "LGF"]:
            current_x += 12
        else:
            current_x += 6

    df_locations = pl.DataFrame(locations)

    # --- STEP 4: ZONE-SPECIFIC DISTANCE LOGIC ---
    # Define door/bay locations based on user input
    # Area 01 Z-coordinate: (1 * 1.5) - 15 = -13.5
    Z_FRONT = -13.5

    # Inside Doors: Between LGF (5) & H (17) -> X=11; Between A (59) & Y (71) -> X=65
    DOOR_INSIDE_1_X = 11
    DOOR_INSIDE_2_X = 65

    # Cold Room Doors: Between FF (-15) & FG (-10) -> X=-12.5; Between FB (-45) & FC (-40) -> X=-42.5
    DOOR_MIX_X = -12.5
    DOOR_HDL_X = -42.5

    df_locations = df_locations.with_columns(
        dist_to_bay=pl.when(pl.col("zone") == "INSIDE_STORAGE")
        .then(
            pl.min_horizontal(
                (pl.col("x") - DOOR_INSIDE_1_X).abs(),
                (pl.col("x") - DOOR_INSIDE_2_X).abs(),
            )
            + (pl.col("z") - Z_FRONT).abs()
            + pl.col("y")
        )
        .when(pl.col("zone") == "COLD_ROOM_MIX")
        .then(
            (pl.col("x") - DOOR_MIX_X).abs()
            + (pl.col("z") - Z_FRONT).abs()
            + pl.col("y")
            + pl.when(pl.col("depth") == "Back").then(5.0).otherwise(0.0) # Penalty for back
        )
        .when(pl.col("zone") == "COLD_ROOM_HDL")
        .then(
            (pl.col("x") - DOOR_HDL_X).abs()
            + (pl.col("z") - Z_FRONT).abs()
            + pl.col("y")
            + pl.when(pl.col("depth") == "Back").then(5.0).otherwise(0.0) # Penalty for back
        )
        .when(pl.col("zone") == "OUTSIDE")
        .then(
            (pl.col("z") - Z_FRONT).abs() + pl.col("y")
        )  # Lorry passes through at Area 01 for each aisle
        .otherwise(0.0)
    )

    return df_locations


if __name__ == "__main__":
    # Create the master dataframe
    df_locations = generate_location_master()

    print(f"Generated {len(df_locations)} total storage bins.")
    print(df_locations.head())
