import polars as pl

def clean_dates(df: pl.DataFrame) -> pl.DataFrame:
    """
    Cleans the CreateDate column by removing non-numeric/date strings 
    and casting to datetime.
    """
    return df.with_columns(
        pl.col("CreateDate")
        .cast(pl.Utf8)
        # If it has any letters, it's likely noise like 'N/A' or 'Unknown'
        .pipe(lambda s: pl.when(s.str.contains(r"[a-zA-Z]")).then(None).otherwise(s))
        .str.to_datetime(strict=False)
        .alias("CreateDate_Cleaned")
    )

if __name__ == "__main__":
    from db_utils import get_mssql_connection_uri
    try:
        uri_mssql = get_mssql_connection_uri()
        print("Running cleanDate as standalone...")
        query = "SELECT TOP 100 CreateDate FROM dbo.admstock"
        df = pl.read_database_uri(query, uri_mssql)
        df_cleaned = clean_dates(df)
        print(df_cleaned.select(["CreateDate", "CreateDate_Cleaned"]).head())
    except Exception as e:
        print(f"Error: {e}")
