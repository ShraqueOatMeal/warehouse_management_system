import polars as pl


def impute_dimensions(df: pl.DataFrame) -> pl.DataFrame:
    """
    Imputes specific Width, Height, and Depth based on the product category
    to support constraint-based slotting and Digital Twin visualization.
    """

    STANDARD_WIDTH = 1.2
    STANDARD_DEPTH = 1.0

    # Validation Window: A standard racking slot is ~1.92 m3 (1.2m x 1.0m x 1.6m)
    # Volumes below 0.1 m3 are likely single cartons.
    # Volumes above 2.4 m3 are likely bulk shipments or bundles.
    MIN_STORAGE_VOLUME = 0.1
    MAX_STORAGE_VOLUME = 2.4

    SUB_UNITS = [
        "PKG",
        "PKGS",
        "PCS",
        "UNIT",
        "UNITS",
        "BTL",
        "BAG",
        "PAIL",
        "TINS",
        "CARTON",
        "CTN",
        "CARS",
        "BOX",
        "CASE",
        "CASES",
    ]
    LIQUID_CONTAINERS = ["IBC", "DRUM", "JERRY CAN", "TONG", "HDPE DRUM"]
    MEDIUM_CONTAINERS = ["PAIL", "TIN", "TINS"]

    df = df.with_columns(
        [
            pl.when(pl.col("Matched_Uom").str.to_uppercase().is_in(SUB_UNITS))
            .then(pl.col("Volume") * pl.col("PalletRatio_Cleaned"))
            .otherwise(pl.col("Volume"))
            .alias("Calculated_Storage_Volume")
        ]
    )

    df = df.with_columns(
        [
            # Priority 1: Heavy Liquid Containers (Regardless of description)
            pl.when(pl.col("Matched_Uom").str.to_uppercase().is_in(LIQUID_CONTAINERS))
            .then(pl.lit(950.0))  # standard density for full liquid drums/IBCs
            # Priority 2: Medium Containers (Check Category)
            .when(pl.col("Matched_Uom").str.to_uppercase().is_in(MEDIUM_CONTAINERS))
            .then(
                pl.when(pl.col("refined_category").is_in(["Chemical", "Food-Grade"]))
                .then(pl.lit(750.0))  # Heavy pails/tins (oil, chemicals)
                .otherwise(pl.lit(400.0))
            )
            # Priority 3: Fallback to Category Baseline for standard Cartons/Packages
            .otherwise(
                pl.when(pl.col("refined_category") == "Chemical")
                .then(pl.lit(600.0))
                .when(pl.col("refined_category") == "Food-Grade")
                .then(
                    # Final check for "Light" keywords in the NLP-cleaned description
                    pl.when(
                        pl.col("clean_description").str.contains(
                            r"(?i)\b(chicken|frozen|powder|bread|snack)\b"
                        )
                    )
                    .then(pl.lit(400.0))
                    .otherwise(pl.lit(650.0))
                )
                .when(pl.col("refined_category") == "Electronics")
                .then(pl.lit(250.0))
                .when(pl.col("refined_category") == "Packaging Material")
                .then(pl.lit(150.0))
                .otherwise(pl.lit(500.0))
            )
            .alias("Weight_Fixed")
        ]
    )
    df = df.with_columns(
        [
            pl.lit(STANDARD_WIDTH).alias("Width_Fixed"),
            pl.lit(STANDARD_DEPTH).alias("Depth_Fixed"),
            pl.when(
                (pl.col("Calculated_Storage_Volume") >= MIN_STORAGE_VOLUME)
                & (pl.col("Calculated_Storage_Volume") <= MAX_STORAGE_VOLUME)
            )
            .then(pl.col("Calculated_Storage_Volume"))
            .otherwise(
                pl.when(pl.col("refined_category") == "Food-Grade")
                .then(pl.lit(1.8))  # Standard food pallet height
                .when(pl.col("refined_category") == "Electronics")
                .then(pl.lit(1.2))  # Electronics often packed in shorter, denser stacks
                .when(pl.col("refined_category") == "Chemical")
                .then(pl.lit(1.5))  # Height for standard chemical totes/drums
                .otherwise(1.8)
            )
            .alias("Cubic_Vol_Fixed"),
        ]
    )
    return df.with_columns(
        [
            # 4. Calculate Cubic Volume based on the assigned dimensions
            (pl.col("Cubic_Vol_Fixed") / (STANDARD_WIDTH * STANDARD_DEPTH)).alias(
                "Height_Fixed"
            )
        ]
    )


if __name__ == "__main__":
    from db_utils import get_mssql_connection_uri

    uri_mssql = get_mssql_connection_uri()
    print("Running imputeDimension as standalone...")
    query = "SELECT TOP 100 * FROM dbo.admstock"
    df = pl.read_database_uri(query, uri_mssql)
    df_imputed = impute_dimensions(df)
    print(
        df_imputed.select(
            ["Width_Fixed", "Height_Fixed", "Depth_Fixed", "Cubic_Vol_Fixed"]
        ).head()
    )
