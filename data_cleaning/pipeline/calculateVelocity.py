import polars as pl


def calculate_abc_velocity(df: pl.DataFrame) -> pl.DataFrame:
    """
    Final Velocity Engine:
    1. Filters for physical bin touches (Inbound & Outbound).
    2. Uses 'Unique Document Count' to measure actual labor frequency (Hits).
    3. Ranks SKUs based on Pareto ABC logic for slotting optimization.
    """

    # 1. Isolate Physical touches and filter administrative noise
    physical_df = df.filter(
        (pl.col("LocationCode").is_not_null())
        & (pl.col("DocumentType").is_in(["PICK", "PWAY", "RECV"]))
    )

    # 2. The Engine: Group by StockCode to calculate Hits vs Volume
    # We use n_unique("DocumentNo") to count actual trips/labor events.
    velocity_stats = physical_df.group_by("StockCode").agg(
        [
            # Labor Frequency (Hits)
            pl.col("DocumentNo")
            .filter(pl.col("LocationBaseQty") > 0)
            .n_unique()
            .alias("Inbound_Hits"),
            pl.col("DocumentNo")
            .filter(pl.col("LocationBaseQty") < 0)
            .n_unique()
            .alias("Outbound_Hits"),
            # Physical Throughput (Quantity)
            pl.col("LocationBaseQty").fill_null(0).abs().sum().alias("Total_Qty_Moved"),
            # Recency Audit
            pl.col("DocumentDate").max().alias("Last_Touch_Date"),
        ]
    )

    # 3. Calculate Final Scores and Ranks
    return (
        velocity_stats.with_columns(
            [
                # Total Hits is our primary optimization metric for travel distance
                (pl.col("Inbound_Hits") + pl.col("Outbound_Hits")).alias("Total_Hits")
            ]
        )
        .with_columns(
            [
                # Apply ABC Rank based on Labor Frequency (Hits)
                pl.col("Total_Hits")
                .rank(method="ordinal", descending=True)
                .alias("Rank")
            ]
        )
        .with_columns(
            [
                pl.when(pl.col("Rank") <= (pl.count() * 0.2))
                .then(pl.lit("A"))
                .when(pl.col("Rank") <= (pl.count() * 0.5))
                .then(pl.lit("B"))
                .otherwise(pl.lit("C"))
                .alias("Velocity_Class")
            ]
        )
        .sort("Total_Hits", descending=True)
    )
