import polars as pl


def cure_missing_locations(
    stock_df: pl.DataFrame, transaction_df: pl.DataFrame
) -> pl.DataFrame:
    """
    Fills null Primary_Location values in AdmStock using the
    most recent non-null location from WmsTransaction history.
    """

    # 1. Isolate the most recent valid location for each SKU
    # We filter for non-null LocationCode and relevant physical moves [cite: 152, 1817]
    latest_location_df = (
        transaction_df.filter(
            (pl.col("LocationCode").is_not_null())
            & (pl.col("DocumentType").is_in(["PICK", "PWAY", "RECV"]))
        )
        .sort(["StockCode", "DocumentDate"], descending=[False, True])
        .unique(subset=["StockCode"], keep="first")
        .select(["StockCode", "LocationCode"])
        .rename({"LocationCode": "Derived_Location"})
    )

    # 2. Join back to your Refined Stock Master [cite: 1829]
    merged_df = stock_df.join(latest_location_df, on="StockCode", how="left")

    # 3. Fallback logic: Use Original -> then Derived -> then "UNASSIGNED" [cite: 151, 153]
    cured_df = merged_df.with_columns(
        pl.coalesce(
            [
                pl.col("Primary_Location"),
                pl.col("Derived_Location"),
                pl.lit("UNASSIGNED/STAGING"),
            ]
        ).alias("Cured_Location")
    )

    return cured_df


if __name__ == "__main__":
    from db_utils import get_pg_connection_uri
    from db_utils import get_mssql_connection_uri

    try:
        uri_pg = get_pg_connection_uri()
        uri_mssql = get_mssql_connection_uri()
        print("Running cleanMissingLocations as standalone...")
        query_stock = "SELECT TOP 100 * FROM refined_stock_master"
        query_transaction = "SELECT TOP 100 * FROM refined_transaction_master"
        stock_df = pl.read_database_uri(query_stock, uri_pg)
        transaction_df = pl.read_database_uri(query_transaction, uri_mssql)
        cured_df = cure_missing_locations(stock_df, transaction_df)
        print(
            cured_df.select(
                ["StockCode", "Primary_Location", "Derived_Location", "Cured_Location"]
            ).head()
        )
    except Exception as e:
        print(f"Error: {e}")
