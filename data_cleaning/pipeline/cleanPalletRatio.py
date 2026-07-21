import polars as pl


def clean_ratios(df: pl.DataFrame) -> pl.DataFrame:
    """
    Cleans the PalletRatio column by handling non-numeric noise
    (like 'BAG', 'PAIL', or zeros) and defaulting them to 1.0.
    """
    return df.with_columns(
        pl.col("PalletRatio")
        .cast(pl.Utf8)
        .str.extract(r"(\d+\.?\d*)", 1)
        .cast(pl.Float64)
        .fill_null(1.0)
        .pipe(lambda s: pl.when(s == 0).then(1.0).otherwise(s))
        .alias("PalletRatio_Cleaned")
    )


if __name__ == "__main__":
    from db_utils import get_mssql_connection_uri

    uri_mssql = get_mssql_connection_uri()
    print("Running cleanPalletRatio as standalone...")
    query = "SELECT TOP 100 * FROM dbo.admstock"
    df = pl.read_database_uri(query, uri_mssql)
    df_cleaned = clean_ratios(df)
    print(df_cleaned.select(["PalletRatio", "PalletRatio_Cleaned"]).head())
