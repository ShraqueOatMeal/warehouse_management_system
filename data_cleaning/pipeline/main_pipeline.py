import polars as pl
from db_utils import get_mssql_connection_uri, get_pg_connection_uri
from cleanDate import clean_dates
from cleanPalletRatio import clean_ratios
from imputeDimension import impute_dimensions
from categorize import refine_stock_master, categorize_cold_room


def run_pipeline():
    try:
        # 1. Fetch Source Data
        uri_mssql = get_mssql_connection_uri()
        print("--- Step 1: Fetching Data from MSSQL ---")
        query = """
            SELECT
                s.*,
                p."PrincipalCode",
                u."Volume",
                u."Uom" as "Matched_Uom"
            FROM dbo.admstock s
            LEFT JOIN dbo.admstockprincipal p
                ON s."CompanyCode" = p."CompanyCode"
                AND s."BranchCode" = p."BranchCode"
                AND s."StockCode" = p."StockCode"
            LEFT JOIN dbo.admstockuom u
                ON s."StockCode" = u."StockCode"
            WHERE u."Volume" > 0 OR u."Volume" IS NULL
        """
        df = pl.read_database_uri(query, uri_mssql)
        print(f"Loaded {len(df)} records.")

        # 2. Sequential Cleaning (No more conflicts!)
        print("--- Step 2: Cleaning Dates ---")
        df = clean_dates(df)

        print("--- Step 3: Cleaning Pallet Ratios ---")
        df = clean_ratios(df)

        print("--- Step 4: Categorizing and NLP Processing ---")
        df = refine_stock_master(df)
        df = categorize_cold_room(df)

        print("--- Step 5: Imputing Dimensions ---")
        df = impute_dimensions(df)

        df = df.group_by("StockCode").agg(
            [
                pl.all().exclude("PrincipalCode").first(),
                pl.col("PrincipalCode").str.concat(", ").alias("PrincipalGroup"),
            ]
        )

        df = df.sort("Cubic_Vol_Fixed", descending=True).unique(subset=["StockCode"])

        df = df.with_columns(
            pl.when(pl.col("CartonRatio") == 0)
            .then(pl.col("PalletRatio_Cleaned") / 4)
            .otherwise(pl.col("CartonRatio"))
            .alias("CartonRatio_Cleaned")
        )

        # 3. Save Final Result
        print("--- Step 6: Saving Results ---")

        # Save to CSV
        output_csv = "refined_stock_master.csv"
        df.write_csv(output_csv)
        print(f"Saved refined data to {output_csv}")

        # Save to PostgreSQL
        print("Pumping refined data to PostgreSQL...")
        uri_pg = get_pg_connection_uri()
        df.write_database(
            table_name="refined_stock_master",
            connection=uri_pg,
            if_table_exists="replace",
            engine="adbc",  # Fast engine
        )
        print("Successfully uploaded data to PostgreSQL.")

        print("--- Pipeline Completed Successfully ---")
        print(f"Final column count: {len(df.columns)}")
        print(df.head(5))

    except Exception as e:
        print(f"!!! Pipeline Failed: {e} !!!")


if __name__ == "__main__":
    run_pipeline()
